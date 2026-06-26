#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run all (ISOLATE_SWEEP_TARGET, SWEEP_CASE_INDEX) combinations automatically.

What it does:
1) edits multiset.py
2) runs multi_main.py
3) runs the TAEM compare script
4) stores each run's taem_compare_by_vehicle.csv under a unique name/folder
5) writes a manifest CSV summarizing all runs

Designed for Windows/PowerShell usage, but plain Python subprocess underneath.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ISOLATE_RE = re.compile(r"(^\s*ISOLATE_SWEEP_TARGET\s*=\s*)([^#\r\n]+)", re.MULTILINE)
CASE_RE = re.compile(r"(^\s*SWEEP_CASE_INDEX\s*=\s*)([^#\r\n]+)", re.MULTILINE)


@dataclass
class RunResult:
    isolate_target: int
    sweep_case_index: int
    status: str
    run_outdir: str
    csv_input: str
    compare_csv: str
    stdout_log: str
    stderr_log: str
    note: str = ""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", required=True, help="EntryGuidance-master root directory")
    ap.add_argument("--multiset", default="multiset.py", help="multiset.py path relative to project root")
    ap.add_argument("--runner", default="multi_main.py", help="main runner path relative to project root")
    ap.add_argument(
        "--compare-script",
        default="taem_compare_runs_LOGCOMPARE_CLEAN.py",
        help="compare script path relative to project root",
    )
    ap.add_argument(
        "--csv-input",
        default=r"store\data_saved\multiSimulation_case.csv",
        help="simulation CSV path relative to project root",
    )
    ap.add_argument(
        "--outdir",
        default=r"store\data_saved\taem_compare_auto",
        help="output directory relative to project root",
    )
    ap.add_argument("--idcol", default="mis_id")
    ap.add_argument("--targets", nargs="*", type=int, default=[1, 2])
    ap.add_argument("--cases", nargs="*", type=int, default=[0, 1, 2, 3, 4, 5])
    ap.add_argument("--python-exe", default=sys.executable, help="python executable to use")
    ap.add_argument("--keep-backup", action="store_true", help="keep multiset auto backup file")
    return ap.parse_args()


def resolve_existing(project_root: Path, rel_path: str, fallbacks: Iterable[str] = ()) -> Path:
    p = (project_root / rel_path).resolve()
    if p.exists():
        return p
    for fb in fallbacks:
        q = (project_root / fb).resolve()
        if q.exists():
            return q
    raise FileNotFoundError(f"Bulunamadı: {rel_path} (fallbacks={list(fallbacks)})")


def patch_multiset(text: str, isolate_target: int, case_index: int) -> str:
    if not ISOLATE_RE.search(text):
        raise RuntimeError("multiset.py içinde 'ISOLATE_SWEEP_TARGET = ...' bulunamadı.")
    if not CASE_RE.search(text):
        raise RuntimeError("multiset.py içinde 'SWEEP_CASE_INDEX = ...' bulunamadı.")

    text = ISOLATE_RE.sub(rf"\g<1>{isolate_target}", text, count=1)
    text = CASE_RE.sub(rf"\g<1>{case_index}", text, count=1)
    return text


def run_cmd(cmd: list[str], cwd: Path, stdout_path: Path, stderr_path: Path) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )
    stdout_path.write_text(proc.stdout, encoding="utf-8", errors="replace")
    stderr_path.write_text(proc.stderr, encoding="utf-8", errors="replace")
    return proc


