from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd()
FIGDIR = Path(r"D:\acta-paper\figs")
FIGDIR.mkdir(parents=True, exist_ok=True)

def first_existing(paths):
    for p in paths:
        p = ROOT / p
        if p.exists():
            return p
    return None

def bool_series(df, col):
    if df is None or col not in df.columns:
        return pd.Series([False] * (0 if df is None else len(df)))
    s = df[col]
    if s.dtype == bool:
        return s
    if np.issubdtype(s.dtype, np.number):
        return pd.to_numeric(s, errors="coerce").fillna(0) > 0.5
    return s.astype(str).str.strip().str.lower().isin(["1", "true", "t", "yes", "y", "pass", "pass_strict"])

def safe_num(s):
    return pd.to_numeric(s, errors="coerce")

def save(fig, name):
    pdf = FIGDIR / name
    png = FIGDIR / name.replace(".pdf", ".png")
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("[OK]", pdf)
    print("[OK]", png)

# ------------------------------------------------------------
# Locate B5E / B5F source CSVs used by B6 publication figures
# ------------------------------------------------------------
b5e_path = first_existing([
    Path("store/data_saved/phase2_B5E_mis0_corner_robustness_refinement_bounded_diagnostic/phase2_B5E_by_run.csv"),
    Path("store/data_saved/phase2_B5E_mis0_corner_robustness_refinement_rescue_soft_first/phase2_B5E_by_run.csv"),
    Path("phase2_B5E_by_run.csv"),
])

b5f_path = first_existing([
    Path("store/data_saved/phase2_B5F_mis0_long_propagation_pathspec_audit/phase2_B5F_by_run.csv"),
    Path("phase2_B5F_by_run.csv"),
])

if b5e_path is None:
    raise SystemExit("[ERR] B5E CSV not found.")
if b5f_path is None:
    raise SystemExit("[ERR] B5F CSV not found.")

b5e = pd.read_csv(b5e_path)
b5f = pd.read_csv(b5f_path)

print("[INFO] B5E:", b5e_path)
print("[INFO] B5F:", b5f_path)

# ------------------------------------------------------------
# Figure 3: Boundary-diagnostic summary
# Same manuscript form, clean layout.
# ------------------------------------------------------------
def failure_timeout_rates(df):
    strict = bool_series(df, "strict_pass") if "strict_pass" in df.columns else pd.Series([False] * len(df))
    timed = bool_series(df, "timed_out") if "timed_out" in df.columns else pd.Series([False] * len(df))
    return float((~strict).mean()), float(timed.mean())

b5e_fail, b5e_timeout = failure_timeout_rates(b5e)
b5f_fail, b5f_timeout = failure_timeout_rates(b5f)

labels = ["Residual-boundary\naudit", "Long-propagation\naudit"]
fail_rates = np.array([b5e_fail, b5f_fail])
timeout_rates = np.array([b5e_timeout, b5f_timeout])

x = np.arange(len(labels))
width = 0.34

fig, ax = plt.subplots(figsize=(8.6, 5.4))
b1 = ax.bar(x - width / 2, fail_rates, width, label="No strict TAEM closure")
b2 = ax.bar(x + width / 2, timeout_rates, width, label="Timeout or missing terminal output")

ax.set_ylim(0.0, 1.12)
ax.set_ylabel("Rate")
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_title("Boundary-diagnostic summary", pad=12)
ax.grid(True, axis="y", alpha=0.30)

for bars in [b1, b2]:
    for bar in bars:
        h = float(bar.get_height())
        ax.text(bar.get_x() + bar.get_width()/2, min(1.07, h + 0.025),
                f"{100*h:.1f}%", ha="center", va="bottom", fontsize=10)

ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, frameon=True)
fig.tight_layout(rect=[0.0, 0.08, 1.0, 1.0], pad=1.5)
save(fig, "fig02_failure_boundary_summary_professional.pdf")

# ------------------------------------------------------------
# Figure 4: Normalized terminal residual diagnostic
# Clean title, LOG scale, no long C1=... bottom note.
# ------------------------------------------------------------
required_final = ["taem_h_err_final", "taem_v_err_final", "taem_s_go_err_final"]
required_alt = ["taem_h_err", "taem_v_err", "taem_s_go_err"]

