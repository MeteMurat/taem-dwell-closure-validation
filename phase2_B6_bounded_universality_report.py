# -*- coding: utf-8 -*-
"""
phase2_B6_bounded_universality_report.py

B6 — Bounded Universality Evidence Pack

Purpose
-------
This is a post-processing/reporting script only. It does NOT run simulations and
does NOT modify guidance/multiset files.

It consolidates:
  - B5D tight local-envelope positive evidence
  - B5E mis0-corner bounded diagnostic evidence
  - B5F mis0 reachability/pathspec audit evidence

Outputs:
  - phase2_B6_campaign_summary.csv
  - phase2_B6_campaign_summary.md
  - phase2_B6_key_metrics.json
  - phase2_B6_bounded_universality_claim.txt
  - phase2_B6_failure_boundary_notes.txt
  - phase2_B6_manuscript_ready_block.md

Recommended claim:
  Bounded local U3 universality is supported inside the tight local envelope.
  Global/broad universality is not claimed. B5E/B5F define the current boundary.

Run:
  python phase2_B6_bounded_universality_report.py --config phase2_B6_campaign_summary_config.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# -----------------------------
# Generic utilities
# -----------------------------

def _as_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    if x is None:
        return False
    try:
        if isinstance(x, (int, float, np.integer, np.floating)):
            if not np.isfinite(float(x)):
                return False
            return float(x) > 0.5
    except Exception:
        pass
    s = str(x).strip().lower()
    return s in {"1", "true", "t", "yes", "y", "pass", "passed", "strict_pass", "pass_strict"}


def _num_or_nan(x: Any) -> float:
    try:
        y = float(x)
        return y if math.isfinite(y) else float("nan")
    except Exception:
        return float("nan")


def _safe_mean(values) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(arr).any():
        return float("nan")
    return float(np.nanmean(arr))


def _safe_min(values) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(arr).any():
        return float("nan")
    return float(np.nanmin(arr))


def _safe_max(values) -> float:
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(arr).any():
        return float("nan")
    return float(np.nanmax(arr))


def _fmt_pct(x: Any) -> str:
    x = _num_or_nan(x)
    if not math.isfinite(x):
        return "N/A"
    return f"{100.0*x:.2f}%"


def _fmt_num(x: Any, nd: int = 3) -> str:
    x = _num_or_nan(x)
    if not math.isfinite(x):
        return "N/A"
    if abs(x) >= 1e6 or (abs(x) > 0 and abs(x) < 1e-3):
        return f"{x:.{nd}e}"
    return f"{x:.{nd}f}"


def resolve_path(root: Path, candidates: List[str]) -> Optional[Path]:
    for c in candidates:
        p = Path(c)
        if not p.is_absolute():
            p = root / p
        if p.exists():
            return p
    return None


def decision_counts(df: pd.DataFrame) -> str:
    if "decision" not in df.columns or len(df) == 0:
        return ""
    vc = df["decision"].astype(str).value_counts(dropna=False)
    return "; ".join([f"{k}:{int(v)}" for k, v in vc.items()])


def bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    return df[col].map(_as_bool)


def numeric_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([np.nan] * len(df), index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


# -----------------------------
# Campaign summarizers
# -----------------------------

def summarize_manual(camp: Dict[str, Any]) -> Dict[str, Any]:
    stats = camp.get("manual_stats", {})
    n_cases = int(stats.get("n_cases", 0))
    n_vehicles = int(stats.get("n_vehicles", 0))
    case_pass = int(stats.get("case_pass", 0))
    vehicle_pass = int(stats.get("vehicle_pass", 0))

    case_pass_rate = case_pass / n_cases if n_cases else float("nan")
    vehicle_pass_rate = vehicle_pass / n_vehicles if n_vehicles else float("nan")

    return {
        "campaign_id": camp["campaign_id"],
        "campaign_label": camp.get("campaign_label", camp["campaign_id"]),
        "evidence_role": camp.get("evidence_role", "positive"),
        "source_status": "manual_stats",
        "source_path": "",
        "n_cases_or_runs": n_cases,
        "n_vehicles": n_vehicles,
        "case_or_run_pass": case_pass,
        "vehicle_pass": vehicle_pass,
        "case_or_run_pass_rate": case_pass_rate,
        "vehicle_pass_rate": vehicle_pass_rate,
        "timeout_count": int(stats.get("timeout_count", 0)),
        "timeout_rate": float(stats.get("timeout_rate", 0.0)),
        "dominant_decision": stats.get("dominant_decision", ""),
        "decision_counts": stats.get("decision_counts", ""),
        "best_case_id": stats.get("best_case_id", ""),
        "best_candidate_id": stats.get("best_candidate_id", ""),
        "best_score": _num_or_nan(stats.get("best_score", np.nan)),
        "min_s_go_final_m": _num_or_nan(stats.get("min_s_go_final_m", np.nan)),
        "max_s_go_drop_pct": _num_or_nan(stats.get("max_s_go_drop_pct", np.nan)),
        "pathspec_active_any": stats.get("pathspec_active_any", ""),
        "guide_phase_last_mode": stats.get("guide_phase_last_mode", ""),
        "dominant_failure_mode": stats.get("dominant_failure_mode", ""),
        "interpretation": camp.get("interpretation", ""),
        "recommended_use": camp.get("recommended_use", ""),
    }


def summarize_csv_by_run(camp: Dict[str, Any], root: Path) -> Dict[str, Any]:
    source = resolve_path(root, camp.get("path_candidates", []))

    if source is None:
        # Fall back to manual stats if provided, but preserve missing status.
        if "manual_stats" in camp:
            row = summarize_manual(camp)
            row["source_status"] = "missing_csv_used_manual_fallback"
            return row
        return {
            "campaign_id": camp["campaign_id"],
            "campaign_label": camp.get("campaign_label", camp["campaign_id"]),
            "evidence_role": camp.get("evidence_role", "unknown"),
            "source_status": "missing_csv",
            "source_path": "",
            "n_cases_or_runs": 0,
            "n_vehicles": 0,
            "case_or_run_pass": 0,
            "vehicle_pass": 0,
            "case_or_run_pass_rate": float("nan"),
            "vehicle_pass_rate": float("nan"),
            "timeout_count": 0,
            "timeout_rate": float("nan"),
            "dominant_decision": "",
            "decision_counts": "",
            "best_case_id": "",
            "best_candidate_id": "",
            "best_score": float("nan"),
            "min_s_go_final_m": float("nan"),
            "max_s_go_drop_pct": float("nan"),
            "pathspec_active_any": "",
            "guide_phase_last_mode": "",
            "dominant_failure_mode": "CSV not found",
            "interpretation": camp.get("interpretation", ""),
            "recommended_use": camp.get("recommended_use", ""),
        }

    df = pd.read_csv(source)
    n = int(len(df))

    strict = bool_col(df, "strict_pass")
    pass_count = int(strict.sum())
    pass_rate = pass_count / n if n else float("nan")

    timed = bool_col(df, "timed_out")
    timeout_count = int(timed.sum())
    timeout_rate = timeout_count / n if n else float("nan")

    # Best row: strict pass first, then lowest score.
    dwork = df.copy()
    if "score" not in dwork.columns:
        dwork["score"] = np.nan
    dwork["_strict_sort"] = strict.astype(int)
    dwork["_score_sort"] = pd.to_numeric(dwork["score"], errors="coerce").fillna(1e99)
    dwork = dwork.sort_values(["_strict_sort", "_score_sort"], ascending=[False, True])
    best = dwork.iloc[0].to_dict() if n else {}

    dom_dec = ""
    if "decision" in df.columns and n:
        dom_dec = str(df["decision"].astype(str).value_counts().idxmax())

    pathspec_active_any = ""
    if "pathspec_active" in df.columns:
        pathspec_active_any = bool(bool_col(df, "pathspec_active").any())

    guide_phase_last_mode = ""
    if "guide_phase_last" in df.columns and n:
        modes = df["guide_phase_last"].dropna().astype(str)
        if len(modes):
            guide_phase_last_mode = str(modes.value_counts().idxmax())

    n_vehicles = int(camp.get("n_vehicles", n))

    return {
        "campaign_id": camp["campaign_id"],
        "campaign_label": camp.get("campaign_label", camp["campaign_id"]),
        "evidence_role": camp.get("evidence_role", "diagnostic"),
        "source_status": "csv_loaded",
        "source_path": str(source),
        "n_cases_or_runs": n,
        "n_vehicles": n_vehicles,
        "case_or_run_pass": pass_count,
        "vehicle_pass": int(camp.get("vehicle_pass", pass_count)),
        "case_or_run_pass_rate": pass_rate,
        "vehicle_pass_rate": float(camp.get("vehicle_pass_rate", pass_rate)),
        "timeout_count": timeout_count,
        "timeout_rate": timeout_rate,
        "dominant_decision": dom_dec,
        "decision_counts": decision_counts(df),
        "best_case_id": str(best.get("case_id", "")),
        "best_candidate_id": str(best.get("candidate_id", "")),
        "best_score": _num_or_nan(best.get("score", np.nan)),
        "min_s_go_final_m": _safe_min(numeric_col(df, "s_go_final")) if "s_go_final" in df.columns else float("nan"),
        "max_s_go_drop_pct": _safe_max(numeric_col(df, "s_go_drop_pct")) if "s_go_drop_pct" in df.columns else float("nan"),
        "pathspec_active_any": pathspec_active_any,
        "guide_phase_last_mode": guide_phase_last_mode,
        "dominant_failure_mode": camp.get("dominant_failure_mode", ""),
        "interpretation": camp.get("interpretation", ""),
        "recommended_use": camp.get("recommended_use", ""),
    }


def summarize_campaign(camp: Dict[str, Any], root: Path) -> Dict[str, Any]:
    typ = camp.get("type", "csv_by_run")
    if typ == "manual":
        return summarize_manual(camp)
    if typ == "csv_by_run":
        return summarize_csv_by_run(camp, root)
    raise ValueError(f"Unsupported campaign type: {typ}")


# -----------------------------
# Output writers
# -----------------------------

def make_markdown_summary(summary: pd.DataFrame, cfg: Dict[str, Any]) -> str:
    lines = []
    lines.append("# Phase 2 B6 — Bounded Universality Evidence Pack")
    lines.append("")
    lines.append("## Executive conclusion")
    lines.append("")
    lines.append(cfg.get("executive_conclusion", "").strip())
    lines.append("")
    lines.append("## Campaign-level evidence table")
    lines.append("")
    cols = [
        "campaign_id", "evidence_role", "source_status", "n_cases_or_runs",
        "case_or_run_pass_rate", "vehicle_pass_rate", "timeout_rate",
        "dominant_decision", "dominant_failure_mode", "recommended_use",
    ]
    lines.append("| " + " | ".join(cols) + " |")
    lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for _, r in summary.iterrows():
        vals = []
        for c in cols:
            v = r.get(c, "")
            if c.endswith("_rate"):
                vals.append(_fmt_pct(v))
            else:
                vals.append(str(v).replace("\n", " "))
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    lines.append("## Detailed campaign interpretation")
    lines.append("")
    for _, r in summary.iterrows():
        lines.append(f"### {r['campaign_id']} — {r['campaign_label']}")
        lines.append("")
        lines.append(f"- Evidence role: `{r['evidence_role']}`")
        lines.append(f"- Source status: `{r['source_status']}`")
        if str(r.get("source_path", "")):
            lines.append(f"- Source path: `{r['source_path']}`")
        lines.append(f"- Pass rate: {_fmt_pct(r['case_or_run_pass_rate'])}")
        lines.append(f"- Vehicle pass rate: {_fmt_pct(r['vehicle_pass_rate'])}")
        lines.append(f"- Timeout rate: {_fmt_pct(r['timeout_rate'])}")
        lines.append(f"- Dominant decision: `{r.get('dominant_decision', '')}`")
        lines.append(f"- Decision counts: `{r.get('decision_counts', '')}`")
        if pd.notna(r.get("min_s_go_final_m", np.nan)):
            lines.append(f"- Minimum final range-to-go: {_fmt_num(r['min_s_go_final_m'])} m")
        if pd.notna(r.get("max_s_go_drop_pct", np.nan)):
            lines.append(f"- Maximum range-closure percentage: {_fmt_num(r['max_s_go_drop_pct'])}%")
        if str(r.get("guide_phase_last_mode", "")):
            lines.append(f"- Dominant last guidance phase: `{r['guide_phase_last_mode']}`")
        if str(r.get("pathspec_active_any", "")):
            lines.append(f"- PathSpec active in any row: `{r['pathspec_active_any']}`")
        lines.append("")
        lines.append(f"Interpretation: {r.get('interpretation', '')}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def make_claim_text(summary: pd.DataFrame, cfg: Dict[str, Any]) -> str:
    b5d = summary[summary["campaign_id"].astype(str).str.contains("B5D", case=False, na=False)]
    b5e = summary[summary["campaign_id"].astype(str).str.contains("B5E", case=False, na=False)]
    b5f = summary[summary["campaign_id"].astype(str).str.contains("B5F", case=False, na=False)]

    b5d_case = _fmt_pct(b5d.iloc[0]["case_or_run_pass_rate"]) if len(b5d) else "N/A"
    b5d_vehicle = _fmt_pct(b5d.iloc[0]["vehicle_pass_rate"]) if len(b5d) else "N/A"
    b5e_pass = _fmt_pct(b5e.iloc[0]["case_or_run_pass_rate"]) if len(b5e) else "N/A"
    b5f_pass = _fmt_pct(b5f.iloc[0]["case_or_run_pass_rate"]) if len(b5f) else "N/A"

    return f"""Recommended universality wording

