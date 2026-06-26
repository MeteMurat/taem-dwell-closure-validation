$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== TAEM terminal angular diagnostics generator ===" -ForegroundColor Cyan
Write-Host "Working directory:" (Get-Location)
Write-Host ""

$Root = Get-Location
$OutDir = Join-Path $Root "outputs\terminal_angular_diagnostics"
$PyPath = Join-Path $Root "make_terminal_angular_diagnostics.py"

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# ------------------------------------------------------------
# 1) Python diagnostic script oluştur
# ------------------------------------------------------------
$PythonCode = @'
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd


def safe_num(s):
    return pd.to_numeric(s, errors="coerce").astype(float)


def bool_series(df, col):
    if col not in df.columns:
        return pd.Series(False, index=df.index)

    s = df[col]

    if s.dtype == bool:
        return s

    if pd.api.types.is_numeric_dtype(s):
        return safe_num(s).fillna(0.0) > 0.5

    return s.astype(str).str.strip().str.lower().isin(["1", "true", "yes", "y", "t"])


def maybe_rad_to_deg_value(x):
    if pd.isna(x):
        return np.nan

    x = float(x)

    # Açı radyan gibi görünüyorsa dereceye çevir.
    if abs(x) <= 6.5:
        return np.degrees(x)

    return x


def wrap_pi(x):
    return (x + np.pi) % (2 * np.pi) - np.pi


def pick_event_row(g):
    """
    Dwell-confirmed strict TAEM event row seçimi.

    Öncelik:
    1) end_reason == taem_dwell_reached
    2) end_reason kolonu yoksa, TAEM latch/reached/success flag fallback

    Not:
    Eğer end_reason kolonu varsa fakat taem_dwell_reached yoksa,
    o vehicle strict terminal angular diagnostics tablosuna dahil edilmez.
    """
    if "end_reason" in g.columns:
        m = g["end_reason"].astype(str).str.strip().eq("taem_dwell_reached")
        if m.any():
            return g.loc[m].iloc[0]
        return None

    flag_cols = [
        "taem_success_latched",
        "taem_latched",
        "taem_reached_event",
        "taem_reached",
        "taem_success",
        "taem_in_box",
    ]

    m = pd.Series(False, index=g.index)

    for c in flag_cols:
        if c in g.columns:
            m = m | bool_series(g, c)

    if m.any():
        return g.loc[m].iloc[0]

    return None


def get_delta_psi_deg(row):
    # Önce doğrudan delta_psi kolonunu kullan.
    if "delta_psi" in row.index and pd.notna(row["delta_psi"]):
        return maybe_rad_to_deg_value(row["delta_psi"])

    # Yoksa heading_angle - ref_psi hesapla.
    if "heading_angle" in row.index and "ref_psi" in row.index:
        psi = row["heading_angle"]
        ref = row["ref_psi"]

        if pd.notna(psi) and pd.notna(ref):
            return np.degrees(wrap_pi(float(psi) - float(ref)))

    return np.nan


def get_gamma_deg(row):
    for c in ["path_angle", "gamma", "flight_path_angle"]:
        if c in row.index and pd.notna(row[c]):
            return maybe_rad_to_deg_value(row[c])

    return np.nan


def role_name(v):
    try:
        iv = int(v)
        return f"Vehicle~{iv + 1}"
    except Exception:
        return str(v)


def fmt(x):
    if pd.isna(x):
        return "--"
    return f"{float(x):.3f}"


