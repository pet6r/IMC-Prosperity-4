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


## Acknowledgments

This workflow builds on ideas and tooling from the wider Prosperity / IMC community. Thanks to the maintainers and contributors of:

- **[prosperity_rust_backtester](https://github.com/GeyzsoN/prosperity_rust_backtester)** - Rust backtester used locally for fast replay and `bundle.json` outputs.  
- **[imc-prosperity-3-visualizer](https://github.com/jmerle/imc-prosperity-3-visualizer)** - charting / visualization dashboard
- **[Prosperity / IMC documentation](https://imc-prosperity.notion.site/prosperity-4-wiki)** - rules, datamodels, and competition context.
- **[Prosperity 4 Visualizer](https://prosperity.equirag.com/)** - community charting / visualization dashboard

Some of these projects are developed independently; clone them from their own sources if you use them.

## License

Follow the license terms of the Prosperity competition and any third-party code you combine with this trader.