The proposed guidance framework is not claimed to be globally universal over all
initial dispersions, route-shaping choices, and terminal-corner cases. Instead,
the evidence supports a bounded local-universality claim over the tight U3
envelope. In the B5D tight local-envelope validation, the case-level success
rate is {b5d_case}, while the vehicle-level success rate is {b5d_vehicle}.
This supports a strong local U3 envelope result.

The B5E and B5F campaigns should be retained as failure-boundary diagnostics
rather than negative evidence against the bounded claim. B5E achieved a
case-level pass rate of {b5e_pass}, and B5F achieved a case-level pass rate of
{b5f_pass}. These campaigns identify the mis0-left corner as outside the
currently certified envelope under the present guidance phase-transition and
terminal-capture logic.

Manuscript-safe claim:
"The method demonstrates bounded local U3 universality within the validated
tight envelope, while the mis0-left corner cases define the current
reachability boundary. We therefore do not claim global universality; instead,
we report an explicitly bounded and reproducible domain of validity."
"""


def make_failure_boundary_notes(summary: pd.DataFrame, cfg: Dict[str, Any]) -> str:
    lines = []
    lines.append("B6 failure-boundary notes")
    lines.append("")
    lines.append("1. B5E/B5F should not be treated as failed replications of B5D.")
    lines.append("   They probe a harder mis0-left corner outside the tight local U3 envelope.")
    lines.append("")
    lines.append("2. Repeated psi_bias/fade sweeps are not recommended at this point.")
    lines.append("   B5E showed no strict pass and did not produce useful candidate separation.")
    lines.append("")
    lines.append("3. Brute-force MAXITER expansion is not recommended as the primary route.")
    lines.append("   B5F showed range closure in one long-propagation case, but no TAEM latch;")
    lines.append("   other long runs timed out or failed to yield a usable pass.")
    lines.append("")
    lines.append("4. The correct technical interpretation is a guidance phase-transition /")
    lines.append("   terminal-capture boundary, not a broad failure of the validated U3 envelope.")
    lines.append("")
    lines.append("5. Future work should target a dedicated mis0 terminal-capture update before")
    lines.append("   expanding the certified envelope beyond B5D.")
    lines.append("")
    for _, r in summary.iterrows():
        if str(r.get("evidence_role", "")).lower().startswith("boundary") or "failure" in str(r.get("evidence_role", "")).lower():
            lines.append(f"- {r['campaign_id']}: {r.get('dominant_decision','')} | {r.get('interpretation','')}")
    return "\n".join(lines).strip() + "\n"


def make_manuscript_block(summary: pd.DataFrame, cfg: Dict[str, Any]) -> str:
    b5d = summary[summary["campaign_id"].astype(str).str.contains("B5D", case=False, na=False)]
    b5e = summary[summary["campaign_id"].astype(str).str.contains("B5E", case=False, na=False)]
    b5f = summary[summary["campaign_id"].astype(str).str.contains("B5F", case=False, na=False)]

    b5d_case = _fmt_pct(b5d.iloc[0]["case_or_run_pass_rate"]) if len(b5d) else "N/A"
    b5d_vehicle = _fmt_pct(b5d.iloc[0]["vehicle_pass_rate"]) if len(b5d) else "N/A"
    b5e_n = int(b5e.iloc[0]["n_cases_or_runs"]) if len(b5e) else 0
    b5f_n = int(b5f.iloc[0]["n_cases_or_runs"]) if len(b5f) else 0

    return f"""# Manuscript-ready B6 paragraph