def percentile_95(x):
    x = pd.to_numeric(x, errors="coerce").dropna()
    if len(x) == 0:
        return np.nan
    return float(np.percentile(x, 95))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", required=True, help="Glob pattern for final combined CSV files")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--idcol", default="mis_id", help="Vehicle id column")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    files = sorted(glob.glob(args.glob))

    if not files:
        raise SystemExit(f"No CSV files found for glob: {args.glob}")

    rows = []

    for f in files:
        try:
            df = pd.read_csv(f)
        except Exception as e:
            print(f"[WARN] Could not read CSV: {f} ({e})")
            continue

        idcol = args.idcol if args.idcol in df.columns else None

        if idcol is None:
            if "mis_id" in df.columns:
                idcol = "mis_id"
            else:
                df["mis_id"] = 0
                idcol = "mis_id"

        if "global_t" in df.columns:
            tcol = "global_t"
        elif "t_local" in df.columns:
            tcol = "t_local"
        elif "t" in df.columns:
            tcol = "t"
        else:
            df["__row_index__"] = np.arange(len(df), dtype=float)
            tcol = "__row_index__"

        for vid, g in df.groupby(idcol):
            g = g.sort_values(tcol)
            event_row = pick_event_row(g)

            if event_row is None:
                continue

            # Close-pass escape olanları strict angular diagnostic tablosuna dahil etme.
            close_cols = ["close_pass_escape", "close_pass_escape_latched", "escape_latched"]
            is_escape = False

            for c in close_cols:
                if c in event_row.index:
                    val = event_row[c]
                    sval = str(val).strip().lower()

                    if sval in ["1", "true", "yes", "y", "t"]:
                        is_escape = True
                    else:
                        try:
                            is_escape = is_escape or (float(val) > 0.5)
                        except Exception:
                            pass

            if is_escape:
                continue

            dpsi_deg = get_delta_psi_deg(event_row)
            gamma_deg = get_gamma_deg(event_row)

            try:
                vid_sort = int(vid)
            except Exception:
                vid_sort = 999

            rows.append({
                "csv": Path(f).name,
                "vehicle_id": vid,
                "vehicle_sort": vid_sort,
                "vehicle_role": role_name(vid),
                "event_time_s": float(event_row[tcol]) if pd.notna(event_row[tcol]) else np.nan,
                "abs_delta_psi_deg": abs(dpsi_deg) if pd.notna(dpsi_deg) else np.nan,
                "abs_gamma_deg": abs(gamma_deg) if pd.notna(gamma_deg) else np.nan,
            })

    events = pd.DataFrame(rows)

    if events.empty:
        raise SystemExit(
            "No terminal angular event rows found. "
            "Check whether the final CSV files contain end_reason == taem_dwell_reached."
        )

    events = events.sort_values(["vehicle_sort", "csv"]).reset_index(drop=True)
    events.to_csv(outdir / "terminal_angular_events.csv", index=False)

    summary = (
        events
        .groupby(["vehicle_sort", "vehicle_role"], sort=True)
        .agg(
            n_events=("csv", "count"),
            mean_abs_delta_psi_deg=("abs_delta_psi_deg", "mean"),
            p95_abs_delta_psi_deg=("abs_delta_psi_deg", percentile_95),
            max_abs_delta_psi_deg=("abs_delta_psi_deg", "max"),
            mean_abs_gamma_deg=("abs_gamma_deg", "mean"),
            p95_abs_gamma_deg=("abs_gamma_deg", percentile_95),
            max_abs_gamma_deg=("abs_gamma_deg", "max"),
        )
        .reset_index()
        .sort_values("vehicle_sort")
    )

    summary.to_csv(outdir / "terminal_angular_diagnostics_summary.csv", index=False)

    # ------------------------------------------------------------
    # LaTeX table üret
    # ------------------------------------------------------------
    tex_lines = []
    tex_lines.append(r"\begin{table}[!htbp]")
    tex_lines.append(r"\centering")
    tex_lines.append(r"\scriptsize")
    tex_lines.append(r"\caption{Diagnostic angular quantities at dwell-confirmed TAEM closure. These quantities are reconstructed at the accepted TAEM event row and are not used as strict-pass variables in the present TAEM-interface claim.}")
    tex_lines.append(r"\label{tab:terminal_angular_diagnostics}")
    tex_lines.append(r"\resizebox{\linewidth}{!}{%")
    tex_lines.append(r"\begin{tabular}{lrrrrrrr}")
    tex_lines.append(r"\hline")
    tex_lines.append(r"Vehicle role & \(N_{\mathrm{evt}}\) & mean \(|\Delta\psi|\) & 95th \(|\Delta\psi|\) & max \(|\Delta\psi|\) & mean \(|\gamma|\) & 95th \(|\gamma|\) & max \(|\gamma|\) \\")
    tex_lines.append(r" &  & \((^\circ)\) & \((^\circ)\) & \((^\circ)\) & \((^\circ)\) & \((^\circ)\) & \((^\circ)\) \\")
    tex_lines.append(r"\hline")

    for _, r in summary.iterrows():
        tex_lines.append(
            f"{r['vehicle_role']} & "
            f"{int(r['n_events'])} & "
            f"{fmt(r['mean_abs_delta_psi_deg'])} & "
            f"{fmt(r['p95_abs_delta_psi_deg'])} & "
            f"{fmt(r['max_abs_delta_psi_deg'])} & "
            f"{fmt(r['mean_abs_gamma_deg'])} & "
            f"{fmt(r['p95_abs_gamma_deg'])} & "
            f"{fmt(r['max_abs_gamma_deg'])} \\\\"
        )

    tex_lines.append(r"\hline")
    tex_lines.append(r"\end{tabular}%")
    tex_lines.append(r"}")
    tex_lines.append(r"\end{table}")

    table_tex = "\n".join(tex_lines)
    table_path = outdir / "terminal_angular_diagnostics_table.tex"
    table_path.write_text(table_tex, encoding="utf-8")

    intro = r"""To further separate the present TAEM-interface claim from a runway-aligned landing claim, the angular variables were also reconstructed at the dwell-confirmed TAEM event rows. These quantities are reported only as diagnostics because the strict TAEM box in Eq.~\eqref{eq:taem_box} is defined in altitude, velocity, and range-to-go. In particular, \(\Delta\psi\) is the line-of-sight heading error relative to the terminal target direction, not a runway-heading error, and \(\gamma\) is the flight-path angle at the accepted TAEM event. The resulting values are summarized in Table~\ref{tab:terminal_angular_diagnostics}."""

    insert_block = intro + "\n\n" + table_tex + "\n"
    insert_path = outdir / "INSERT_AFTER_LOGGING_TABLE_terminal_angular_block.tex"
    insert_path.write_text(insert_block, encoding="utf-8")

    print("")
    print("[OK] Wrote:")
    print(f"  {outdir / 'terminal_angular_events.csv'}")
    print(f"  {outdir / 'terminal_angular_diagnostics_summary.csv'}")
    print(f"  {table_path}")
    print(f"  {insert_path}")
    print("")
    print("[SUMMARY]")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
