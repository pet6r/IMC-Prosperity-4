#!/usr/bin/env python3
"""
Alpha signal scanner for Prosperity book snapshots.

Computes predictive signals from order-book data and measures their
correlation with next-tick mid-price movement.  Works on both tutorial
``prices_clean.csv`` and submission ``activities_clean.csv``.

Signals computed
~~~~~~~~~~~~~~~~
1. **L1 imbalance**  bid_vol_1 / (bid_vol_1 + ask_vol_1)
2. **Multi-level pressure** (L1+L2+L3 bid volume share — may invert)
3. **Micro-price**  (bid*ask_vol + ask*bid_vol) / (bid_vol + ask_vol)
4. **Spread → next |Δmid|** (do narrow spreads precede big moves?)
5. **Cross-product lead/lag** (does one product forecast the other?)

Usage
~~~~~
  python -m tools alpha-scan data/tutorial/clean
  python -m tools alpha-scan data/submissions/83991/clean
  python -m tools alpha-scan data/tutorial/clean --product TOMATOES
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


# ── data loading ──────────────────────────────────────────────────────────

def _load(clean_dir: Path) -> pd.DataFrame:
    """Load whichever CSV exists (tutorial or submission layout)."""
    for name in ("prices_clean.csv", "activities_clean.csv"):
        p = clean_dir / name
        if p.exists():
            df = pd.read_csv(p)
            # normalise column name
            if "product" not in df.columns and "symbol" in df.columns:
                df = df.rename(columns={"symbol": "product"})
            # ensure spread exists
            if "spread" not in df.columns:
                df["spread"] = df["ask_price_1"] - df["bid_price_1"]
            # drop rows with empty book / corrupt mid
            before = len(df)
            df = df[df["mid_price"].notna() & (df["mid_price"] > 100)].reset_index(drop=True)
            if before - len(df):
                print(f"  (dropped {before - len(df)} rows with empty/zero book)")
            return df
    raise FileNotFoundError(f"No prices_clean.csv or activities_clean.csv in {clean_dir}")


# ── signal builders ───────────────────────────────────────────────────────

def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Add all signal columns in-place, return the same frame."""
    bv1 = df["bid_volume_1"].astype(float)
    av1 = df["ask_volume_1"].astype(float)
    bp1 = df["bid_price_1"].astype(float)
    ap1 = df["ask_price_1"].astype(float)

    # L1 imbalance: 1 = all bids, 0 = all asks
    total_l1 = bv1 + av1
    df["imbalance_l1"] = np.where(total_l1 > 0, bv1 / total_l1, 0.5)

    # Multi-level (L1+L2+L3) pressure
    bid_deep = bv1.copy()
    ask_deep = av1.copy()
    for lvl in (2, 3):
        bc = f"bid_volume_{lvl}"
        ac = f"ask_volume_{lvl}"
        if bc in df.columns:
            bid_deep = bid_deep + pd.to_numeric(df[bc], errors="coerce").fillna(0)
        if ac in df.columns:
            ask_deep = ask_deep + pd.to_numeric(df[ac], errors="coerce").fillna(0)
    total_deep = bid_deep + ask_deep
    df["pressure_deep"] = np.where(total_deep > 0, bid_deep / total_deep, 0.5)

    # Micro-price (L1 volume-weighted)
    df["micro_price"] = np.where(
        total_l1 > 0,
        (bp1 * av1 + ap1 * bv1) / total_l1,
        df["mid_price"],
    )
    df["micro_dev"] = df["micro_price"] - df["mid_price"]

    # GASP (Global Average Symmetric Price) — full-book volume-matched
    df["gasp"] = df.apply(_compute_gasp_row, axis=1)
    df["gasp_dev"] = df["gasp"] - df["mid_price"]

    return df


