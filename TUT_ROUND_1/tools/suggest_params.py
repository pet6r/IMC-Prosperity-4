#!/usr/bin/env python3
"""
Turn log_pipeline output (or a raw JSON export) into suggested constants for trader.py.

What this can do from *historical book snapshots*:
  - EMERALDS: how far `mid_price` drifts from 10_000 → inform `EMERALD_BAND` / anchor behavior
  - TOMATOES: spread + mid volatility → how "wide" the market is (qualitative)
  - Ending positions from `run_summary.json` → skew / inventory hints

Usage:
  python -m tools log-export data/submissions/64176/64176.json -o data/submissions/64176/clean
  python -m tools suggest data/submissions/64176/clean
"""

import argparse
import json
from pathlib import Path

import pandas as pd


def load_activities(clean_dir: Path | None, json_path: Path | None) -> pd.DataFrame:
    if clean_dir is not None:
        return pd.read_csv(clean_dir / "activities_clean.csv")
    if json_path is not None:
        import json as js
        from io import StringIO

        data = js.loads(json_path.read_text())
        return pd.read_csv(StringIO(data["activitiesLog"]), sep=";")
    raise ValueError("Need --clean or --json")


def main() -> None:
    ap = argparse.ArgumentParser(description="Suggest trader.py params from logs")
    ap.add_argument(
        "clean_dir",
        type=Path,
        nargs="?",
        default=None,
        help="Directory from log_pipeline.py (contains activities_clean.csv, run_summary.json)",
    )
    ap.add_argument("--json", type=Path, dest="json_path", default=None, help="Raw Prosperity JSON instead of clean_dir")
    args = ap.parse_args()

    if args.clean_dir is None and args.json_path is None:
        ap.error("Provide clean_dir or --json")

    df = load_activities(args.clean_dir, args.json_path)
    for c in ("mid_price", "bid_price_1", "ask_price_1"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    summary: dict = {}
    if args.clean_dir is not None and (args.clean_dir / "run_summary.json").exists():
        summary = json.loads((args.clean_dir / "run_summary.json").read_text())

    anchor = 10_000.0

    print("=== Suggested knobs for trader.py (manual review required) ===\n")

    # EMERALDS
    em = df[df["product"] == "EMERALDS"].copy()
    if len(em) > 0:
        dev = (em["mid_price"] - anchor).abs()
        mx = float(dev.max())
        p99 = float(dev.quantile(0.99))
        at_anchor = float((dev < 0.5).mean() * 100.0)
        print("EMERALDS (stable ~10_000)")
        print(
            f"  |mid - {anchor:.0f}|: max={mx:.2f}  p99={p99:.2f}  "
            f"({at_anchor:.0f}% of ticks within ±0.5 of anchor — p95 is often 0 for that reason)"
        )
        print(
            f"  EMERALD_BAND: use ≥ max deviation (~{mx:.1f}) so fair can stay {anchor:.0f} whenever mid is near "
            f"print; current 5.0 covers max {mx:.1f}. Wider band = follow mid for more ticks when it drifts."
        )
        print(f"  EMERALD_ANCHOR: keep {anchor:.0f} unless the brief says otherwise.\n")

    # TOMATOES
    to = df[df["product"] == "TOMATOES"].copy()
    if len(to) > 0:
        to = to.sort_values("timestamp")
        mid = to["mid_price"].astype(float)
        spread = (to["ask_price_1"].astype(float) - to["bid_price_1"].astype(float)).dropna()
        print("TOMATOES (volatile)")
        print(f"  mid: mean={mid.mean():.2f}  std={mid.std():.2f}  spread mean={spread.mean():.2f}")
        print(
            "  Fair value is `_fair_tomatoes` = popular mid — no extra constant yet. "
            "If you add quote skew, use mid std as a scale reference.\n"
        )

    # Positions
    pos = summary.get("positions") or []
    print("Inventory (from run_summary if available)")
    for p in pos:
        if isinstance(p, dict) and p.get("symbol") in ("EMERALDS", "TOMATOES"):
            q = p.get("quantity", 0)
            sym = p["symbol"]
            lim = 20  # match LIMITS in trader.py
            print(f"  {sym}: {q} (limit {lim})")
            if sym == "EMERALDS" and q <= -lim + 2:
                print(
                    "    → Often max short: tighten sells / widen buy bias (e.g. lower min_sell_price skew) "
                    "or reduce size on the sell side in a future edit."
                )
            if sym == "TOMATOES" and abs(q) >= lim - 2:
                print("    → Near limit: consider asymmetric to_buy/to_sell weights by sign(position).")

    print("\n=== Next steps ===")
    print("  1. Edit LIMITS / EMERALD_BAND / (later) quote logic in trader.py.")
    print("  2. Re-upload; compare profit + positions in new download.")
    print("  3. Optional: grid search only works with a local matching simulator or many submissions.")


if __name__ == "__main__":
    main()