def main() -> int:
    args = parse_args()

    project_root = Path(args.project_root).resolve()
    multiset_path = resolve_existing(project_root, args.multiset)
    runner_path = resolve_existing(project_root, args.runner)
    compare_path = resolve_existing(
        project_root,
        args.compare_script,
        fallbacks=("taem_compare_runs.py",),
    )
    csv_input = (project_root / args.csv_input).resolve()
    base_outdir = (project_root / args.outdir).resolve()
    base_outdir.mkdir(parents=True, exist_ok=True)

    original_text = multiset_path.read_text(encoding="utf-8")
    backup_path = multiset_path.with_suffix(multiset_path.suffix + ".auto_sweep_backup")
    backup_path.write_text(original_text, encoding="utf-8")

    manifest: list[RunResult] = []

    try:
        for isolate_target in args.targets:
            for case_index in args.cases:
                run_name = f"target{isolate_target}_case{case_index}"
                run_outdir = base_outdir / run_name
                run_outdir.mkdir(parents=True, exist_ok=True)

                stdout_log = run_outdir / "stdout.log"
                stderr_log = run_outdir / "stderr.log"
                compare_csv = run_outdir / "taem_compare_by_vehicle.csv"

                try:
                    patched = patch_multiset(original_text, isolate_target, case_index)
                    multiset_path.write_text(patched, encoding="utf-8")

                    proc1 = run_cmd(
                        [args.python_exe, str(runner_path)],
                        cwd=project_root,
                        stdout_path=run_outdir / "01_multi_main_stdout.log",
                        stderr_path=run_outdir / "01_multi_main_stderr.log",
                    )
                    if proc1.returncode != 0:
                        manifest.append(
                            RunResult(
                                isolate_target=isolate_target,
                                sweep_case_index=case_index,
                                status="multi_main_failed",
                                run_outdir=str(run_outdir),
                                csv_input=str(csv_input),
                                compare_csv="",
                                stdout_log=str(run_outdir / "01_multi_main_stdout.log"),
                                stderr_log=str(run_outdir / "01_multi_main_stderr.log"),
                                note=f"returncode={proc1.returncode}",
                            )
                        )
                        continue

                    if not csv_input.exists():
                        manifest.append(
                            RunResult(
                                isolate_target=isolate_target,
                                sweep_case_index=case_index,
                                status="missing_sim_csv",
                                run_outdir=str(run_outdir),
                                csv_input=str(csv_input),
                                compare_csv="",
                                stdout_log=str(run_outdir / "01_multi_main_stdout.log"),
                                stderr_log=str(run_outdir / "01_multi_main_stderr.log"),
                                note="multi_main tamamlandı ama beklenen CSV bulunamadı",
                            )
                        )
                        continue

                    shutil.copy2(csv_input, run_outdir / "multiSimulation_case.csv")

                    proc2 = run_cmd(
                        [
                            args.python_exe,
                            str(compare_path),
                            "--inputs",
                            str(csv_input),
                            "--outdir",
                            str(run_outdir),
                            "--idcol",
                            args.idcol,
                        ],
                        cwd=project_root,
                        stdout_path=run_outdir / "02_compare_stdout.log",
                        stderr_path=run_outdir / "02_compare_stderr.log",
                    )
                    if proc2.returncode != 0:
                        manifest.append(
                            RunResult(
                                isolate_target=isolate_target,
                                sweep_case_index=case_index,
                                status="compare_failed",
                                run_outdir=str(run_outdir),
                                csv_input=str(run_outdir / "multiSimulation_case.csv"),
                                compare_csv="",
                                stdout_log=str(run_outdir / "02_compare_stdout.log"),
                                stderr_log=str(run_outdir / "02_compare_stderr.log"),
                                note=f"returncode={proc2.returncode}",
                            )
                        )
                        continue

                    if compare_csv.exists():
                        flat_copy = base_outdir / f"taem_compare_by_vehicle_target{isolate_target}_case{case_index}.csv"
                        shutil.copy2(compare_csv, flat_copy)
                        status = "ok"
                        note = ""
                    else:
                        status = "missing_compare_csv"
                        note = "compare script tamamlandı ama taem_compare_by_vehicle.csv oluşmadı"

                    manifest.append(
                        RunResult(
                            isolate_target=isolate_target,
                            sweep_case_index=case_index,
                            status=status,
                            run_outdir=str(run_outdir),
                            csv_input=str(run_outdir / "multiSimulation_case.csv"),
                            compare_csv=str(compare_csv) if compare_csv.exists() else "",
                            stdout_log=str(run_outdir / "02_compare_stdout.log"),
                            stderr_log=str(run_outdir / "02_compare_stderr.log"),
                            note=note,
                        )
                    )

                except Exception as exc:  # noqa: BLE001
                    manifest.append(
                        RunResult(
                            isolate_target=isolate_target,
                            sweep_case_index=case_index,
                            status="runner_exception",
                            run_outdir=str(run_outdir),
                            csv_input=str(csv_input),
                            compare_csv="",
                            stdout_log="",
                            stderr_log="",
                            note=str(exc),
                        )
                    )

    finally:
        multiset_path.write_text(original_text, encoding="utf-8")
        if not args.keep_backup:
            try:
                backup_path.unlink(missing_ok=True)
            except Exception:
                pass

    manifest_path = base_outdir / "sweep_manifest.csv"
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(RunResult.__dataclass_fields__.keys()))
        writer.writeheader()
        for row in manifest:
            writer.writerow(row.__dict__)

    ok_count = sum(1 for m in manifest if m.status == "ok")
    print(f"[DONE] {ok_count}/{len(manifest)} koşu başarılı.")
    print(f"[DONE] Manifest: {manifest_path}")
    print(f"[DONE] Base outdir: {base_outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