The validation results support a bounded local-universality interpretation
rather than an unrestricted global-universality claim. In the tight local U3
envelope, the B5D campaign achieved a case-level success rate of {b5d_case}
and a vehicle-level success rate of {b5d_vehicle}. This result indicates that
the guidance logic can consistently close the TAEM condition for the tested
three-vehicle local perturbation envelope. However, the subsequent B5E and B5F
diagnostic campaigns, comprising {b5e_n} bounded mis0-corner cases and {b5f_n}
long-propagation/pathspec-audit cases, did not produce a strict TAEM pass for
the mis0-left corner. These diagnostic cases are therefore interpreted as a
failure-boundary study. They delimit the present certified envelope and show
that the mis0-left corner requires a dedicated terminal-capture or
phase-transition refinement before a broader universality claim can be made.

# Manuscript-ready limitation sentence

Accordingly, the present study claims bounded local U3 universality only within
the validated tight envelope; broader U4-style or global universality is left as
future work after resolving the mis0-left terminal-capture boundary.
"""


def write_outputs(summary: pd.DataFrame, cfg: Dict[str, Any], outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)

    summary_path = outdir / "phase2_B6_campaign_summary.csv"
    summary.to_csv(summary_path, index=False)

    md = make_markdown_summary(summary, cfg)
    (outdir / "phase2_B6_campaign_summary.md").write_text(md, encoding="utf-8")

    claim = make_claim_text(summary, cfg)
    (outdir / "phase2_B6_bounded_universality_claim.txt").write_text(claim, encoding="utf-8")

    failure = make_failure_boundary_notes(summary, cfg)
    (outdir / "phase2_B6_failure_boundary_notes.txt").write_text(failure, encoding="utf-8")

    manuscript = make_manuscript_block(summary, cfg)
    (outdir / "phase2_B6_manuscript_ready_block.md").write_text(manuscript, encoding="utf-8")

    key_metrics = {
        "output_dir": str(outdir),
        "campaigns": summary.to_dict(orient="records"),
        "recommended_claim": "bounded local U3 universality within the tight validated envelope; no global universality claim",
    }
    (outdir / "phase2_B6_key_metrics.json").write_text(
        json.dumps(key_metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("[B6] Wrote:")
    for p in [
        summary_path,
        outdir / "phase2_B6_campaign_summary.md",
        outdir / "phase2_B6_key_metrics.json",
        outdir / "phase2_B6_bounded_universality_claim.txt",
        outdir / "phase2_B6_failure_boundary_notes.txt",
        outdir / "phase2_B6_manuscript_ready_block.md",
    ]:
        print(f"  - {p}")


# -----------------------------
# Main
# -----------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="B6 config JSON path")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    root = Path.cwd()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path

    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    outdir = Path(cfg.get("output_dir", "store/data_saved/phase2_B6_bounded_universality_evidence_pack"))
    if not outdir.is_absolute():
        outdir = root / outdir

    rows = []
    for camp in cfg.get("campaigns", []):
        rows.append(summarize_campaign(camp, root))

    summary = pd.DataFrame(rows)

    # Stable column order
    col_order = [
        "campaign_id", "campaign_label", "evidence_role", "source_status", "source_path",
        "n_cases_or_runs", "n_vehicles", "case_or_run_pass", "vehicle_pass",
        "case_or_run_pass_rate", "vehicle_pass_rate", "timeout_count", "timeout_rate",
        "dominant_decision", "decision_counts", "best_case_id", "best_candidate_id",
        "best_score", "min_s_go_final_m", "max_s_go_drop_pct", "pathspec_active_any",
        "guide_phase_last_mode", "dominant_failure_mode", "interpretation", "recommended_use",
    ]
    for c in col_order:
        if c not in summary.columns:
            summary[c] = np.nan
    summary = summary[col_order]

    write_outputs(summary, cfg, outdir)

    print("\n[B6] Summary:")
    print(summary[[
        "campaign_id", "source_status", "n_cases_or_runs",
        "case_or_run_pass_rate", "vehicle_pass_rate",
        "timeout_rate", "dominant_decision", "recommended_use"
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
