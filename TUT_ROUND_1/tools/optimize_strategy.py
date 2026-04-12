#!/usr/bin/env python3
"""
Exploratory metrics from log_pipeline outputs to guide parameter tuning.

This does NOT re-simulate the exchange (you need the official backtester or re-upload
for true PnL optimization). It summarizes what happened in one run so you can:
  - see average spreads / mid volatility per product
  - compare ending inventory (from run_summary.json) to limits
  - later: plug a grid search into a real local backtester

Usage:
  python -m tools log-export data/submissions/64102/64102.json -o data/submissions/64102/clean
  python -m tools report data/submissions/64102/clean
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def load_summary(clean_dir: Path) -> dict:
    return json.loads((clean_dir / "run_summary.json").read_text())


def report(clean_dir: Path) -> None:
    summary = load_summary(clean_dir)
    feat = pd.read_csv(clean_dir / "features_long.csv")

    print("=== run_summary ===")
    print(f"profit: {summary.get('profit')}")
    print(f"positions: {summary.get('positions')}")
    print(f"pnl_validation_max_abs_diff: {summary.get('pnl_validation_max_abs_diff')}")

    print("\n=== spread + mid (by product) ===")
    for prod in sorted(feat["product"].unique()):
        sub = feat[feat["product"] == prod]
        print(
            f"{prod}: mid mean={sub['mid_price'].mean():.3f}  "
            f"spread mean={sub['spread'].mean():.3f}  "
            f"spread p90={sub['spread'].quantile(0.9):.3f}"
        )

    print("\n=== hints ===")
    pos = summary.get("positions") or []
    for p in pos:
        if isinstance(p, dict) and p.get("symbol") in ("EMERALDS", "TOMATOES"):
            q = p.get("quantity", 0)
            sym = p.get("symbol")
            if abs(q) >= 18:
                print(f"- {sym} ended near limit (qty={q}): consider stronger inventory skew / flattening.")

    print("\nTo optimize numerically, vary EMERALD_BAND / LIMITS / quote offsets in trader.py")
    print("and re-run on Prosperity, or connect this data to a local matching simulator.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("clean_dir", type=Path, help="Output dir from `python -m tools log-export`")
    args = ap.parse_args()
    report(args.clean_dir)


if __name__ == "__main__":
    main()
