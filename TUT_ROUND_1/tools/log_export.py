#!/usr/bin/env python3
"""
Load a Prosperity run export (64102.json-style), clean, validate PnL, export CSVs.

Usage:
  python -m tools log-export data/submissions/64102/64102.json -o data/submissions/64102/clean

Outputs:
  - activities_clean.csv       — full book + mid + per-product PnL columns
  - pnl_curve.csv              — timestamp, total_pnl (from graphLog)
  - pnl_by_timestamp.csv       — timestamp, pnl_emeralds, pnl_tomatoes, pnl_sum (from activities)
  - features_by_timestamp.csv  — one row per timestamp: mids, spreads, half-spreads
  - run_summary.json           — profit, status, positions, validation max error vs graph
"""

import argparse
import json
from io import StringIO
from pathlib import Path

import pandas as pd

NUMERIC_ACTIVITY_COLS = [
    "bid_price_1",
    "bid_volume_1",
    "bid_price_2",
    "bid_volume_2",
    "bid_price_3",
    "bid_volume_3",
    "ask_price_1",
    "ask_volume_1",
    "ask_price_2",
    "ask_volume_2",
    "ask_price_3",
    "ask_volume_3",
    "mid_price",
    "profit_and_loss",
]


def load_run_json(path: Path) -> dict:
    return json.loads(path.read_text())


def activities_to_dataframe(activities_log: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(activities_log), sep=";")
    for c in NUMERIC_ACTIVITY_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def graph_to_dataframe(graph_log: str) -> pd.DataFrame:
    return pd.read_csv(StringIO(graph_log), sep=";")


def pnl_wide_by_timestamp(activities: pd.DataFrame) -> pd.DataFrame:
    """One row per timestamp: per-product PnL (last row per product at that ts)."""
    # Two rows per timestamp (one per product); profit_and_loss is per-product contribution
    sub = activities[["timestamp", "product", "profit_and_loss"]].copy()
    wide = sub.pivot_table(
        index="timestamp",
        columns="product",
        values="profit_and_loss",
        aggfunc="last",
    )
    wide = wide.rename(
        columns={
            "EMERALDS": "pnl_emeralds",
            "TOMATOES": "pnl_tomatoes",
        }
    )
    wide["pnl_sum_products"] = wide["pnl_emeralds"] + wide["pnl_tomatoes"]
    wide = wide.reset_index()
    return wide


def validate_pnl(graph: pd.DataFrame, pnl_wide: pd.DataFrame) -> pd.DataFrame:
    """Merge graph total with sum of product PnLs; expect near-zero diff."""
    m = graph.merge(pnl_wide, on="timestamp", how="inner", suffixes=("_graph", ""))
    m["diff"] = m["value"] - m["pnl_sum_products"]
    return m


def features_by_timestamp(activities: pd.DataFrame) -> pd.DataFrame:
    """One row per (timestamp, product) then pivot key mids/spreads — here long format simpler."""
    rows = []
    for _, r in activities.iterrows():
        bid = r.get("bid_price_1")
        ask = r.get("ask_price_1")
        mid = r.get("mid_price")
        spread = None
        if pd.notna(bid) and pd.notna(ask):
            spread = float(ask) - float(bid)
        rows.append(
            {
                "day": r["day"],
                "timestamp": r["timestamp"],
                "product": r["product"],
                "mid_price": mid,
                "best_bid": bid,
                "best_ask": ask,
                "spread": spread,
                "half_spread": spread / 2 if spread is not None else None,
            }
        )
    return pd.DataFrame(rows)


def features_wide_by_timestamp(features_long: pd.DataFrame) -> pd.DataFrame:
    """Single timestamp row with TOMATOES / EMERALDS columns."""
    mids = features_long.pivot_table(
        index="timestamp",
        columns="product",
        values="mid_price",
        aggfunc="last",
    )
    mids.columns = [f"mid_{c.lower()}" for c in mids.columns]
    spr = features_long.pivot_table(
        index="timestamp",
        columns="product",
        values="spread",
        aggfunc="last",
    )
    spr.columns = [f"spread_{c.lower()}" for c in spr.columns]
    out = mids.join(spr, how="outer").reset_index()
    return out


def export_run(data: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    activities = activities_to_dataframe(data["activitiesLog"])
    activities.to_csv(out_dir / "activities_clean.csv", index=False)

    graph = graph_to_dataframe(data["graphLog"])
    graph.to_csv(out_dir / "pnl_curve.csv", index=False)

    pnl_wide = pnl_wide_by_timestamp(activities)
    pnl_wide.to_csv(out_dir / "pnl_by_timestamp.csv", index=False)

    check = validate_pnl(graph, pnl_wide)
    max_abs_diff = float(check["diff"].abs().max()) if len(check) else 0.0

    feat_long = features_by_timestamp(activities)
    feat_long.to_csv(out_dir / "features_long.csv", index=False)
    feat_wide = features_wide_by_timestamp(feat_long)
    feat_wide.to_csv(out_dir / "features_by_timestamp.csv", index=False)

    positions = data.get("positions")
    summary = {
        "round": data.get("round"),
        "status": data.get("status"),
        "profit": data.get("profit"),
        "positions": positions,
        "pnl_validation_max_abs_diff": max_abs_diff,
        "rows_activities": len(activities),
        "rows_graph": len(graph),
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"Wrote CSVs + run_summary.json under {out_dir}")
    print(f"profit={summary['profit']}  PnL check max|graph - sum(products)| = {max_abs_diff:.6g}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse Prosperity JSON log export")
    ap.add_argument("json_path", type=Path, help="Path to e.g. 64102.json")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: <json_stem>_clean next to json)",
    )
    args = ap.parse_args()
    out = args.out if args.out is not None else args.json_path.parent / f"{args.json_path.stem}_clean"
    data = load_run_json(args.json_path)
    export_run(data, out)


if __name__ == "__main__":
    main()
