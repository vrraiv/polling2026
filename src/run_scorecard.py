"""Refresh the post-election scorecard: results in, scores out. Never touches the frozen forecast (data/final/,
data/processed/, data/interim/, data/raw/votehub/).

    python src/run_scorecard.py            refresh results and scores (run once a day while counting continues)
    python src/run_scorecard.py --build    ...and rebuild site/ locally to preview the Scorecard tab
    python src/run_scorecard.py --manual   ...and read your own downloads of official results for the close Senate
                                           races no script can reach (data/raw/official_manual/<ST>/<date>/)

Steps:
  1. src/collect/results.py          called winners (Wikipedia overview pages)
  2. src/collect/results_margins.py  vote counts (Wikipedia state pages; California from its Secretary of State)
  3. src/collect/official_senate.py  official counts for the close Senate races where a state publishes them
  4. src/model/scorecard.py          scores -> data/scorecard/scorecard.json
A count only enters the margin scores once it has settled (see results_margins.settledness), so the first run of a
day after a gap is what moves things; running more than once a day changes nothing.
Commit and publish yourself (git), as with the forecast.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = [["src/collect/results.py"], ["src/collect/results_margins.py"], ["src/collect/official_senate.py"], ["src/model/scorecard.py"]]

if __name__ == "__main__":
    steps = [s + (["--manual"] if "--manual" in sys.argv[1:] and s[0].endswith("official_senate.py") else []) for s in STEPS]
    steps += [["src/site/build.py"]] if "--build" in sys.argv[1:] else []
    for s in steps:
        print(f"\n>> {' '.join(s)}", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / s[0]), *s[1:]], cwd=ROOT)
        if r.returncode:
            sys.exit(f"stopped: {s[0]} exited with {r.returncode}")
    print("\nscorecard refreshed: data/scorecard/scorecard.json" + (" and site/ (local preview)" if "--build" in sys.argv[1:] else ""))
