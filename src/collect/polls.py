"""Polling collectors: VoteHub (2026) and archived 538 files (2018-2024)."""
import sys

from common import fetch

WAYBACK_538 = {
    # file -> wayback timestamp (Feb 2025 snapshots, verified to exist)
    "senate_polls_historical.csv": "20250210111722",
    "house_polls_historical.csv": "20250209145115",
    "generic_ballot_polls_historical.csv": "20250207030755",
    "president_approval_polls_historical.csv": "20250305204636",
    "governor_polls_historical.csv": None,
}
GH = "https://raw.githubusercontent.com/fivethirtyeight/data/master/"


def votehub():
    p = fetch("votehub", "polls.json", "https://api.votehub.com/polls", skip_existing=False)
    print("votehub", p, p.stat().st_size)


def wayback_538():
    import requests
    for f, ts in WAYBACK_538.items():
        if ts is None:
            j = requests.get("https://archive.org/wayback/available",
                             params={"url": f"projects.fivethirtyeight.com/polls/data/{f}", "timestamp": "20250201"},
                             timeout=60).json()
            snap = j["archived_snapshots"].get("closest")
            if not snap:
                print("no snapshot", f)
                continue
            ts = snap["timestamp"]
        url = f"https://web.archive.org/web/{ts}id_/https://projects.fivethirtyeight.com/polls/data/{f}"
        try:
            p = fetch("538_wayback", f, url, timeout=300)
            print("538", f, p.stat().st_size)
        except Exception as e:  # noqa: BLE001
            print("FAILED", f, e)


def github_538():
    for path in ["pollster-ratings/raw_polls.csv", "pollster-ratings/pollster-ratings-combined.csv",
                 "congress-generic-ballot/generic_topline_historical.csv"]:
        p = fetch("538_github", path.split("/")[-1], GH + path)
        print("gh", path, p.stat().st_size)


if __name__ == "__main__":
    which = sys.argv[1:] or ["votehub", "wayback_538", "github_538"]
    for w in which:
        globals()[w]()
