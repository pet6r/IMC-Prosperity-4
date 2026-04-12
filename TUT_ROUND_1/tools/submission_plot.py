#!/usr/bin/env python3
"""
Build price (and optional trade) charts from a Prosperity *downloaded* log JSON.

The `activitiesLog` field is the same semicolon CSV shape as `prices_round_*.csv`
(day, timestamp, product, book levels, mid_price, profit_and_loss).

Full `.log` downloads may also include `tradeHistory` for scatter overlay; slim `.json`
often has only `activitiesLog`.

Portal stores the submission replay under `day=-1` in the CSV; plots label that row **Submission** (not tutorial day −1).

Usage:
  python -m tools submission-plot data/submissions/64176/64176.log
  python -m tools submission-plot data/submissions/64176/64176.json -o data/submissions/64176/plots_from_log
"""

import argparse
import json
import sys
from io import StringIO
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

NUMERIC_COLS = [
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


def load_export(path: Path) -> dict:
    return json.loads(path.read_text())


def activities_to_dataframe(activities_log: str) -> pd.DataFrame:
    df = pd.read_csv(StringIO(activities_log), sep=";")
    for c in NUMERIC_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def trades_to_dataframe(trade_history: list | None) -> pd.DataFrame | None:
    if not trade_history:
        return None
    return pd.DataFrame(trade_history)


def _day_label_for_plot(day) -> str:
    """Portal uses day=-1 in the file for the submission segment; we do not show '-1' on the figure."""
    if pd.isna(day):
        return "?"
    d = int(day)
    if d == -1:
        return "Submission"
    return f"Day {d}"


def plot(
    prices: pd.DataFrame,
    trades: pd.DataFrame | None,
    out_dir: Path,
    title_prefix: str,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    products = sorted(prices["product"].unique())
    days = sorted(prices["day"].unique())

    color = {p: c for p, c in zip(products, ["#c0392b", "#27ae60", "#2980b9", "#8e44ad"])}
    trade_color = "#2c3e50"

    fig, axes = plt.subplots(len(days), len(products), figsize=(4 + 3 * len(products), 3.5 * len(days)))
    axes = np.atleast_2d(axes)

    for row, day in enumerate(days):
        day_prices = prices[prices["day"] == day]
        for col, product in enumerate(products):
            ax = axes[row, col]
            sub = day_prices[day_prices["product"] == product].sort_values("timestamp")
            ax.plot(
                sub["timestamp"],
                sub["mid_price"],
                color=color.get(product, "#333"),
                linewidth=0.8,
                label="mid_price",
            )

            if trades is not None and len(trades) > 0:
                tt = trades[trades["symbol"] == product]
                if len(tt) > 0:
                    ax.scatter(
                        tt["timestamp"],
                        tt["price"],
                        s=12,
                        c=trade_color,
                        alpha=0.55,
                        zorder=5,
                        label="trade",
                    )

            ax.set_title(f"{_day_label_for_plot(day)} — {product}")
            ax.set_xlabel("timestamp")
            ax.set_ylabel("price")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right", fontsize=8)

    fig.suptitle(
        f"{title_prefix}: mid from activitiesLog" + (" + trades" if trades is not None else "")
    )
    fig.tight_layout()
    main_png = out_dir / "prices_from_log.png"
    fig.savefig(main_png, dpi=150)
    plt.close(fig)
    print(f"Wrote {main_png}")

    # Optional zoom for stable-looking products near round thousands
    em = [p for p in products if "EMERALD" in p.upper()]
    if em:
        p = em[0]
        fig2, axs2 = plt.subplots(1, len(days), figsize=(6 * len(days), 4))
        if len(days) == 1:
            axs2 = [axs2]
        for i, day in enumerate(days):
            sub = prices[(prices["day"] == day) & (prices["product"] == p)].sort_values("timestamp")
            axs2[i].plot(sub["timestamp"], sub["mid_price"], color="#27ae60", linewidth=0.7)
            if trades is not None:
                tt = trades[trades["symbol"] == p]
                if len(tt) > 0:
                    axs2[i].scatter(tt["timestamp"], tt["price"], s=10, c=trade_color, alpha=0.5)
            axs2[i].set_title(f"{p} (zoom) — {_day_label_for_plot(day)}")
            y0, y1 = sub["mid_price"].min(), sub["mid_price"].max()
            pad = max(1.0, (y1 - y0) * 0.5)
            axs2[i].set_ylim(y0 - pad, y1 + pad)
            axs2[i].grid(True, alpha=0.3)
        fig2.suptitle(f"{title_prefix}: {p} mid/trades")
        fig2.tight_layout()
        zpath = out_dir / "emeralds_zoom_from_log.png"
        fig2.savefig(zpath, dpi=150)
        plt.close(fig2)
        print(f"Wrote {zpath}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot prices from downloaded Prosperity log JSON")
    ap.add_argument("log_path", type=Path, help="Path to 64176.log, 64176.json, etc.")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=None,
        help="Output directory for CSVs + PNGs (default: <log_stem>_plots next to file)",
    )
    args = ap.parse_args()

    if not args.log_path.is_file():
        print(f"error: file not found: {args.log_path.resolve()}", file=sys.stderr)
        raise SystemExit(1)

    data = load_export(args.log_path)
    if "activitiesLog" not in data:
        raise SystemExit("No activitiesLog in file — not a Prosperity results export?")

    prices = activities_to_dataframe(data["activitiesLog"])
    trades_df = trades_to_dataframe(data.get("tradeHistory"))

    out = args.out if args.out is not None else args.log_path.parent / f"{args.log_path.stem}_plots"
    out.mkdir(parents=True, exist_ok=True)

    prices.to_csv(out / "prices_from_log.csv", index=False)
    print(f"Wrote {out / 'prices_from_log.csv'} ({len(prices)} rows)")

    if trades_df is not None:
        trades_df.to_csv(out / "trades_from_log.csv", index=False)
        print(f"Wrote {out / 'trades_from_log.csv'} ({len(trades_df)} rows)")
    else:
        print("No tradeHistory in file — price lines only (use full .log for trades).")

    plot(prices, trades_df, out, title_prefix=args.log_path.stem)


if __name__ == "__main__":
    main()
