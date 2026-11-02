"""Refresh all inputs and rebuild the forecast.

    python src/run_all.py            refresh + rebuild (local only; commit/push yourself)
    python src/run_all.py --final    the final pre-election run (morning of Nov 3):
                                     refresh + rebuild with a "Final forecast" banner, snapshot the outputs to
                                     data/final/, commit, tag final-forecast-2026, push (Cloudflare redeploys)

1. Re-pull VoteHub polls, Wikipedia pages (House, Senate, redistricting, approval), FRED national + state series.
   Raw files land in data/raw/<source>/<today>/ ; older snapshots are kept.
2. Re-estimate everything, forecast, backtest, write FORECAST.md, build site/.

Safety: refuses to run once polls start closing (23:00 UTC on Nov 3 = 6 pm Eastern). After that, Wikipedia starts
filling in results and the parsers would half-absorb them (e.g. locking "re-elected" House seats). Override with
--allow-after-close only for deliberate post-election work.
"""
import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLLS_CLOSE_UTC = dt.datetime(2026, 11, 3, 23, 0, tzinfo=dt.timezone.utc)
TAG = "final-forecast-2026"
STEPS = [
    ["src/collect/polls.py", "votehub"],
    ["src/collect/wiki.py", "snapshot", "house", "senate", "generic_aggregates"],
    ["src/collect/econ.py", "fred", "state_fred"],
    ["src/collect/history.py", "fred_long"],
    ["src/model/calibrate.py"],
    ["src/model/bias_analysis.py"],
    ["src/model/bias_confidence.py"],
    ["src/model/bias_decay.py"],
    ["src/model/error_structure.py"],
    ["src/model/state_econ.py"],
    ["src/model/prior_weight.py"],
    ["src/model/house_structure.py"],
    ["src/model/poll_settings.py"],
    ["src/model/fundamentals.py"],
    ["src/model/forecast.py"],
    ["src/model/bias_decomposition.py"],
    ["src/model/backtest.py"],
    ["src/model/report.py"],
    ["src/site/build.py"],
]


def git(*args, check=True):
    print("   git", " ".join(args), flush=True)
    return subprocess.run(["git", *args], cwd=ROOT, check=check)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="final pre-election run: banner, snapshot, commit, tag, push")
    ap.add_argument("--allow-after-close", action="store_true", help="run even after polls start closing")
    ap.add_argument("--no-push", action="store_true", help="with --final: commit and tag but don't push")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    if now >= POLLS_CLOSE_UTC and not a.allow_after_close:
        sys.exit(f"Polls started closing at {POLLS_CLOSE_UTC:%Y-%m-%d %H:%M} UTC. Not refreshing: Wikipedia now contains partial "
                 f"results. Use --allow-after-close only for deliberate post-election work.")
    if a.final and subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{TAG}"], cwd=ROOT,
                                  capture_output=True).returncode == 0:
        sys.exit(f"Tag {TAG} already exists: the final forecast has been made. Delete the tag first if you really mean to redo it.")

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if a.final:
        env["FORECAST_FINAL"] = "1"
    for step in STEPS:
        print(">>", " ".join(step), flush=True)
        r = subprocess.run([sys.executable, str(ROOT / step[0]), *step[1:]], cwd=ROOT, env=env)
        if r.returncode:
            sys.exit(f"step failed: {step}")
    print("done -> FORECAST.md, site/")

    if a.final:
        snap = ROOT / "data" / "final"
        if snap.exists():
            shutil.rmtree(snap)
        shutil.copytree(ROOT / "data" / "processed", snap)
        shutil.copy(ROOT / "FORECAST.md", snap / "FORECAST.md")
        (snap / "MADE_AT.txt").write_text(f"{dt.datetime.now().astimezone():%Y-%m-%d %H:%M %Z}\n")
        print(f">> snapshot of the final forecast -> {snap}")
        git("add", "-A")
        git("commit", "-q", "-m", f"Final pre-election forecast ({dt.date.today():%Y-%m-%d})\n\n"
            "Frozen copy of model outputs in data/final/ for post-election scoring.")
        git("tag", "-a", TAG, "-m", "Final pre-election forecast, 2026 midterms")
        if not a.no_push:
            git("push", "origin", "main")
            git("push", "origin", TAG)
            print("pushed: Cloudflare will redeploy in ~1 minute. Check the build started (GitHub commit checks or the dashboard).")


if __name__ == "__main__":
    main()
