
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
terminal_authority_audit.py

Aggregate single-vehicle TAEM / terminal-regulator runs into one audit table.

Inputs:
  - explicit CSV paths via --inputs
  - or a glob pattern via --glob

Outputs:
  - terminal_authority_audit_summary.csv
  - terminal_authority_audit_notes.md
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def pick_col(df: pd.DataFrame, *names: str) -> str | None:
    for n in names:
        if n in df.columns:
            return n
    return None


def bool_col(df: pd.DataFrame, *names: str) -> pd.Series:
    c = pick_col(df, *names)
    if c is None:
        return pd.Series(False, index=df.index)
    s = df[c]
    if pd.api.types.is_bool_dtype(s):
        return s.fillna(False)
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce").fillna(0.0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])


def num_col(df: pd.DataFrame, *names: str) -> pd.Series:
    c = pick_col(df, *names)
    if c is None:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[c], errors="coerce")


def first_row_where(df: pd.DataFrame, mask: pd.Series) -> pd.Series | None:
    sub = df.loc[mask]
    return sub.iloc[0] if len(sub) else None


def last_end_or_last(df: pd.DataFrame) -> pd.Series:
    end_mask = bool_col(df, "end_guide")
    if end_mask.any():
        return df.loc[end_mask].iloc[-1]
    return df.iloc[-1]


def min_abs_row(df: pd.DataFrame, col: str) -> tuple[int | None, float]:
    s = num_col(df, col)
    if not s.notna().any():
        return None, np.nan
    idx = s.abs().idxmin()
    return int(idx), float(s.loc[idx])


def state_path(df: pd.DataFrame) -> str:
    c = pick_col(df, "terminal_supervisor_state")
    if c is None:
        return ""
    vals = df[c].dropna().astype(str)
    if len(vals) == 0:
        return ""
    path = []
    prev = None
    for v in vals:
        if v != prev:
            path.append(v)
            prev = v
    return " -> ".join(path)


def summarize_one(csv_path: Path) -> dict:
    df = pd.read_csv(csv_path, low_memory=False)

    tcol = pick_col(df, "t_local", "global_t", "t")
    if tcol is None:
        df["__row__"] = np.arange(len(df), dtype=float)
        tcol = "__row__"

    authority = bool_col(df, "terminal_authority_active", "terminal_capture_active")
    taem_in_box = bool_col(df, "taem_in_box")
    taem_reached = bool_col(df, "taem_reached")
    success_latched = bool_col(df, "taem_success_latched")
    fail_latched = bool_col(df, "taem_fail_latched")
    close_escape = bool_col(df, "close_pass_escape")
    box = num_col(df, "box_score", "taem_box_score")

    first_auth = first_row_where(df, authority)
    end_row = last_end_or_last(df)

    best_box_idx = int(box.idxmax()) if box.notna().any() else None
    best_box_row = df.loc[best_box_idx] if best_box_idx is not None else None

    h_idx, h_val = min_abs_row(df, "taem_h_err")
    v_idx, v_val = min_abs_row(df, "taem_v_err")
    s_idx, s_val = min_abs_row(df, "taem_s_go_err")

    def row_get(row, key, default=np.nan):
        if row is None:
            return default
        try:
            return float(pd.to_numeric(row[key], errors="coerce"))
        except Exception:
            return default

    def row_get_str(row, key, default=""):
        if row is None:
            return default
        try:
            x = row.get(key, default)
            if pd.isna(x):
                return default
            return str(x)
        except Exception:
            return default

    summary = {
        "run_id": csv_path.stem,
        "csv": str(csv_path),
        "rows": int(len(df)),
        "time_col": tcol,
        "terminal_state_path": state_path(df),

        "authority_active_any": bool(authority.any()),
        "authority_first_t": row_get(first_auth, tcol),
        "authority_first_h": row_get(first_auth, "height"),
        "authority_first_v": row_get(first_auth, "velocity"),
        "authority_first_s_go": row_get(first_auth, "s_go"),
        "authority_first_delta_psi": row_get(first_auth, "delta_psi"),

        "best_box_score": float(box.max()) if box.notna().any() else np.nan,
        "best_box_t": row_get(best_box_row, tcol),
        "best_box_h": row_get(best_box_row, "height"),
        "best_box_v": row_get(best_box_row, "velocity"),
        "best_box_s_go": row_get(best_box_row, "s_go"),
        "best_box_delta_psi": row_get(best_box_row, "delta_psi"),

        "min_abs_taem_h_err": abs(h_val) if pd.notna(h_val) else np.nan,
        "min_abs_taem_h_err_t": row_get(df.loc[h_idx] if h_idx is not None else None, tcol),
        "min_abs_taem_h_err_h": row_get(df.loc[h_idx] if h_idx is not None else None, "height"),
        "min_abs_taem_h_err_v": row_get(df.loc[h_idx] if h_idx is not None else None, "velocity"),
        "min_abs_taem_h_err_s_go": row_get(df.loc[h_idx] if h_idx is not None else None, "s_go"),
        "min_abs_taem_h_err_delta_psi": row_get(df.loc[h_idx] if h_idx is not None else None, "delta_psi"),

        "min_abs_taem_v_err": abs(v_val) if pd.notna(v_val) else np.nan,
        "min_abs_taem_v_err_t": row_get(df.loc[v_idx] if v_idx is not None else None, tcol),
        "min_abs_taem_v_err_h": row_get(df.loc[v_idx] if v_idx is not None else None, "height"),
        "min_abs_taem_v_err_v": row_get(df.loc[v_idx] if v_idx is not None else None, "velocity"),
        "min_abs_taem_v_err_s_go": row_get(df.loc[v_idx] if v_idx is not None else None, "s_go"),
        "min_abs_taem_v_err_delta_psi": row_get(df.loc[v_idx] if v_idx is not None else None, "delta_psi"),

        "min_abs_taem_s_go_err": abs(s_val) if pd.notna(s_val) else np.nan,
        "min_abs_taem_s_go_err_t": row_get(df.loc[s_idx] if s_idx is not None else None, tcol),
        "min_abs_taem_s_go_err_h": row_get(df.loc[s_idx] if s_idx is not None else None, "height"),
        "min_abs_taem_s_go_err_v": row_get(df.loc[s_idx] if s_idx is not None else None, "velocity"),
        "min_abs_taem_s_go_err_s_go": row_get(df.loc[s_idx] if s_idx is not None else None, "s_go"),
        "min_abs_taem_s_go_err_delta_psi": row_get(df.loc[s_idx] if s_idx is not None else None, "delta_psi"),

        "taem_in_box_any": bool(taem_in_box.any()),
        "taem_reached_any": bool(taem_reached.any()),
        "taem_success_latched_any": bool(success_latched.any()),
        "taem_fail_latched_any": bool(fail_latched.any()),
        "close_pass_escape_any": bool(close_escape.any()),

        "end_reason": row_get_str(end_row, "end_reason"),
        "final_t": row_get(end_row, tcol),
        "final_h": row_get(end_row, "height"),
        "final_v": row_get(end_row, "velocity"),
        "final_s_go": row_get(end_row, "s_go"),
        "final_delta_psi": row_get(end_row, "delta_psi"),
    }

    return summary


