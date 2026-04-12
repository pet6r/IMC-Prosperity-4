#!/usr/bin/env python3
"""
Benchmark how your posted quotes sit vs the touch (best bid / best ask) each tick.

Uses the full Prosperity **.log** (not the slim JSON): `logs[].lambdaLog` has your
`Logger.flush` orders; `activitiesLog` has the book snapshot.

Definitions (integer ticks):
  bid_off = our_max_buy_price  - best_bid   →  +1 means you quote 1 tick *inside* (above BB).
  ask_off = our_min_sell_price - best_ask   →  -1 means you quote 1 tick *inside* (below BA).

So "penny jumping" toward the mid (common MM) shows up as bid_off >= 1 and ask_off <= -1
when the spread is wide. "Behind" the touch is bid_off < 0 or ask_off > 0.

Usage:
  python -m tools benchmark data/submissions/64242/64242.log
  python -m tools benchmark data/submissions/64242/64242.log --min-spread 12
"""

import argparse
import json
from io import StringIO
from pathlib import Path

import pandas as pd


def load_log(path: Path) -> dict:
    return json.loads(path.read_text())


def activities_df(data: dict) -> pd.DataFrame:
    df = pd.read_csv(StringIO(data["activitiesLog"]), sep=";")
    for c in ("bid_price_1", "ask_price_1"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def parse_orders(orders_raw: list) -> dict[str, tuple[int | None, int | None]]:
    """Map symbol -> (max buy price, min sell price)."""
    by: dict[str, dict[str, list[int]]] = {}
    for row in orders_raw:
        sym, price, qty = row[0], int(row[1]), int(row[2])
        by.setdefault(sym, {"buys": [], "sells": []})
        if qty > 0:
            by[sym]["buys"].append(price)
        elif qty < 0:
            by[sym]["sells"].append(price)
    out: dict[str, tuple[int | None, int | None]] = {}
    for sym, d in by.items():
        ob = max(d["buys"]) if d["buys"] else None
        oa = min(d["sells"]) if d["sells"] else None
        out[sym] = (ob, oa)
    return out


def build_frame(data: dict) -> pd.DataFrame:
    acts = activities_df(data)
    rows: list[dict] = []
    for entry in data.get("logs") or []:
        ts = entry.get("timestamp")
        raw = entry.get("lambdaLog")
        if not raw or not isinstance(raw, str):
            continue
        try:
            lam = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(lam, list) or len(lam) < 2:
            continue
        orders_raw = lam[1]
        if not orders_raw:
            continue
        our = parse_orders(orders_raw)
        sub = acts[acts["timestamp"] == ts]
        for _, r in sub.iterrows():
            p = r["product"]
            if p not in our:
                continue
            bb, ba = r["bid_price_1"], r["ask_price_1"]
            ob, oa = our[p]
            if ob is None or oa is None or pd.isna(bb) or pd.isna(ba):
                continue
            spread = int(ba - bb)
            rows.append(
                {
                    "product": p,
                    "timestamp": int(ts),
                    "spread": spread,
                    "best_bid": int(bb),
                    "best_ask": int(ba),
                    "our_bid": ob,
                    "our_ask": oa,
                    "bid_off": int(ob - bb),
                    "ask_off": int(oa - ba),
                    "quoted_width": int(oa - ob),
                }
            )
    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame, min_spread: int | None) -> None:
    if df.empty:
        print("No rows — need a full .log with logs[].lambdaLog and activitiesLog.")
        return
    tag = f" (spread >= {min_spread})" if min_spread is not None else ""
    if min_spread is not None:
        df = df[df["spread"] >= min_spread]
    if df.empty:
        print(f"No rows after filter{tag}.")
        return

    print(f"=== Penny jump vs touch{tag} ===")
    print(f"Ticks (rows): {len(df)}  products: {sorted(df['product'].unique())}\n")

    for prod in sorted(df["product"].unique()):
        s = df[df["product"] == prod]
        n = len(s)
        print(f"--- {prod} (n={n}) ---")
        print(
            f"spread: mean={s['spread'].mean():.2f}  p50={s['spread'].median():.0f}  "
            f"quoted_width mean={s['quoted_width'].mean():.2f}"
        )

        def pct(cond: pd.Series) -> float:
            return 100.0 * float(cond.sum()) / float(n)

        # Touch vs inside vs behind (bid side)
        print("bid_off = our_bid - best_bid:")
        print(
            f"  at touch (0): {pct(s['bid_off'] == 0):.1f}%   "
            f"inside (+1): {pct(s['bid_off'] == 1):.1f}%   "
            f"inside (+2+): {pct(s['bid_off'] >= 2):.1f}%   "
            f"behind (<0): {pct(s['bid_off'] < 0):.1f}%"
        )
        print("ask_off = our_ask - best_ask:")
        print(
            f"  at touch (0): {pct(s['ask_off'] == 0):.1f}%   "
            f"inside (-1): {pct(s['ask_off'] == -1):.1f}%   "
            f"inside (-2-): {pct(s['ask_off'] <= -2):.1f}%   "
            f"behind (>0): {pct(s['ask_off'] > 0):.1f}%"
        )

        vc = s["bid_off"].value_counts().sort_index()
        vc2 = s["ask_off"].value_counts().sort_index()
        bd = {int(k): int(v) for k, v in vc.items()}
        ad = {int(k): int(v) for k, v in vc2.items()}
        print(f"  bid_off counts: {bd}")
        print(f"  ask_off counts: {ad}")
        print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark quote placement vs touch from a .log export")
    ap.add_argument("log_path", type=Path, help="Path to e.g. logs_64242/64242.log")
    ap.add_argument(
        "--min-spread",
        type=int,
        default=None,
        metavar="N",
        help="Only rows where (best_ask - best_bid) >= N (drops tight/spread-collapse ticks)",
    )
    args = ap.parse_args()

    data = load_log(args.log_path)
    df = build_frame(data)
    summarize(df, args.min_spread)


if __name__ == "__main__":
    main()
