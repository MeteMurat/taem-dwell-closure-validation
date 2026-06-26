import math
import matplotlib.pyplot as plt
import numpy as np

# ------------------------------------------------------------
# Wilson confidence interval
# ------------------------------------------------------------
def wilson_ci(k, n, z=1.959963984540054):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1.0 + (z**2) / n
    center = (p + (z**2) / (2*n)) / denom
    margin = (z / denom) * math.sqrt((p*(1-p)/n) + (z**2)/(4*n**2))
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return lower, upper

# ------------------------------------------------------------
# B5D positive-evidence data ONLY
# ------------------------------------------------------------
labels = [
    "Case-level\nstrict closure",
    "Vehicle-level\nstrict closure"
]

successes = [49, 149]
totals    = [50, 150]

rates = [k/n for k, n in zip(successes, totals)]
cis = [wilson_ci(k, n) for k, n in zip(successes, totals)]

lower_err = [r - ci[0] for r, ci in zip(rates, cis)]
upper_err = [ci[1] - r for r, ci in zip(rates, cis)]

# ------------------------------------------------------------
# Plot
# ------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8.6, 5.8))

x = np.arange(len(labels))
bars = ax.bar(
    x,
    rates,
    yerr=[lower_err, upper_err],
    capsize=6,
    width=0.58
)

# Y-axis: Ã¼st boÅŸluÄŸu artÄ±r
ax.set_ylim(0.0, 1.18)
ax.set_ylabel("Strict closure rate")
ax.set_title("Final sampled validation statistics")
ax.set_xticks(x)
ax.set_xticklabels(labels)

# Referans Ã§izgisi
ax.axhline(1.0, linestyle="--", linewidth=1)

# Grid
ax.grid(True, axis="y", alpha=0.25)

# ------------------------------------------------------------
# Controlled annotation placement
# ------------------------------------------------------------
for bar, k, n, r, ci in zip(bars, successes, totals, rates, cis):
    txt = (
        f"{k}/{n} = {r:.3f}\n"
        f"95% CI: [{ci[0]:.3f}, {ci[1]:.3f}]"
    )

    # YazÄ±yÄ± taÅŸÄ±rmamak iÃ§in sabit kontrollÃ¼ yÃ¼kseklik
    y_text = min(ci[1] + 0.025, 1.105)

    ax.text(
        bar.get_x() + bar.get_width()/2,
        y_text,
        txt,
        ha="center",
        va="bottom",
        fontsize=8.5,
        bbox=dict(boxstyle="round,pad=0.25", facecolor="white", edgecolor="none", alpha=0.9)
    )

plt.tight_layout()

# ------------------------------------------------------------
# Save
# ------------------------------------------------------------
out_pdf = "fig01_phase2_success_rates_professional.pdf"
out_png = "fig01_phase2_success_rates_professional.png"

plt.savefig(out_pdf, bbox_inches="tight")
plt.savefig(out_png, dpi=300, bbox_inches="tight")
plt.close()

print(f"[OK] wrote: {out_pdf}")
print(f"[OK] wrote: {out_png}")
