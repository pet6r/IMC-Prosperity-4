#!/usr/bin/env python3
"""
Rich replay visualization for a submission: mid + our trades + position + PnL.

Runs the Rust backtester against a submission .log, collects the trades.csv
and pnl_by_product.csv artifacts, then builds a 3-panel chart per product:
  top:    mid price with our buy (green ▲) and sell (red ▼) markers
  middle: our position over time (shaded 0-line)
  bottom: cumulative PnL for that product

Usage:
  python -m tools replay-plot data/submissions/130772/130772.log
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent


def run_backtester(trader: Path, log: Path, out_root: Path) -> Path:
    repo = _ROOT.parent / "prosperity_rust_backtester"
    binary = repo / "target" / "release" / "rust_backtester"
    if not binary.is_file():
        raise SystemExit(f"backtester not found at {binary}; build it first")
    cmd = [
        str(binary),
        "--trader", str(trader),
        "--dataset", str(log),
        "--persist",
        "--artifact-mode", "full",
        "--output-root", str(out_root),
    ]
    env = os.environ.copy()
    env["PYTHONHOME"] = "/usr"
    subprocess.run(cmd, check=True, env=env, stdout=subprocess.DEVNULL)
    runs = sorted(out_root.glob("backtest-*"))
    if not runs:
        raise SystemExit(f"no run dir under {out_root}")
    return runs[-1]


def load_artifacts(run_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = pd.read_csv(run_dir / "trades.csv", sep=";")
    pnl = pd.read_csv(run_dir / "pnl_by_product.csv", sep=";")
    return trades, pnl


def load_book(log_path: Path) -> pd.DataFrame:
    import json
    from io import StringIO
    data = json.loads(log_path.read_text())
    df = pd.read_csv(StringIO(data["activitiesLog"]), sep=";")
    # drop corrupt rows (mid=0 / NaN book)
    df["mid_price"] = pd.to_numeric(df["mid_price"], errors="coerce")
    return df[df["mid_price"].notna() & (df["mid_price"] > 100)]


def positions_from_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Per-(symbol, timestamp) cumulative position after our trades."""
    parts = []
    for sym, grp in trades.groupby("symbol"):
        g = grp.sort_values("timestamp").copy()
        g["signed"] = g["quantity"]
        g.loc[g["seller"] == "SUBMISSION", "signed"] = -g["quantity"]
        g["position"] = g["signed"].cumsum()
        parts.append(g)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def build_plot(
    book: pd.DataFrame,
    trades: pd.DataFrame,
    pnl: pd.DataFrame,
    out_path: Path,
    title: str,
) -> None:
    products = sorted(book["product"].dropna().unique())
    positions = positions_from_trades(trades)

    # filter spike rows in pnl (empty-book mark-to-market artifacts)
    pnl = pnl.copy()
    pnl["dt"] = pnl["total"].diff().abs()
    pnl.loc[pnl["dt"] > 500, ["total"] + products] = pd.NA
    pnl[["total"] + products] = pnl[["total"] + products].ffill()

    fig, axes = plt.subplots(3, len(products),
                             figsize=(7 * len(products), 9),
                             squeeze=False)

    colors = ["#27ae60", "#c0392b", "#2980b9", "#8e44ad"]

    for col, product in enumerate(products):
        color = colors[col % len(colors)]
        bp = book[book["product"] == product].sort_values("timestamp")
        tr = trades[trades["symbol"] == product] if len(trades) else pd.DataFrame()
        po = positions[positions["symbol"] == product] if len(positions) else pd.DataFrame()

        # --- panel 1: mid + trades ---
        ax = axes[0, col]
        ax.plot(bp["timestamp"], bp["mid_price"], color=color, linewidth=0.9, alpha=0.8, label="mid")
        if len(tr):
            buys = tr[tr["buyer"] == "SUBMISSION"]
            sells = tr[tr["seller"] == "SUBMISSION"]
            if len(buys):
                ax.scatter(buys["timestamp"], buys["price"], marker="^",
                           s=35, c="#27ae60", alpha=0.85, zorder=5,
                           label=f"buy ({len(buys)})", edgecolors="black", linewidths=0.3)
            if len(sells):
                ax.scatter(sells["timestamp"], sells["price"], marker="v",
                           s=35, c="#c0392b", alpha=0.85, zorder=5,
                           label=f"sell ({len(sells)})", edgecolors="black", linewidths=0.3)
        ax.set_title(f"{product}")
        ax.set_ylabel("price")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left", fontsize=8)

        # --- panel 2: position trajectory ---
        ax = axes[1, col]
        if len(po):
            # step-plot between trade events
            ax.step(po["timestamp"], po["position"], where="post",
                    color=color, linewidth=1.2, alpha=0.9)
            ax.fill_between(po["timestamp"], 0, po["position"],
                            step="post", color=color, alpha=0.2)
        ax.axhline(0, color="#555", linewidth=0.6)
        ax.axhline(100, color="#aaa", linestyle="--", linewidth=0.5, label="limit +100")
        ax.axhline(-100, color="#aaa", linestyle="--", linewidth=0.5, label="limit -100")
        ax.set_ylabel("position")
        ax.set_ylim(-110, 110)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper left", fontsize=7)

        # --- panel 3: per-product cumulative PnL ---
        ax = axes[2, col]
        ax.plot(pnl["timestamp"], pnl[product], color=color, linewidth=1.0)
        ax.fill_between(pnl["timestamp"], 0, pnl[product], color=color, alpha=0.15)
        ax.axhline(0, color="#555", linewidth=0.6)
        final = pnl[product].iloc[-1]
        ax.set_title(f"final PnL: {final:.0f}")
        ax.set_ylabel("cumulative PnL")
        ax.set_xlabel("timestamp")
        ax.grid(True, alpha=0.3)

    fig.suptitle(title, fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Wrote {out_path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Rich replay plot: mid, trades, position, PnL")
    ap.add_argument("log_path", type=Path)
    ap.add_argument("--trader", type=Path, default=_ROOT / "trader.py",
                    help="Trader file to replay (default: trader.py)")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    if not args.log_path.is_file():
        raise SystemExit(f"log not found: {args.log_path}")
    if not args.trader.is_file():
        raise SystemExit(f"trader not found: {args.trader}")

    out = args.out if args.out else args.log_path.parent / "replay_plot.png"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_dir = run_backtester(args.trader, args.log_path, tmp_path)
        trades, pnl = load_artifacts(run_dir)

    book = load_book(args.log_path)
    title = f"{args.log_path.stem}: {args.trader.name} replay — PnL={pnl['total'].iloc[-1]:.0f}"
    build_plot(book, trades, pnl, out, title)


if __name__ == "__main__":
    main()
