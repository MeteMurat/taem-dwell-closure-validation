import argparse
from pathlib import Path
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs_root", default="store/data_saved/runs")
    ap.add_argument("--out", default="store/data_saved/runs/run_scores_all.csv")
    args = ap.parse_args()

    runs_root = Path(args.runs_root)
    paths = sorted(runs_root.glob("*/run_score.csv"))

    if not paths:
        raise SystemExit(f"[ERR] No run_score.csv under: {runs_root}")

    rows = []
    for p in paths:
        run_id = p.parent.name
        df = pd.read_csv(p, low_memory=False)
        df.insert(0, "run_id", run_id)
        rows.append(df)

    all_df = pd.concat(rows, ignore_index=True)
    all_df.to_csv(args.out, index=False)
    print("[OK] wrote:", args.out)
    print("[OK] runs:", all_df["run_id"].nunique(), "rows:", len(all_df))

if __name__ == "__main__":
    main()