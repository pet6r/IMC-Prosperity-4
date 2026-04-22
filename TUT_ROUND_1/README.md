# Tutorial Round 1 — trader and tooling

This folder contains the Prosperity **tutorial round** trader (`trader.py`) and small Python helpers. Use it with your own local Prosperity / IMC environment 

## Prerequisites

- **Python** 3.11 or newer  
- **[uv](https://docs.astral.sh/uv/)** (recommended) or another way to install dependencies from `pyproject.toml`

## Setup

From this directory:

```bash
uv sync
```

That creates `.venv/` and installs dependencies from `pyproject.toml`

Activate the environment if your shell does not do it automatically:

```bash
source .venv/bin/activate
```

## Contents


| Path           | Purpose                                        |
| -------------- | ---------------------------------------------- |
| `trader.py`    | `Trader` implementation for the tutorial round |
| `datamodel.py` | Types expected by the engine / backtester      |
| `tools/`       | Unified CLI (`python -m tools <command>`) — pipelines, plots, log export, dashboards |
| `scripts/`     | One-off scripts (`visualize_bundle.py`) |
| `data/tutorial/` | Raw + cleaned tutorial CSVs (`extracted/`, `clean/`) |
| `data/submissions/<id>/` | Per-submission `.json` / `.log` export + derived CSVs |


## Tools CLI

From this folder, run `python -m tools` for the command list. All commands auto-detect the `data/` layout.

| Command | Purpose |
| ------- | ------- |
| `tutorial-pipeline` | Parse `data/tutorial/extracted/*.csv` → `clean/prices_clean.csv`, `trades_clean.csv`, `trades_enriched.csv`, `flow_by_timestamp.csv`, `features_by_timestamp.csv`, `tutorial_summary.json` |
| `tutorial-plot` | Plots from cleaned CSVs: per-day mid+trades grid, continuous per-product overlay, spread histogram (written to `plots/`) |
| `alpha-scan <clean_dir>` | Signal scan (L1 imbalance, deep pressure, micro-price dev, **GASP** dev, spread→|Δ|, autocorr) with quintile tables and cross-product lead/lag |
| `log-export <json>` | Parse Prosperity portal `.json` log → activities/features/PnL CSVs + `run_summary.json` (product-agnostic) |
| `submission-plot <log>` | Plot a submission `.log` mid + own trades |
| `replay-plot <log>` | Run rust backtester against a submission `.log`, then 3-panel per product: mid+trades, position, cumulative PnL. Requires `../prosperity_rust_backtester/target/release/rust_backtester` |
| `benchmark <log>` | Stats on a submission `.log` |
| `plotly` | Standalone HTML dashboard |
| `dash` | Live Dash server dashboard |

Example workflow:

```bash
# 1. clean raw tutorial CSVs
python -m tools tutorial-pipeline

# 2. plot mid + trades per day/product
python -m tools tutorial-plot

# 3. scan alpha signals on cleaned data
python -m tools alpha-scan data/tutorial/clean

# 4. export a submission .json and replay it
python -m tools log-export data/submissions/78239/78239.json
python -m tools replay-plot data/submissions/78239/78239.log
```


## Acknowledgments

This workflow builds on ideas and tooling from the wider Prosperity / IMC community. Thanks to the maintainers and contributors of:

- **[prosperity_rust_backtester](https://github.com/GeyzsoN/prosperity_rust_backtester)** - Rust backtester used locally for fast replay and `bundle.json` outputs.  
- **[imc-prosperity-3-visualizer](https://github.com/jmerle/imc-prosperity-3-visualizer)** - charting / visualization dashboard
- **[Prosperity / IMC documentation](https://imc-prosperity.notion.site/prosperity-4-wiki)** - rules, datamodels, and competition context.
- **[Prosperity 4 Visualizer](https://prosperity.equirag.com/)** - community charting / visualization dashboard

Some of these projects are developed independently; clone them from their own sources if you use them.

## License

Follow the license terms of the Prosperity competition and any third-party code you combine with this trader.