'@

Set-Content -LiteralPath $PyPath -Value $PythonCode -Encoding UTF8
Write-Host "[OK] Python script created:" $PyPath -ForegroundColor Green

# ------------------------------------------------------------
# 2) Table 5 için hazır LaTeX satırları oluştur
# ------------------------------------------------------------
$Table5RequiredRows = @'
Vehicle mass & \(m_i=907.185~\mathrm{kg}\), \(i=1,2,3\) & Common vehicle mass read directly from \texttt{CAVHParams()}. The same value is used for all three role trajectories and is not sampled, estimated, or retuned during validation. It enters the point-mass dynamics in Eq.~\eqref{eq:point_mass_entry_dynamics}. \\

Reference area & \(S_i=0.4839~\mathrm{m^2}\), \(i=1,2,3\) & Common aerodynamic reference area read directly from \texttt{CAVHParams()}. The same value is used for all three role trajectories and is not sampled, estimated, or retuned during validation. It enters the aerodynamic-force calculation in Eq.~\eqref{eq:aero_forces}. \\
'@

$Table5OptionalRow = @'
Vehicle limits and heating-proxy constants & \(\alpha_{\max}=20^\circ\), \(\alpha_{L/D,\max}=10^\circ\), \(\dot Q_{\max}=500\), \(q_{\max}=1.5\times10^{5}~\mathrm{Pa}\), \(n_{\max}=2\), \(k_Q=1.5\times10^{-8}\) & Frozen vehicle-limit and heating-proxy constants read from \texttt{CAVHParams()}. These values are not sampled, estimated, or retuned in the reported validation campaign. \\
'@

