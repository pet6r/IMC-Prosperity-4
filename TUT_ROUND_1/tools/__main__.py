"""
Unified CLI for tutorial pipelines, portal log export, and plots.

Run from ``TUT_ROUND_1``:

  python -m tools log-export data/submissions/72618/72618.json -o data/submissions/72618/clean
  python -m tools tutorial-pipeline
  python -m tools tutorial-plot
  python -m tools submission-plot data/submissions/72618/72618.log
  python -m tools benchmark data/submissions/64242/64242.log
  python -m tools plotly
  python -m tools dash
"""

import runpy
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent

COMMANDS: dict[str, str] = {
    "alpha-scan": "alpha_scan.py",
    "log-export": "log_export.py",
    "replay-plot": "replay_plot.py",
    "submission-plot": "submission_plot.py",
    "tutorial-pipeline": "tutorial_pipeline.py",
    "tutorial-plot": "tutorial_plot.py",
    "benchmark": "benchmark.py",
    "plotly": "plotly_dashboard.py",
    "dash": "dash_app.py",
}


def _help() -> str:
    lines = [
        "usage: python -m tools <command> [...]",
        "",
        "commands:",
    ]
    for name in sorted(COMMANDS):
        lines.append(f"  {name}")
    lines += [
        "",
        "Run `python -m tools <command> --help` for each command.",
        "Data layout: data/tutorial/{extracted,clean}/  data/submissions/<id>/",
    ]
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(_help())
        sys.exit(0)

    cmd = sys.argv[1]
    script = COMMANDS.get(cmd)
    if not script:
        print(_help(), file=sys.stderr)
        sys.exit(f"Unknown command: {cmd!r}")

    script_path = _TOOLS_DIR / script
    sys.argv = [str(script_path)] + sys.argv[2:]
    runpy.run_path(str(script_path), run_name="__main__")


if __name__ == "__main__":
    main()