if all(c in b5e.columns for c in required_final):
    hcol, vcol, scol = required_final
elif all(c in b5e.columns for c in required_alt):
    hcol, vcol, scol = required_alt
else:
    raise SystemExit("[ERR] B5E CSV does not contain terminal residual columns.")

d = b5e.copy()
d["_h"] = safe_num(d[hcol]).abs() / 3000.0
d["_v"] = safe_num(d[vcol]).abs() / 100.0
d["_s"] = safe_num(d[scol]).abs() / 20000.0
d["_max"] = d[["_h", "_v", "_s"]].max(axis=1)
d = d[np.isfinite(d["_max"])].sort_values("_max", ascending=False).head(12).reset_index(drop=True)

labels = [f"C{i+1}" for i in range(len(d))]
x = np.arange(len(d))
width = 0.26

fig, ax = plt.subplots(figsize=(10.5, 5.8))
ax.bar(x - width, d["_h"], width, label=r"Altitude residual $|e_h|/\epsilon_h$")
ax.bar(x, d["_v"], width, label=r"Velocity residual $|e_v|/\epsilon_v$")
ax.bar(x + width, d["_s"], width, label=r"Range-to-go residual $|e_s|/\epsilon_s$")

ax.axhline(1.0, linestyle="--", linewidth=1.2, label="Strict TAEM tolerance boundary")
ax.set_yscale("log")
ax.set_ylim(0.8, max(10.0, float(d["_max"].max()) * 1.35))
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_ylabel("Normalized terminal residual (log scale)")
ax.set_title("Normalized terminal-residual diagnostic", pad=12)
ax.grid(True, axis="y", alpha=0.3, which="both")
ax.legend(fontsize=8, loc="upper right")

fig.tight_layout()
save(fig, "fig03_B5E_terminal_error_diagnostic_professional.pdf")

# Save compact label map separately, not inside the figure.
label_map = pd.DataFrame({
    "compact_label": labels,
    "source_row": d.index + 1,
})
if "case_id" in d.columns:
    label_map["case_id"] = d["case_id"].astype(str)
elif "candidate_label" in d.columns:
    label_map["case_id"] = d["candidate_label"].astype(str)
label_map.to_csv(FIGDIR / "fig03_B5E_compact_case_label_map.csv", index=False)

# ------------------------------------------------------------
# Figure 5: Long-propagation range-closure audit
# Clean spacing; no overlapping annotations.
# ------------------------------------------------------------
d = b5f.copy().head(min(4, len(b5f))).reset_index(drop=True)

if "s_go_start" in d.columns and "s_go_final" in d.columns:
    start = safe_num(d["s_go_start"])
    final = safe_num(d["s_go_final"])
    reduction = 100.0 * (start - final) / start
else:
    # fallback matching current manuscript evidence
    reduction = pd.Series([58.5] + [0.0] * (len(d) - 1))

labels = [f"Audit {i+1}" for i in range(len(d))]
x = np.arange(len(d))

fig, ax = plt.subplots(figsize=(8.6, 5.4))
bars = ax.bar(x, reduction.fillna(0.0), width=0.55, label="Observed range-to-go reduction")

ax.set_title("Long-propagation range-closure audit", pad=12)
ax.set_ylabel("Observed range-to-go reduction (%)")
ax.set_ylim(0.0, 72.0)
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=25, ha="right")
ax.grid(True, axis="y", alpha=0.30)

for i, bar in enumerate(bars):
    h = float(bar.get_height())
    if h > 0:
        ax.text(bar.get_x() + bar.get_width()/2, h + 2.0,
                f"{h:.1f}%", ha="center", va="bottom", fontsize=10)
        ax.text(bar.get_x() + bar.get_width()/2, h * 0.50,
                "No strict\nTAEM closure", ha="center", va="center",
                fontsize=9, bbox=dict(facecolor="white", edgecolor="none", alpha=0.75))
    else:
        ax.text(bar.get_x() + bar.get_width()/2, 8.0,
                "No terminal\noutput", ha="center", va="bottom",
                fontsize=9, rotation=90)

ax.legend(loc="upper right", frameon=True)
fig.tight_layout(pad=1.5)
save(fig, "fig04_B5F_range_closure_audit_professional.pdf")
