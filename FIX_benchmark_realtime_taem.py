# -*- coding: utf-8 -*-
from pathlib import Path
import re

p = Path("benchmark_realtime_taem.py")
txt = p.read_text(encoding="utf-8")

start = txt.find("def write_latex_and_text(summary: dict, outdir: Path):")
end = txt.find("\ndef main():", start)

if start < 0 or end < 0:
    raise SystemExit("[ERR] Could not locate write_latex_and_text() block.")

new_func = r'''
def write_latex_and_text(summary: dict, outdir: Path):
    table_path = outdir / "TABLE_computational_burden.tex"
    text_path = outdir / "INSERT_ComputationalBurdenSection.tex"

    sim = summary.get("simulation", {})
    post = summary.get("postprocess", {})

    sim_wall_med = sim.get("wall_s_median", np.nan)
    sim_rtf_med = sim.get("real_time_factor_median", np.nan)
    sim_ms_row_med = sim.get("ms_per_logged_row_median", np.nan)
    sim_rows_med = sim.get("row_count_median", np.nan)
    sim_span_med = sim.get("sim_span_max_s_median", np.nan)

    post_files = post.get("n_files", np.nan)
    post_rows = post.get("n_rows_total", np.nan)
    post_proc_s = post.get("processing_excluding_io_s_total", np.nan)
    post_us_row = post.get("us_per_row_excluding_io_weighted", np.nan)
    post_rows_per_s = post.get("rows_per_s_excluding_io_weighted", np.nan)
    post_total_s = post.get("total_including_io_s_total", np.nan)

    table_lines = []
    table_lines.append(r"\begin{table}[pos=htbp]")
    table_lines.append(r"\centering")
    table_lines.append(r"\scriptsize")
    table_lines.append(r"\caption{Computational-burden audit for the guidance--logging--TAEM event-detection workflow. The timing values are hardware- and implementation-dependent and are reported as a reproducibility audit rather than as embedded-flight certification.}")
    table_lines.append(r"\label{tab:computational_burden_audit}")
    table_lines.append(r"\begin{tabular}{lll}")
    table_lines.append(r"\hline")
    table_lines.append(r"Audit item & Measured value & Interpretation \\")
    table_lines.append(r"\hline")
    table_lines.append("End-to-end three-role simulation wall time & " + fmt_float(sim_wall_med, 3) + r" s & Median wall-clock time for the timed execution command. \\")
    table_lines.append("Simulated trajectory time span & " + fmt_float(sim_span_med, 3) + r" s & Maximum logged simulated-time span in the generated run. \\")
    table_lines.append("Real-time factor & " + fmt_float(sim_rtf_med, 2) + r" & Simulated-time span divided by wall-clock time. \\")
    table_lines.append("Logged samples per timed simulation & " + fmt_float(sim_rows_med, 0) + r" & Number of saved trajectory rows in the timed output. \\")
    table_lines.append("Wall time per logged sample & " + fmt_float(sim_ms_row_med, 4) + r" ms & End-to-end simulation wall time normalized by saved rows. \\")
    table_lines.append("CSV files replayed for event audit & " + fmt_float(post_files, 0) + r" & Existing final-campaign logs used for event-detection timing. \\")
    table_lines.append("Logged rows replayed for event audit & " + fmt_float(post_rows, 0) + r" & Total rows processed by the dwell/event replay audit. \\")
    table_lines.append("Dwell/event replay time excluding CSV I/O & " + fmt_float(post_proc_s, 6) + r" s & Time for in-box reconstruction and dwell replay only. \\")
    table_lines.append("Dwell/event replay cost per row & " + fmt_float(post_us_row, 3) + r" $\mu$s/row & Per-row post-processing overhead of the event detector. \\")
    table_lines.append("Dwell/event replay throughput & " + fmt_float(post_rows_per_s, 0) + r" rows/s & Logged-row processing throughput excluding CSV I/O. \\")
    table_lines.append("Total replay time including CSV I/O & " + fmt_float(post_total_s, 3) + r" s & End-to-end log-reading plus event-replay time. \\")
    table_lines.append(r"\hline")
    table_lines.append(r"\end{tabular}")
    table_lines.append(r"\end{table}")
    table = "\n".join(table_lines)

    text_lines = []
    text_lines.append(r"\subsection{Computational-burden and real-time audit}")
    text_lines.append(r"\label{subsec:computational_burden_audit}")
    text_lines.append("")
    text_lines.append("Because the proposed validation layer is intended for online entry-guidance assessment, the computational burden of the guidance--logging--event-detection workflow was audited in addition to the closure statistics. The audit separates two costs. The first is the end-to-end wall-clock time required to execute the three-role guidance and propagation workflow. The second is the cost of reconstructing TAEM box membership and replaying the dwell-confirmed event detector from saved trajectory logs. The latter is the computational overhead added by the proposed validation logic and is distinct from the trajectory propagation itself.")
    text_lines.append("")
    text_lines.append(r"For a run with wall-clock time \(t_{\mathrm{wall}}\), logged simulated-time span \(T_{\mathrm{sim}}\), and \(N_{\mathrm{row}}\) saved trajectory samples, the real-time factor is computed as")
    text_lines.append(r"\[")
    text_lines.append(r"\chi_{\mathrm{RT}}=\frac{T_{\mathrm{sim}}}{t_{\mathrm{wall}}},")
    text_lines.append(r"\]")
    text_lines.append(r"and the end-to-end logged-sample cost is \(1000\,t_{\mathrm{wall}}/N_{\mathrm{row}}\) ms per saved row. For the event-replay audit, the per-row dwell-detection cost is computed from the time required to reconstruct the in-box sequence and update the sample-count dwell latch over all logged rows. The dwell/event replay is a linear pass over the logged samples, with \(O(N_vK)\) complexity for \(N_v\) vehicle roles and \(K\) samples per role; it does not require optimization, root finding, or trajectory repropagation.")
    text_lines.append("")
    text_lines.append("The measured values are summarized in Table~\\ref{tab:computational_burden_audit}. On the tested software and hardware configuration, the timed three-role execution required a median wall-clock time of " + fmt_float(sim_wall_med, 3) + "~s for a logged simulated-time span of " + fmt_float(sim_span_med, 3) + "~s, corresponding to a real-time factor of " + fmt_float(sim_rtf_med, 2) + ". The dwell/event replay over " + fmt_float(post_rows, 0) + " logged rows required " + fmt_float(post_proc_s, 6) + "~s excluding CSV input/output, corresponding to " + fmt_float(post_us_row, 3) + "~\\(\\mu\\)s per row. Thus, the event-detection layer is negligible relative to the trajectory propagation and guidance computation in the present implementation.")
    text_lines.append("")
    text_lines.append("These timings should be interpreted as an implementation-level reproducibility audit, not as certification of a flight processor or hard real-time avionics implementation. The code used in this study is a Python research implementation with CSV logging and diagnostic bookkeeping retained for auditability. Nevertheless, the measured event-detection cost shows that the dwell-confirmed TAEM closure logic itself is computationally light: it requires only component-wise tolerance checks, an integer dwell counter, and a latch update at each logged sample.")
    text = "\n".join(text_lines)

    table_path.write_text(table + "\n", encoding="utf-8")
    text_path.write_text(text + "\n", encoding="utf-8")
'''

backup = p.with_suffix(".py.bak_before_fstring_fix")
backup.write_text(txt, encoding="utf-8")

txt2 = txt[:start] + new_func + txt[end:]
p.write_text(txt2, encoding="utf-8")

print("[OK] patched benchmark_realtime_taem.py")
print("[OK] backup:", backup)