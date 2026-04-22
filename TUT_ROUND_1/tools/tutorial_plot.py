#!/usr/bin/env python3
"""Plot mid prices and trades from Prosperity CSV exports.

Auto-detects the data directory, days, and products from the CSV filenames.
Usage:
  python -m tools tutorial-plot                          # auto-detect layout
  python -m tools tutorial-plot --data path/to/extracted # explicit
"""

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

_ROUND = Path(__file__).resolve().parent.parent

# Default: first data/<set>/extracted dir found.
_candidates = sorted((_ROUND / "data").glob("*/extracted"))
DEFAULT_DATA = _candidates[0] if _candidates else _ROUND / "data" / "tutorial" / "extracted"

OUT = _ROUND / "plots"
OUT.mkdir(exist_ok=True)

PRODUCT_COLORS = [
    "#27ae60", "#c0392b", "#2980b9", "#8e44ad",
    "#e67e22", "#16a085", "#7f8c8d", "#2c3e50",
]
TRADE_COLOR = "#111111"


def _parse_filename(path: Path) -> tuple[int, str] | None:
    """Extract (day, round) from prices_round_X_day_Y.csv."""
    m = re.match(r"prices_round_(-?\d+)_day_(-?\d+)\.csv", path.name)
    if not m:
        return None
    return int(m.group(2)), m.group(1)


def discover(data_dir: Path) -> tuple[list[int], list[str], str]:
    """Find all days and products present in data_dir, plus the round label."""
    days, round_label = [], ""
    products: set[str] = set()
    for p in sorted(data_dir.glob("prices_round_*_day_*.csv")):
        parsed = _parse_filename(p)
        if parsed is None:
            continue
        day, rnd = parsed
        days.append(day)
        round_label = rnd
        df = pd.read_csv(p, sep=";", usecols=["product"])
        products.update(df["product"].dropna().unique())
    return sorted(set(days)), sorted(products), round_label


def load_prices(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";")
    df["mid_price"] = pd.to_numeric(df["mid_price"], errors="coerce")
    # drop corrupt rows (mid=0 / NaN book)
    return df[df["mid_price"].notna() & (df["mid_price"] > 100)]


def load_trades(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";")


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot mid price + trades per product per day")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    days, products, round_label = discover(args.data)
    if not days or not products:
        raise SystemExit(f"No data found in {args.data}")
    print(f"Round {round_label}: days={days}, products={products}")

    colors = {p: PRODUCT_COLORS[i % len(PRODUCT_COLORS)] for i, p in enumerate(products)}

    # --- Figure 1: per-product-per-day mid + trades
    fig, axes = plt.subplots(len(days), len(products),
                             figsize=(5 * len(products), 3.5 * len(days)),
                             squeeze=False)
    for row, day in enumerate(days):
        prices = load_prices(args.data / f"prices_round_{round_label}_day_{day}.csv")
        trades_path = args.data / f"trades_round_{round_label}_day_{day}.csv"
        trades = load_trades(trades_path) if trades_path.exists() else pd.DataFrame()
        for col, product in enumerate(products):
            ax = axes[row, col]
            sub = prices[prices["product"] == product].sort_values("timestamp")
            ax.plot(sub["timestamp"], sub["mid_price"],
                    color=colors[product], linewidth=0.8, alpha=0.9, label="mid")
            if len(trades) > 0:
                tt = trades[trades["symbol"] == product]
                if len(tt) > 0:
                    ax.scatter(tt["timestamp"], tt["price"],
                               s=10, c=TRADE_COLOR, alpha=0.45, zorder=5, label="trade")
            ax.set_title(f"Day {day} — {product}")
            ax.set_xlabel("timestamp")
            ax.set_ylabel("price")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right", fontsize=8)
    fig.suptitle(f"Round {round_label}: mid price (line) and trades (dots)", fontsize=12)
    fig.tight_layout()
    out1 = args.out / f"round_{round_label}_prices_and_trades.png"
    fig.savefig(out1, dpi=150)
    print(f"Wrote {out1}")

    # --- Figure 2: per-product across-day overlay (zoomed y)
    fig2, axes2 = plt.subplots(len(products), 1,
                               figsize=(12, 3 * len(products)),
                               squeeze=False)
    for i, product in enumerate(products):
        ax = axes2[i, 0]
        for day in days:
            prices = load_prices(args.data / f"prices_round_{round_label}_day_{day}.csv")
            sub = prices[prices["product"] == product].sort_values("timestamp")
            # offset x so days are distinguishable: day-2 first, then -1, then 0
            day_offset = (day - min(days)) * 100_000
            ax.plot(sub["timestamp"] + day_offset, sub["mid_price"],
                    linewidth=0.7, alpha=0.85, label=f"day {day}")
        ax.set_title(f"{product} — mid across all days")
        ax.set_xlabel("timestamp (day-offset)")
        ax.set_ylabel("mid price")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)
    fig2.suptitle(f"Round {round_label}: per-product continuous price view", fontsize=12)
    fig2.tight_layout()
    out2 = args.out / f"round_{round_label}_continuous.png"
    fig2.savefig(out2, dpi=150)
    print(f"Wrote {out2}")

    # --- Figure 3: spread distribution per product
    fig3, ax3 = plt.subplots(1, 1, figsize=(10, 4))
    for product in products:
        all_spreads = []
        for day in days:
            prices = load_prices(args.data / f"prices_round_{round_label}_day_{day}.csv")
            sub = prices[prices["product"] == product]
            all_spreads.extend((sub["ask_price_1"] - sub["bid_price_1"]).dropna().tolist())
        ax3.hist(all_spreads, bins=30, alpha=0.5, label=product, color=colors[product])
    ax3.set_xlabel("spread (ask_1 - bid_1)")
    ax3.set_ylabel("frequency")
    ax3.set_title(f"Round {round_label}: spread distribution per product")
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    fig3.tight_layout()
    out3 = args.out / f"round_{round_label}_spread_histogram.png"
    fig3.savefig(out3, dpi=150)
    print(f"Wrote {out3}")

    plt.close("all")


if __name__ == "__main__":
    main()