def build_notes(df: pd.DataFrame) -> str:
    lines = []
    lines.append("# Terminal Authority Audit Notes")
    lines.append("")
    lines.append("## Quick ranking")
    if len(df):
        rank = df.sort_values(["taem_reached_any", "best_box_score", "min_abs_taem_s_go_err"], ascending=[False, False, True])
        for _, r in rank.iterrows():
            lines.append(
                f"- **{r['run_id']}**: reached={bool(r['taem_reached_any'])}, "
                f"best_box_score={r['best_box_score']:.3f}, "
                f"min|h_err|={r['min_abs_taem_h_err']:.1f} m, "
                f"min|v_err|={r['min_abs_taem_v_err']:.2f} m/s, "
                f"min|s_go_err|={r['min_abs_taem_s_go_err']:.1f} m, "
                f"end_reason={r['end_reason']}"
            )
    lines.append("")
    lines.append("## Common patterns")
    lines.append("- Runs that reduce `s_go` well still tend to carry a large `delta_psi` when the best `h/v` moments occur.")
    lines.append("- Good single-axis moments do not coincide in time; the audit is built specifically to show that mismatch.")
    lines.append("- The redesigned terminal controller should be judged against this table before any new multi-vehicle work.")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*", default=[], help="Explicit CSV inputs")
    ap.add_argument("--glob", default=None, help="Glob pattern for CSV inputs")
    ap.add_argument("--outdir", required=True, help="Output directory")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    paths = [Path(p) for p in args.inputs]
    if args.glob:
        paths.extend(sorted(Path().glob(args.glob)))
    # de-dup preserve order
    seen = set()
    uniq = []
    for p in paths:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(p)

    if not uniq:
        raise SystemExit("No input CSVs found.")

    rows = [summarize_one(p) for p in uniq]
    df = pd.DataFrame(rows).sort_values("run_id")
    df.to_csv(outdir / "terminal_authority_audit_summary.csv", index=False)

    notes = build_notes(df)
    (outdir / "terminal_authority_audit_notes.md").write_text(notes, encoding="utf-8")

    print("[OK] Wrote:")
    print(f"  - {outdir / 'terminal_authority_audit_summary.csv'}")
    print(f"  - {outdir / 'terminal_authority_audit_notes.md'}")


if __name__ == "__main__":
    main()
