#!/usr/bin/env python3
"""Plot mid prices and trades from Tutorial Round 1 CSV exports."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

_TUT = Path(__file__).resolve().parent.parent
DATA = _TUT / "data" / "tutorial" / "extracted"
OUT = _TUT / "plots"
OUT.mkdir(exist_ok=True)

DAYS = [
    ("-2", "prices_round_0_day_-2.csv", "trades_round_0_day_-2.csv"),
    ("-1", "prices_round_0_day_-1.csv", "trades_round_0_day_-1.csv"),
]

PRODUCTS = ["TOMATOES", "EMERALDS"]
COLORS = {"TOMATOES": "#c0392b", "EMERALDS": "#27ae60"}
TRADE_COLOR = "#2c3e50"


def load_prices(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";")
    df["mid_price"] = pd.to_numeric(df["mid_price"], errors="coerce")
    return df


def load_trades(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";")


def main() -> None:
    fig, axes = plt.subplots(len(DAYS), len(PRODUCTS), figsize=(12, 7), sharex=False, sharey=False)
    if len(DAYS) == 1:
        axes = axes.reshape(1, -1)

    for row, (day_label, prices_name, trades_name) in enumerate(DAYS):
        prices = load_prices(DATA / prices_name)
        trades = load_trades(DATA / trades_name)

        for col, product in enumerate(PRODUCTS):
            ax = axes[row, col]
            sub = prices[prices["product"] == product].sort_values("timestamp")
            ax.plot(
                sub["timestamp"],
                sub["mid_price"],
                color=COLORS[product],
                linewidth=0.8,
                alpha=0.9,
                label="mid_price",
            )

            tt = trades[trades["symbol"] == product]
            if len(tt) > 0:
                ax.scatter(
                    tt["timestamp"],
                    tt["price"],
                    s=12,
                    c=TRADE_COLOR,
                    alpha=0.55,
                    zorder=5,
                    label="trade",
                )

            ax.set_title(f"Day {day_label} — {product}")
            ax.set_xlabel("timestamp")
            ax.set_ylabel("price")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right", fontsize=8)

    fig.suptitle("Tutorial Round 0: mid price (line) and trades (dots)", fontsize=12)
    fig.tight_layout()
    out_path = OUT / "prices_and_trades.png"
    fig.savefig(out_path, dpi=150)
    print(f"Wrote {out_path}")

    # Second figure: EMERALDS y-axis zoom (stable asset)
    fig2, axes2 = plt.subplots(1, 2, figsize=(12, 4))
    for ax, (day_label, prices_name, trades_name) in zip(axes2, DAYS):
        prices = load_prices(DATA / prices_name)
        trades = load_trades(DATA / trades_name)
        sub = prices[prices["product"] == "EMERALDS"].sort_values("timestamp")
        ax.plot(sub["timestamp"], sub["mid_price"], color=COLORS["EMERALDS"], linewidth=0.7)
        tt = trades[trades["symbol"] == "EMERALDS"]
        if len(tt) > 0:
            ax.scatter(tt["timestamp"], tt["price"], s=10, c=TRADE_COLOR, alpha=0.5)
        ax.set_title(f"EMERALDS (zoomed) — Day {day_label}")
        ax.set_xlabel("timestamp")
        ax.set_ylabel("mid / trade price")
        ax.grid(True, alpha=0.3)
        y0, y1 = sub["mid_price"].min(), sub["mid_price"].max()
        pad = max(1.0, (y1 - y0) * 0.5)
        ax.set_ylim(y0 - pad, y1 + pad)
    fig2.suptitle("EMERALDS: mid vs trades (expanded y-axis)")
    fig2.tight_layout()
    out2 = OUT / "emeralds_zoom.png"
    fig2.savefig(out2, dpi=150)
    print(f"Wrote {out2}")

    plt.close("all")


if __name__ == "__main__":
    main()
