#!/usr/bin/env python3
"""
Plot rust_backtester bundle.json (from a run with --persist / full outputs).

Requires: pip install matplotlib

Example:
  python3 scripts/visualize_bundle.py \\
    ../prosperity_rust_backtester/runs/backtest-XXXX/bundle.json \\
    -o ../prosperity_rust_backtester/runs/backtest-XXXX/plots
"""

import argparse
import json
from pathlib import Path


def _best_bid_ask(book: dict) -> tuple[float | None, float | None]:
    bids = book.get("bids") or []
    asks = book.get("asks") or []
    if not bids or not asks:
        return None, None
    bb = max(level["price"] for level in bids)
    ba = min(level["price"] for level in asks)
    return float(bb), float(ba)


def _load_bundle(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _final_pnl_snapshot(timeline: list) -> tuple[float | None, dict[str, float]]:
    """Last tick carries terminal mark-to-market PnL (unaffected by plot stride)."""
    if not timeline:
        return None, {}
    last = timeline[-1]
    total = last.get("pnl_total")
    by_prod = last.get("pnl_by_product") or {}
    by_f = {str(k): float(v) for k, v in by_prod.items()}
    return (float(total) if total is not None else None, by_f)


def _format_pnl_caption(
    total: float | None,
    by_product: dict[str, float],
    short: dict[str, str],
) -> str:
    lines = []
    if total is not None:
        lines.append(f"Final total PnL: {total:,.2f}")
    if by_product:
        parts = [f"{short.get(s, s)} {by_product[s]:,.2f}" for s in sorted(by_product.keys())]
        lines.append("  " + "  ·  ".join(parts))
    return "\n".join(lines) if lines else ""


def main() -> None:
    p = argparse.ArgumentParser(description="Visualize prosperity_rust_backtester bundle.json")
    p.add_argument("bundle", type=Path, help="Path to bundle.json")
    p.add_argument(
        "-o",
        "--out-dir",
        type=Path,
        default=None,
        help="Directory for PNG outputs (default: next to bundle.json)",
    )
    p.add_argument(
        "--stride",
        type=int,
        default=1,
        help="Use every Nth tick for faster plotting on huge timelines (default: 1)",
    )
    args = p.parse_args()

    try:
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise SystemExit("Install matplotlib: pip install matplotlib") from e

    data = _load_bundle(args.bundle)
    timeline = data.get("timeline") or []
    products = data.get("products") or []
    run = data.get("run") or {}
    if not timeline:
        raise SystemExit(
            "bundle has empty timeline — regenerate with: cargo run ... --persist "
            "(log-only runs do not include per-tick book snapshots)."
        )

    out_dir = args.out_dir or args.bundle.parent / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    stride = max(1, args.stride)
    ticks = timeline[::stride]
    ts = [t["timestamp"] for t in ticks]

    short = {"EMERALDS": "EMR", "TOMATOES": "TOM"}
    pnl_final, pnl_by_prod = _final_pnl_snapshot(timeline)
    pnl_caption = _format_pnl_caption(pnl_final, pnl_by_prod, short)

    # --- Figure 1: book / L2 top ---
    n = len(products)
    fig1, axes = plt.subplots(n, 1, figsize=(12, 3.5 * n), sharex=True)
    if n == 1:
        axes = [axes]

    for ax, sym in zip(axes, products, strict=True):
        mids, bbs, bas, spreads = [], [], [], []
        for t in ticks:
            book = (t.get("products") or {}).get(sym) or {}
            bb, ba = _best_bid_ask(book)
            mid = book.get("mid_price")
            if mid is None and bb is not None and ba is not None:
                mid = (bb + ba) / 2.0
            mids.append(mid)
            bbs.append(bb)
            bas.append(ba)
            if bb is not None and ba is not None:
                spreads.append(ba - bb)
            else:
                spreads.append(float("nan"))

        label = short.get(sym, sym)
        ax.plot(ts, mids, label="mid", color="black", linewidth=0.8)
        ax.plot(ts, bbs, label="best bid", color="green", alpha=0.85, linewidth=0.7)
        ax.plot(ts, bas, label="best ask", color="red", alpha=0.85, linewidth=0.7)
        ax.set_ylabel("price")
        ax.set_title(f"{label} — book (bundle snapshot)")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("timestamp")
    if pnl_caption:
        fig1.suptitle(pnl_caption, fontsize=10, y=1.0)
    fig1.tight_layout()
    if pnl_caption:
        fig1.subplots_adjust(top=0.92)
    p1 = out_dir / "bundle_book_mid_spread.png"
    fig1.savefig(p1, dpi=150)
    plt.close(fig1)

    # --- Spread only (second file for clarity) ---
    fig_sp, axes_sp = plt.subplots(n, 1, figsize=(12, 2.8 * n), sharex=True)
    if n == 1:
        axes_sp = [axes_sp]
    for ax, sym in zip(axes_sp, products, strict=True):
        spreads = []
        for t in ticks:
            book = (t.get("products") or {}).get(sym) or {}
            bb, ba = _best_bid_ask(book)
            if bb is not None and ba is not None:
                spreads.append(ba - bb)
            else:
                spreads.append(float("nan"))
        label = short.get(sym, sym)
        ax.fill_between(ts, spreads, alpha=0.35, color="steelblue")
        ax.plot(ts, spreads, color="steelblue", linewidth=0.6)
        ax.set_ylabel("spread")
        ax.set_title(f"{label} — bid–ask spread")
        ax.grid(True, alpha=0.3)
    axes_sp[-1].set_xlabel("timestamp")
    if pnl_caption:
        fig_sp.suptitle(pnl_caption, fontsize=10, y=1.0)
    fig_sp.tight_layout()
    if pnl_caption:
        fig_sp.subplots_adjust(top=0.90)
    p_sp = out_dir / "bundle_spread.png"
    fig_sp.savefig(p_sp, dpi=150)
    plt.close(fig_sp)

    # --- PnL + positions ---
    pnl_tot = [t.get("pnl_total") for t in ticks]
    fig2, (ax_pnl, ax_pos) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    ax_pnl.plot(ts, pnl_tot, color="darkblue", linewidth=0.9)
    ax_pnl.set_ylabel("total PnL")
    title_pnl = "Mark-to-market PnL"
    if pnl_final is not None:
        title_pnl += f"  —  final {pnl_final:,.2f}"
    ax_pnl.set_title(title_pnl)
    if pnl_caption:
        ax_pnl.text(
            0.02,
            0.98,
            pnl_caption,
            transform=ax_pnl.transAxes,
            va="top",
            ha="left",
            fontsize=9,
            bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "edgecolor": "0.75", "alpha": 0.92},
        )
    ax_pnl.grid(True, alpha=0.3)

    pos_data: dict[str, list[float]] = {sym: [] for sym in products}
    for t in ticks:
        pos = t.get("position") or {}
        for sym in products:
            pos_data[sym].append(float(pos.get(sym, 0)))

    for sym in products:
        ax_pos.plot(ts, pos_data[sym], label=short.get(sym, sym), linewidth=0.8)
    ax_pos.axhline(0, color="gray", linewidth=0.5)
    ax_pos.set_ylabel("position")
    ax_pos.set_xlabel("timestamp")
    ax_pos.legend(loc="upper right", fontsize=8)
    ax_pos.set_title("Inventory")
    ax_pos.grid(True, alpha=0.3)

    run_id = run.get("run_id", "")
    sub = f"run_id={run_id}  |  dataset={run.get('dataset_id', '')}"
    if pnl_final is not None:
        sub += f"  |  final PnL {pnl_final:,.2f}"
    fig2.suptitle(sub, fontsize=9, y=1.02)
    fig2.tight_layout()
    p2 = out_dir / "bundle_pnl_position.png"
    fig2.savefig(p2, dpi=150, bbox_inches="tight")
    plt.close(fig2)

    series = data.get("pnl_series") or []
    if series:
        fig3, ax = plt.subplots(figsize=(12, 4))
        st = [row["timestamp"] for row in series[::stride]]
        tot = [row["total"] for row in series[::stride]]
        ax.plot(st, tot, color="navy", linewidth=0.9)
        ax.set_xlabel("timestamp")
        ax.set_ylabel("total PnL")
        series_final = float(tot[-1]) if tot else None
        amount = pnl_final if pnl_final is not None else series_final
        ax.set_title(f"{amount:,.2f}" if amount is not None else "total PnL", fontsize=14)
        ax.grid(True, alpha=0.3)
        fig3.tight_layout()
        p3 = out_dir / "bundle_pnl_series.png"
        fig3.savefig(p3, dpi=150)
        plt.close(fig3)

    print(f"Wrote: {p1}")
    print(f"Wrote: {p_sp}")
    print(f"Wrote: {p2}")
    if series:
        print(f"Wrote: {p3}")


if __name__ == "__main__":
    main()