def _compute_gasp_row(row: pd.Series) -> float:
    """GASP for one row's L1-L3 book levels."""
    bids: list[tuple[float, float]] = []
    asks: list[tuple[float, float]] = []
    for lvl in (1, 2, 3):
        bp = row.get(f"bid_price_{lvl}")
        bv = row.get(f"bid_volume_{lvl}")
        if pd.notna(bp) and pd.notna(bv) and bv > 0:
            bids.append((float(bp), float(bv)))
        ap = row.get(f"ask_price_{lvl}")
        av = row.get(f"ask_volume_{lvl}")
        if pd.notna(ap) and pd.notna(av) and av > 0:
            asks.append((float(ap), float(av)))
    if not bids or not asks:
        mid = row.get("mid_price")
        return float(mid) if pd.notna(mid) else float("nan")
    # bids sorted best-first (desc), asks sorted best-first (asc)
    bids.sort(key=lambda t: -t[0])
    asks.sort(key=lambda t: t[0])

    numerator = 0.0
    denominator = 0.0
    bid_idx = ask_idx = 0
    bid_rem = bids[0][1]
    ask_rem = asks[0][1]
    while bid_idx < len(bids) and ask_idx < len(asks):
        bp = bids[bid_idx][0]
        ap = asks[ask_idx][0]
        matched = min(bid_rem, ask_rem)
        numerator += matched * (bp + ap)
        denominator += 2 * matched
        bid_rem -= matched
        ask_rem -= matched
        if bid_rem == 0:
            bid_idx += 1
            if bid_idx < len(bids):
                bid_rem = bids[bid_idx][1]
        if ask_rem == 0:
            ask_idx += 1
            if ask_idx < len(asks):
                ask_rem = asks[ask_idx][1]
    return numerator / denominator if denominator > 0 else float("nan")


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Per-product next-tick mid delta (the thing we want to predict)."""
    parts = []
    for _, grp in df.groupby(["day", "product"] if "day" in df.columns else ["product"]):
        g = grp.sort_values("timestamp").copy()
        g["mid_delta"] = g["mid_price"].diff().shift(-1)  # next-tick change
        g["abs_mid_delta"] = g["mid_delta"].abs()
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


# ── analysis helpers ──────────────────────────────────────────────────────

def _corr(x: pd.Series, y: pd.Series) -> float:
    mask = x.notna() & y.notna()
    if mask.sum() < 30:
        return float("nan")
    return float(x[mask].corr(y[mask]))


def _quintile_table(signal: pd.Series, target: pd.Series, label: str) -> str:
    """Bucket signal into quintiles, show mean target per bucket."""
    mask = signal.notna() & target.notna()
    s, t = signal[mask], target[mask]
    if len(s) < 50:
        return "  (too few rows for quintile analysis)\n"
    try:
        buckets = pd.qcut(s.rank(method="first"), 5, labels=["Q1(lo)", "Q2", "Q3", "Q4", "Q5(hi)"])
    except ValueError:
        return "  (not enough unique values to bucket)\n"
    tbl = t.groupby(buckets, observed=True).agg(["mean", "std", "count"])
    lines = [f"  {label} quintiles → mean next-tick Δmid:"]
    for q in tbl.index:
        row = tbl.loc[q]
        lines.append(f"    {q:8s}  mean={row['mean']:+.4f}  std={row['std']:.4f}  n={int(row['count'])}")
    return "\n".join(lines) + "\n"


# ── per-product report ────────────────────────────────────────────────────

def report_product(df: pd.DataFrame, product: str) -> None:
    p = df[df["product"] == product].copy()
    n = len(p)
    valid = p["mid_delta"].notna().sum()
    print(f"\n{'='*60}")
    print(f"  {product}   ({n} ticks, {valid} with next-tick target)")
    print(f"{'='*60}")

    if valid < 50:
        print("  Too few rows for analysis.\n")
        return

    mid = p["mid_price"]
    print(f"\n  Mid: mean={mid.mean():.2f}  std={mid.std():.2f}  "
          f"range=[{mid.min():.1f}, {mid.max():.1f}]")
    print(f"  Spread: mean={p['spread'].mean():.2f}  median={p['spread'].median():.0f}")

    # --- Signal 1: L1 imbalance ---
    c = _corr(p["imbalance_l1"], p["mid_delta"])
    print(f"\n  1. L1 imbalance → next Δmid:  corr = {c:+.4f}")
    print(_quintile_table(p["imbalance_l1"], p["mid_delta"], "imbalance_l1"))

    # --- Signal 2: deep pressure ---
    c = _corr(p["pressure_deep"], p["mid_delta"])
    print(f"  2. Deep pressure (L1-L3) → next Δmid:  corr = {c:+.4f}")
    print(_quintile_table(p["pressure_deep"], p["mid_delta"], "pressure_deep"))

    # --- Signal 3: micro-price deviation ---
    c = _corr(p["micro_dev"], p["mid_delta"])
    print(f"  3. Micro-price dev → next Δmid:  corr = {c:+.4f}")
    print(_quintile_table(p["micro_dev"], p["mid_delta"], "micro_dev"))

    # micro-price stability vs simple mid
    mp_ret = p["micro_price"].diff()
    mid_ret = p["mid_price"].diff()
    print(f"     Return std — micro: {mp_ret.std():.4f}  simple mid: {mid_ret.std():.4f}")

    # --- Signal 3b: GASP deviation ---
    c = _corr(p["gasp_dev"], p["mid_delta"])
    print(f"  3b. GASP dev → next Δmid:  corr = {c:+.4f}")
    print(_quintile_table(p["gasp_dev"], p["mid_delta"], "gasp_dev"))
    g_ret = p["gasp"].diff()
    print(f"     Return std — gasp: {g_ret.std():.4f}  vs mid: {mid_ret.std():.4f}")

    # --- Signal 4: spread → next |Δmid| ---
    c = _corr(p["spread"], p["abs_mid_delta"])
    print(f"\n  4. Spread → next |Δmid|:  corr = {c:+.4f}")
    print(_quintile_table(p["spread"], p["abs_mid_delta"], "spread"))

    # --- Signal 5: lag-1 autocorrelation of mid_delta ---
    mid_d = p.sort_values("timestamp")["mid_delta"].dropna()
    ac1 = float(mid_d.autocorr(lag=1)) if len(mid_d) > 30 else float("nan")
    print(f"  5. Mid-delta autocorr(1):  {ac1:+.4f}")
    if ac1 < -0.2:
        print("     → Strong mean-reversion (negative autocorrelation)")
    elif ac1 > 0.2:
        print("     → Momentum / trending")
    else:
        print("     → Weak / noise")
    print()


# ── cross-product analysis ────────────────────────────────────────────────

def report_cross(df: pd.DataFrame, products: list[str]) -> None:
    if len(products) < 2:
        return
    print(f"\n{'='*60}")
    print(f"  Cross-product lead/lag")
    print(f"{'='*60}\n")

    # build a wide frame: one row per (day, timestamp), columns = product mid_delta
    pivot_cols = ["timestamp"]
    if "day" in df.columns:
        pivot_cols = ["day", "timestamp"]
    wide = df.pivot_table(index=pivot_cols, columns="product", values="mid_delta")

    for i, a in enumerate(products):
        for b in products[i + 1:]:
            if a not in wide.columns or b not in wide.columns:
                continue
            sa = wide[a].dropna()
            sb = wide[b].dropna()
            idx = sa.index.intersection(sb.index)
            if len(idx) < 30:
                continue
            print(f"  {a} vs {b}:")
            for lag in range(-3, 4):
                shifted = sb.shift(lag).loc[idx]
                c = _corr(sa.loc[idx], shifted)
                marker = " ◀" if abs(c) > 0.05 else ""
                print(f"    lag={lag:+d}  corr={c:+.4f}{marker}")
            print()


# ── main ──────────────────────────────────────────────────────────────────

def run(clean_dir: Path, product_filter: str | None = None) -> None:
    df = _load(clean_dir)
    df = add_signals(df)
    df = add_targets(df)

    products = sorted(df["product"].dropna().unique())
    if product_filter:
        products = [p for p in products if p == product_filter]

    src = clean_dir.name
    parent = clean_dir.parent.name
    print(f"Alpha scan: {parent}/{src}  ({len(df)} rows, products: {products})")

    for prod in products:
        report_product(df, prod)

    if not product_filter:
        report_cross(df, products)

    # summary
    print(f"{'='*60}")
    print("  Signal strength ranking (|corr| with next-tick Δmid)")
    print(f"{'='*60}")
    rows = []
    for prod in products:
        p = df[df["product"] == prod]
        for sig_name, sig_col, tgt_col in [
            ("L1 imbalance", "imbalance_l1", "mid_delta"),
            ("Deep pressure", "pressure_deep", "mid_delta"),
            ("Micro-price dev", "micro_dev", "mid_delta"),
            ("GASP dev", "gasp_dev", "mid_delta"),
            ("Spread→|Δ|", "spread", "abs_mid_delta"),
        ]:
            c = _corr(p[sig_col], p[tgt_col])
            rows.append((abs(c), prod, sig_name, c))
    rows.sort(reverse=True)
    for _, prod, sig, c in rows:
        bar = "#" * int(abs(c) * 40)
        print(f"  {prod:12s} {sig:20s}  {c:+.4f}  {bar}")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan book data for alpha signals")
    ap.add_argument("clean_dir", type=Path, help="Directory with prices_clean.csv or activities_clean.csv")
    ap.add_argument("--product", type=str, default=None, help="Filter to one product")
    args = ap.parse_args()
    run(args.clean_dir, args.product)


if __name__ == "__main__":
    main()
