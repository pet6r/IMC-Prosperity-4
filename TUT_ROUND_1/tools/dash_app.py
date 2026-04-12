#!/usr/bin/env python3
"""
Serve the tutorial dashboard as a Dash app with filters.

Usage:
  python -m tools dash
  python -m tools dash --clean-dir data/tutorial/clean --host 127.0.0.1 --port 8050
"""

import argparse
import sys
from pathlib import Path

from dash import Dash, Input, Output, dcc, html

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from plotly_dashboard import _load, build_dashboard


def _day_label(day: int) -> str:
    if day == -1:
        return "Day 1"
    if day == -2:
        return "Day 2"
    return f"Day {day}"


def _layout(days: list[int], symbols: list[str]):
    return html.Div(
        [
            html.H3("Tutorial CSV Dashboard (Dash)"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Label("Days"),
                            dcc.Dropdown(
                                id="days",
                                options=[{"label": _day_label(int(d)), "value": d} for d in days],
                                value=days,
                                multi=True,
                            ),
                        ],
                        style={"flex": "1", "minWidth": "220px"},
                    ),
                    html.Div(
                        [
                            html.Label("Symbols"),
                            dcc.Dropdown(
                                id="symbols",
                                options=[{"label": s, "value": s} for s in symbols],
                                value=symbols,
                                multi=True,
                            ),
                        ],
                        style={"flex": "1", "minWidth": "220px"},
                    ),
                ],
                style={"display": "flex", "gap": "12px", "marginBottom": "12px"},
            ),
            dcc.Graph(id="main-graph", style={"height": "88vh"}),
        ],
        style={"padding": "10px 14px"},
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    _tut = Path(__file__).resolve().parent.parent
    ap.add_argument(
        "--clean-dir",
        type=Path,
        default=_tut / "data" / "tutorial" / "clean",
    )
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    features, flow, trades = _load(args.clean_dir)
    days = sorted(features["day"].dropna().astype(int).unique().tolist())
    symbols = sorted(features["symbol"].dropna().astype(str).unique().tolist())

    app = Dash(__name__)
    app.layout = _layout(days, symbols)

    @app.callback(
        Output("main-graph", "figure"),
        Input("days", "value"),
        Input("symbols", "value"),
    )
    def update(days_value, symbols_value):
        selected_days = [int(x) for x in (days_value or days)]
        selected_symbols = [str(x) for x in (symbols_value or symbols)]
        return build_dashboard(
            features,
            flow,
            trades,
            selected_days=selected_days,
            selected_symbols=selected_symbols,
        )

    print(f"Serving Dash at http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
