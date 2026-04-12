#!/usr/bin/env python3
"""
Build an interactive Plotly dashboard from tutorial_clean outputs.

Inputs (from tutorial_csv_pipeline.py):
  - features_by_timestamp.csv
  - flow_by_timestamp.csv
  - trades_enriched.csv

Usage:
  python -m tools plotly
  python -m tools plotly --clean-dir data/tutorial/clean --out data/tutorial/clean/tutorial_dashboard.html
"""

import argparse
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _load(clean_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features = pd.read_csv(clean_dir / "features_by_timestamp.csv")
    flow = pd.read_csv(clean_dir / "flow_by_timestamp.csv")
    trades = pd.read_csv(clean_dir / "trades_enriched.csv")

    for df in (features, flow, trades):
        df["day"] = pd.to_numeric(df["day"], errors="coerce")
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")

    return features, flow, trades


def build_dashboard(
    features: pd.DataFrame,
    flow: pd.DataFrame,
    trades: pd.DataFrame,
    selected_days: list[int] | None = None,
    selected_symbols: list[str] | None = None,
) -> go.Figure:
    if selected_days is not None:
        features = features[features["day"].isin(selected_days)]
        flow = flow[flow["day"].isin(selected_days)]
        trades = trades[trades["day"].isin(selected_days)]
    if selected_symbols is not None:
        features = features[features["symbol"].isin(selected_symbols)]
        flow = flow[flow["symbol"].isin(selected_symbols)]
        trades = trades[trades["symbol"].isin(selected_symbols)]

    fea = features.copy()
    flo = flow.copy()
    tra = trades.copy()

    fea["ts_plot"] = fea["timestamp"]
    flo["ts_plot"] = flo["timestamp"]
    tra["ts_plot"] = tra["timestamp"]

    fig = make_subplots(
        rows=2,
        cols=2,
        subplot_titles=(
            "Mid Price + Trades",
            "Spread",
            "Signed Trade Flow (per tick)",
            "Cumulative Signed Flow",
        ),
        horizontal_spacing=0.08,
        vertical_spacing=0.12,
    )

    color_by_symbol = {"EMERALDS": "#2ca02c", "TOMATOES": "#d62728"}
    trade_color = {"buy": "#1f77b4", "sell": "#ff7f0e", "neutral": "#7f7f7f", "unknown": "#9467bd"}

    combos = (
        fea[["day", "symbol"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["day", "symbol"])
        .itertuples(index=False, name=None)
    )

    for day, symbol in combos:
        key = f"day {int(day)} | {symbol}"
        color = color_by_symbol.get(symbol, "#333333")

        f = fea[(fea["day"] == day) & (fea["symbol"] == symbol)].sort_values("ts_plot")
        fl = flo[(flo["day"] == day) & (flo["symbol"] == symbol)].sort_values("ts_plot")
        t = tra[(tra["day"] == day) & (tra["symbol"] == symbol)].sort_values("ts_plot")

        fig.add_trace(
            go.Scatter(
                x=f["ts_plot"],
                y=f["mid_price"],
                mode="lines",
                name=f"{key} mid",
                line=dict(color=color, width=1.2),
                legendgroup=key,
            ),
            row=1,
            col=1,
        )

        for side in ("buy", "sell"):
            tt = t[t["aggressor_side"] == side]
            if len(tt) == 0:
                continue
            fig.add_trace(
                go.Scatter(
                    x=tt["ts_plot"],
                    y=tt["price"],
                    mode="markers",
                    name=f"{key} trade {side}",
                    marker=dict(size=4, color=trade_color[side], opacity=0.55),
                    legendgroup=key,
                    showlegend=False,
                    hovertemplate="ts=%{x}<br>price=%{y}<br>qty=%{customdata}<extra></extra>",
                    customdata=tt["quantity"],
                ),
                row=1,
                col=1,
            )

        fig.add_trace(
            go.Scatter(
                x=f["ts_plot"],
                y=f["spread"],
                mode="lines",
                name=f"{key} spread",
                line=dict(color=color, width=1.0, dash="dot"),
                legendgroup=key,
                showlegend=False,
            ),
            row=1,
            col=2,
        )

        # Filled disks + discrete y-levels → solid ribbons. Open rings + smaller glyphs stay legible.
        q = fl["signed_qty"].abs()
        max_abs = float(q.max()) if len(q) else 1.0
        if max_abs <= 0:
            max_abs = 1.0
        marker_size = 3.5 + (q / max_abs) * 2.0  # ~3.5–5.5 px
        fig.add_trace(
            go.Scatter(
                x=fl["ts_plot"],
                y=fl["signed_qty"],
                mode="markers",
                name=f"{key} signed flow",
                marker=dict(
                    size=marker_size,
                    sizemode="diameter",
                    sizemin=3,
                    symbol="circle-open",
                    color=color,
                    line=dict(width=1.1, color=color),
                    opacity=0.92,
                ),
                legendgroup=key,
                showlegend=False,
                hovertemplate="ts=%{x}<br>signed qty=%{y}<br>|qty|=%{customdata}<extra></extra>",
                customdata=q,
            ),
            row=2,
            col=1,
        )

        cum = fl[["ts_plot", "signed_qty"]].copy()
        cum["cum_signed_qty"] = cum["signed_qty"].cumsum()
        fig.add_trace(
            go.Scatter(
                x=cum["ts_plot"],
                y=cum["cum_signed_qty"],
                mode="lines",
                name=f"{key} cum flow",
                line=dict(shape="hv", color=color, width=2.6),
                legendgroup=key,
                showlegend=False,
            ),
            row=2,
            col=2,
        )

    title = "Tutorial CSV Dashboard: Price, Spread, and Flow Proxies"

    fig.update_layout(
        template="plotly_white",
        title=title,
        hovermode="x unified",
        height=900,
    )

    x_title = "timestamp"
    fig.update_xaxes(title_text=x_title, row=1, col=1)
    fig.update_xaxes(title_text=x_title, row=1, col=2)
    fig.update_xaxes(title_text=x_title, row=2, col=1)
    fig.update_xaxes(title_text=x_title, row=2, col=2, rangeslider=dict(visible=True))
    fig.update_yaxes(title_text="price", row=1, col=1)
    fig.update_yaxes(title_text="spread", row=1, col=2)
    fig.update_yaxes(title_text="signed qty", row=2, col=1)
    fig.update_yaxes(title_text="cum signed qty", row=2, col=2)

    return fig


def main() -> None:
    ap = argparse.ArgumentParser()
    _tut = Path(__file__).resolve().parent.parent
    _clean = _tut / "data" / "tutorial" / "clean"
    ap.add_argument(
        "--clean-dir",
        type=Path,
        default=_clean,
        help="Directory with features_by_timestamp.csv, flow_by_timestamp.csv, trades_enriched.csv",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=_clean / "tutorial_dashboard.html",
        help="Output HTML path",
    )
    args = ap.parse_args()

    features, flow, trades = _load(args.clean_dir)
    fig = build_dashboard(features, flow, trades)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(args.out), include_plotlyjs="cdn")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
