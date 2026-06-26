from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

FIGDIR = Path(r"D:\acta-paper\figs")
FIGDIR.mkdir(parents=True, exist_ok=True)

def save_both(fig, name_pdf):
    pdf = FIGDIR / name_pdf
    png = FIGDIR / name_pdf.replace(".pdf", ".png")
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[OK] wrote {pdf}")
    print(f"[OK] wrote {png}")

# ============================================================
# Figure 2: final sampled validation statistics
# Same form: two bars + Wilson interval annotations.
# ============================================================
rates = np.array([49/50, 149/150], dtype=float)
ci_low = np.array([0.895, 0.963], dtype=float)
ci_high = np.array([0.996, 0.999], dtype=float)

x = np.arange(2)
fig, ax = plt.subplots(figsize=(6.2, 4.2))
bars = ax.bar(x, rates, width=0.55)

yerr = np.vstack([rates - ci_low, ci_high - rates])
ax.errorbar(x, rates, yerr=yerr, fmt="none", capsize=4, linewidth=1.1)

ax.set_title("Final sampled validation statistics")
ax.set_ylabel("Strict closure rate")
ax.set_ylim(0.0, 1.08)
ax.set_xticks(x)
ax.set_xticklabels(["Case-level\nstrict closure", "Vehicle-level\nstrict closure"])

texts = [
    "49/50 = 0.980\n95% CI: [0.895, 0.996]",
    "149/150 = 0.993\n95% CI: [0.963, 0.999]",
]
for i, txt in enumerate(texts):
    ax.text(x[i], min(1.055, rates[i] + 0.035), txt,
            ha="center", va="bottom", fontsize=9)

ax.grid(True, axis="y", alpha=0.3)
fig.tight_layout()
save_both(fig, "fig01_phase2_success_rates_professional.pdf")

# ============================================================
# Figure 3: boundary-diagnostic summary
# Same form: grouped bars, two audit classes, two rates.
# ============================================================
labels = ["Residual-boundary\naudit", "Long-propagation\naudit"]
x = np.arange(len(labels))
width = 0.34

no_strict = np.array([1.00, 1.00])
timeout = np.array([0.00, 0.75])

fig, ax = plt.subplots(figsize=(7.2, 4.3))
b1 = ax.bar(x - width/2, no_strict, width, label="No strict TAEM closure")
b2 = ax.bar(x + width/2, timeout, width, label="Timeout or missing terminal output")

ax.set_title("Boundary-diagnostic summary")
ax.set_ylabel("Rate")
ax.set_ylim(0.0, 1.12)
ax.set_xticks(x)
ax.set_xticklabels(labels)

for bars in (b1, b2):
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h + 0.025,
                f"{100*h:.1f}%", ha="center", va="bottom", fontsize=9)

ax.grid(True, axis="y", alpha=0.3)
ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.24), ncol=2, frameon=True)
fig.tight_layout()
save_both(fig, "fig02_failure_boundary_summary_professional.pdf")

# ============================================================
# Figure 5: long-propagation range-closure audit
# Same form: 4 audits, observed range-reduction bar + missing-output text.
# ============================================================
labels = ["Audit 1", "Audit 2", "Audit 3", "Audit 4"]
x = np.arange(len(labels))
reduction = np.array([58.5, 0.0, 0.0, 0.0])

fig, ax = plt.subplots(figsize=(7.2, 4.3))
bars = ax.bar(x, reduction, width=0.55, label="Observed range-to-go reduction")

ax.set_title("Long-propagation range-closure audit")
ax.set_ylabel("Observed range-to-go reduction (%)")
ax.set_ylim(0.0, 70.0)
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=25, ha="right")

ax.text(x[0], reduction[0] + 2.0, "58.5%", ha="center", va="bottom", fontsize=9)
ax.text(x[0], max(4.0, reduction[0] * 0.45), "No strict TAEM closure",
        ha="center", va="center", rotation=90, fontsize=8)

for i in [1, 2, 3]:
    ax.text(x[i], 6.0, "No terminal\noutput",
            ha="center", va="bottom", rotation=90, fontsize=8)

ax.grid(True, axis="y", alpha=0.3)
ax.legend(loc="upper right", frameon=True)
fig.tight_layout()
save_both(fig, "fig04_B5F_range_closure_audit_professional.pdf")
