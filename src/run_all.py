"""Refresh all inputs and rebuild the forecast.  Usage: python src/run_all.py

1. Re-pull VoteHub polls, Wikipedia pages (House, Senate, redistricting, approval), FRED national + state series.
   Raw files land in data/raw/<source>/<today>/ ; older snapshots are kept.
2. Re-parse race tables, calibrate, forecast (polls-only, polls+fundamentals, bias scenario, sensitivity),
   backtest 2018/2022, and write FORECAST.md.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ["src/collect/polls.py", "votehub"],
    ["src/collect/wiki.py", "snapshot", "house", "senate", "generic_aggregates"],
    ["src/collect/econ.py", "fred", "state_fred"],
    ["src/collect/history.py", "fred_long"],
    ["src/model/calibrate.py"],
    ["src/model/bias_analysis.py"],
    ["src/model/bias_decay.py"],
    ["src/model/error_structure.py"],
    ["src/model/state_econ.py"],
    ["src/model/prior_weight.py"],
    ["src/model/house_structure.py"],
    ["src/model/poll_settings.py"],
    ["src/model/fundamentals.py"],
    ["src/model/forecast.py"],
    ["src/model/backtest.py"],
    ["src/model/report.py"],
    ["src/site/build.py"],
]
for step in STEPS:
    print(">>", " ".join(step), flush=True)
    r = subprocess.run([sys.executable, str(ROOT / step[0]), *step[1:]], cwd=ROOT,
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode:
        sys.exit(f"step failed: {step}")
print("done -> FORECAST.md")