Set-Content -LiteralPath (Join-Path $OutDir "LATEX_TABLE5_REPLACE_mass_area_rows.tex") -Value $Table5RequiredRows -Encoding UTF8
Set-Content -LiteralPath (Join-Path $OutDir "LATEX_TABLE5_OPTIONAL_vehicle_limits_row.tex") -Value $Table5OptionalRow -Encoding UTF8

Write-Host "[OK] Table 5 LaTeX rows created under:" $OutDir -ForegroundColor Green
Write-Host ""

# ------------------------------------------------------------
# 3) Final CSV klasörü buldur
# ------------------------------------------------------------
Write-Host "Scanning CSV directories..." -ForegroundColor Cyan

$CsvFiles = Get-ChildItem -Path $Root -Recurse -Filter "*.csv" -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -notmatch "terminal_angular_diagnostics" -and
        $_.FullName -notmatch "\\report\\" -and
        $_.FullName -notmatch "\\plots" -and
        $_.Length -gt 1000
    }

$Candidates = $CsvFiles |
    Group-Object DirectoryName |
    Sort-Object Count -Descending |
    Select-Object -First 25

if ($Candidates.Count -eq 0) {
    Write-Host "No CSV candidate directories found." -ForegroundColor Red
    Write-Host "You can still run manually:"
    Write-Host "python .\make_terminal_angular_diagnostics.py --glob `"PATH\TO\FINAL50\*.csv`" --outdir `"$OutDir`" --idcol mis_id"
    exit 1
}

Write-Host ""
Write-Host "Candidate CSV directories:" -ForegroundColor Yellow

for ($i = 0; $i -lt $Candidates.Count; $i++) {
    $n = $i + 1
    $dir = $Candidates[$i].Name
    $count = $Candidates[$i].Count
    Write-Host ("[{0}] count={1}  {2}" -f $n, $count, $dir)
}

Write-Host ""
Write-Host "Final 50 combined CSV dosyalarının olduğu klasörün numarasını gir."
Write-Host "Eğer listede yoksa, doğrudan glob yazabilirsin. Örnek:"
Write-Host ".\outputs\B5D_final_50\*.csv"
Write-Host ""

$Choice = Read-Host "Seçim"

if ($Choice -match '^\d+$') {
    $idx = [int]$Choice - 1
    if ($idx -lt 0 -or $idx -ge $Candidates.Count) {
        throw "Invalid selection number."
    }
    $SelectedDir = $Candidates[$idx].Name
    $CsvGlob = Join-Path $SelectedDir "*.csv"
} else {
    $CsvGlob = $Choice
}

Write-Host ""
Write-Host "Selected CSV glob:" $CsvGlob -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------
# 4) Python analizini çalıştır
# ------------------------------------------------------------
python $PyPath --glob "$CsvGlob" --outdir "$OutDir" --idcol mis_id

Write-Host ""
Write-Host "=== FINISHED ===" -ForegroundColor Green
Write-Host "Generated files:"
Write-Host "  $OutDir\terminal_angular_events.csv"
Write-Host "  $OutDir\terminal_angular_diagnostics_summary.csv"
Write-Host "  $OutDir\terminal_angular_diagnostics_table.tex"
Write-Host "  $OutDir\INSERT_AFTER_LOGGING_TABLE_terminal_angular_block.tex"
Write-Host "  $OutDir\LATEX_TABLE5_REPLACE_mass_area_rows.tex"
Write-Host "  $OutDir\LATEX_TABLE5_OPTIONAL_vehicle_limits_row.tex"
Write-Host ""
Write-Host "Preview summary:"
Import-Csv (Join-Path $OutDir "terminal_angular_diagnostics_summary.csv") | Format-Table -AutoSize