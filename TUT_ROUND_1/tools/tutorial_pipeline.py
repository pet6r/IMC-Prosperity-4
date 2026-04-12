#!/usr/bin/env python3
"""
Pipeline for tutorial day CSVs in extracted/.

Reads all prices_round_0_day_*.csv and trades_round_0_day_*.csv, then writes:
  - prices_clean.csv
  - trades_clean.csv
  - trades_enriched.csv      (joined with touch + mid, plus inferred aggressor side)
  - flow_by_timestamp.csv    (signed flow proxy per timestamp/product/day)
  - features_by_timestamp.csv
  - tutorial_summary.json

Usage:
  python -m tools tutorial-pipeline
  python -m tools tutorial-pipeline --data data/tutorial/extracted --out data/tutorial/clean
"""

import argparse
import json
from pathlib import Path

import pandas as pd

_TUT = Path(__file__).resolve().parent.parent
TUTORIAL_EXTRACTED = _TUT / "data" / "tutorial" / "extracted"
TUTORIAL_CLEAN = _TUT / "data" / "tutorial" / "clean"

PRICE_NUMERIC_COLS = [
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

TRADE_NUMERIC_COLS = ["timestamp", "price", "quantity"]


def _load_prices(data_dir: Path) -> pd.DataFrame:
    files = sorted(data_dir.glob("prices_round_0_day_*.csv"))
    if not files:
        raise FileNotFoundError(f"No prices files found in {data_dir}")

    parts: list[pd.DataFrame] = []
    for path in files:
        df = pd.read_csv(path, sep=";")
        for c in PRICE_NUMERIC_COLS:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["source_file"] = path.name
        df["day"] = pd.to_numeric(df["day"], errors="coerce").astype(int)
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype(int)
        df["spread"] = df["ask_price_1"] - df["bid_price_1"]
        df["half_spread"] = df["spread"] / 2.0
        parts.append(df)
    return pd.concat(parts, ignore_index=True).sort_values(["day", "timestamp", "product"])


def _day_from_name(path: Path) -> int:
    # trades_round_0_day_-2.csv -> -2
    token = path.stem.split("day_")[-1]
    return int(token)


def _load_trades(data_dir: Path) -> pd.DataFrame:
    files = sorted(data_dir.glob("trades_round_0_day_*.csv"))
    if not files:
        raise FileNotFoundError(f"No trades files found in {data_dir}")

    parts: list[pd.DataFrame] = []
    for path in files:
        df = pd.read_csv(path, sep=";")
        for c in TRADE_NUMERIC_COLS:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df["day"] = int(_day_from_name(path))
        df["source_file"] = path.name
        parts.append(df)
    return pd.concat(parts, ignore_index=True).sort_values(["day", "timestamp", "symbol"])


def _enrich_trades_with_book(trades: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """
    Join each trade to nearest previous price snapshot by (day, product/symbol, timestamp).
    Infer aggressor side from touch first, then mid as fallback.
    """
    p = prices[["day", "timestamp", "product", "bid_price_1", "ask_price_1", "mid_price", "spread"]].copy()
    p = p.rename(columns={"product": "symbol"})
    t = trades.copy()

    merged_parts: list[pd.DataFrame] = []
    keys = t[["day", "symbol"]].drop_duplicates()
    for _, key in keys.iterrows():
        day = key["day"]
        symbol = key["symbol"]
        tt = t[(t["day"] == day) & (t["symbol"] == symbol)].sort_values("timestamp")
        pp = p[(p["day"] == day) & (p["symbol"] == symbol)].sort_values("timestamp")
        pp = pp.drop(columns=["day", "symbol"])
        if len(tt) == 0:
            continue
        if len(pp) == 0:
            merged_parts.append(tt.copy())
            continue
        merged_parts.append(
            pd.merge_asof(
                tt,
                pp,
                on="timestamp",
                direction="backward",
                allow_exact_matches=True,
            )
        )
    enriched = pd.concat(merged_parts, ignore_index=True).sort_values(["day", "timestamp", "symbol"])

    def infer_side(row: pd.Series) -> str:
        price = row.get("price")
        bid = row.get("bid_price_1")
        ask = row.get("ask_price_1")
        mid = row.get("mid_price")
        if pd.isna(price) or pd.isna(bid) or pd.isna(ask):
            return "unknown"
        if float(price) >= float(ask):
            return "buy"
        if float(price) <= float(bid):
            return "sell"
        if pd.notna(mid):
            if float(price) > float(mid):
                return "buy"
            if float(price) < float(mid):
                return "sell"
            return "neutral"
        return "neutral"

    enriched["aggressor_side"] = enriched.apply(infer_side, axis=1)
    enriched["signed_qty"] = enriched["quantity"]
    enriched.loc[enriched["aggressor_side"] == "sell", "signed_qty"] *= -1
    enriched.loc[enriched["aggressor_side"].isin(["neutral", "unknown"]), "signed_qty"] = 0
    return enriched


def _flow_by_timestamp(enriched: pd.DataFrame) -> pd.DataFrame:
    out = (
        enriched.groupby(["day", "timestamp", "symbol"], as_index=False)
        .agg(
            trades=("quantity", "count"),
            traded_qty=("quantity", "sum"),
            signed_qty=("signed_qty", "sum"),
            buy_trades=("aggressor_side", lambda s: int((s == "buy").sum())),
            sell_trades=("aggressor_side", lambda s: int((s == "sell").sum())),
            neutral_trades=("aggressor_side", lambda s: int((s == "neutral").sum())),
            unknown_trades=("aggressor_side", lambda s: int((s == "unknown").sum())),
        )
        .sort_values(["day", "timestamp", "symbol"])
    )
    out["net_buy_ratio"] = out["signed_qty"] / out["traded_qty"].replace(0, pd.NA)
    return out


def _features_by_timestamp(prices: pd.DataFrame) -> pd.DataFrame:
    keep = ["day", "timestamp", "product", "mid_price", "bid_price_1", "ask_price_1", "spread", "half_spread"]
    f = prices[keep].copy().rename(columns={"product": "symbol", "bid_price_1": "best_bid", "ask_price_1": "best_ask"})
    return f.sort_values(["day", "timestamp", "symbol"])


def _build_summary(prices: pd.DataFrame, enriched: pd.DataFrame) -> dict:
    summary: dict[str, dict] = {"days": {}, "overall": {}}

    for day in sorted(prices["day"].dropna().astype(int).unique()):
        d_prices = prices[prices["day"] == day]
        d_trades = enriched[enriched["day"] == day]
        day_key = str(day)
        summary["days"][day_key] = {}
        for sym in sorted(d_prices["product"].dropna().unique()):
            p = d_prices[d_prices["product"] == sym]
            t = d_trades[d_trades["symbol"] == sym]
            buy_n = int((t["aggressor_side"] == "buy").sum()) if len(t) else 0
            sell_n = int((t["aggressor_side"] == "sell").sum()) if len(t) else 0
            directional = buy_n + sell_n
            summary["days"][day_key][sym] = {
                "rows_prices": int(len(p)),
                "rows_trades": int(len(t)),
                "mid_mean": float(p["mid_price"].mean()) if len(p) else None,
                "mid_std": float(p["mid_price"].std()) if len(p) else None,
                "spread_mean": float(p["spread"].mean()) if len(p) else None,
                "spread_p90": float(p["spread"].quantile(0.9)) if len(p) else None,
                "trade_qty_total": float(t["quantity"].sum()) if len(t) else 0.0,
                "signed_qty_total": float(t["signed_qty"].sum()) if len(t) else 0.0,
                "buy_trade_share": (buy_n / directional) if directional > 0 else None,
                "sell_trade_share": (sell_n / directional) if directional > 0 else None,
            }

    summary["overall"]["days"] = sorted(prices["day"].dropna().astype(int).unique().tolist())
    summary["overall"]["products"] = sorted(prices["product"].dropna().unique().tolist())
    summary["overall"]["rows_prices"] = int(len(prices))
    summary["overall"]["rows_trades"] = int(len(enriched))
    return summary


def run(data_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    prices = _load_prices(data_dir)
    trades = _load_trades(data_dir)
    enriched = _enrich_trades_with_book(trades, prices)
    flow = _flow_by_timestamp(enriched)
    features = _features_by_timestamp(prices)
    summary = _build_summary(prices, enriched)

    prices.to_csv(out_dir / "prices_clean.csv", index=False)
    trades.to_csv(out_dir / "trades_clean.csv", index=False)
    enriched.to_csv(out_dir / "trades_enriched.csv", index=False)
    flow.to_csv(out_dir / "flow_by_timestamp.csv", index=False)
    features.to_csv(out_dir / "features_by_timestamp.csv", index=False)
    (out_dir / "tutorial_summary.json").write_text(json.dumps(summary, indent=2))

    print(f"Wrote tutorial outputs under {out_dir}")
    print(f"prices rows={len(prices)} trades rows={len(trades)} enriched rows={len(enriched)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pipeline for tutorial extracted CSVs")
    ap.add_argument("--data", type=Path, default=TUTORIAL_EXTRACTED)
    ap.add_argument("--out", type=Path, default=TUTORIAL_CLEAN)
    args = ap.parse_args()
    run(args.data, args.out)


if __name__ == "__main__":
    main()
