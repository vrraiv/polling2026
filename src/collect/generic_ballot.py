"""National generic-ballot polling average by day, November 1995 to November 2026: the polls of the time, for setting
off-cycle results (House specials, odd-year governor races) against what national polls said when they were held.

Sources (raw files committed under data/raw/):
  - to 2016-11-06: FiveThirtyEight's historical generic-ballot average (538_github/generic_topline_historical.csv,
    CC BY 4.0): its daily Democratic and Republican estimates, as published.
  - 2016-11-07 to 2024-11-05: FiveThirtyEight's generic-ballot poll file (538_wayback/generic_ballot_polls_historical.csv,
    CC BY 4.0).
  - from 2024-11-06: VoteHub's generic-ballot polls (votehub/<latest>/polls.json, CC BY 4.0).
From the two poll files, each day's value is a plain average: the latest poll from each pollster that ended in the
previous 30 days (widened to 60 when fewer than 3 pollsters qualify), one version per poll (likely voters, then
registered voters, then adults), polls sponsored by a party or campaign left out. No house effects or other adjustments.
Margins are two-party: 100 * (D - R) / (D + R).

    python src/collect/generic_ballot.py
Writes data/interim/generic_ballot_daily.csv (date, margin_2p, n_polls, window_days, source).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, latest  # noqa: E402

OUT = ROOT / "data" / "interim" / "generic_ballot_daily.csv"
START_538_POLLS = pd.Timestamp("2016-11-07")
START_VOTEHUB = pd.Timestamp("2024-11-06")
END = pd.Timestamp("2026-11-03")
POP_RANK = {"lv": 0, "rv": 1, "v": 1, "a": 2}
WINDOWS, MIN_POLLSTERS = (30, 60), 3


def two_party(d, r):
    return 100.0 * (d - r) / (d + r)


def topline():
    t = pd.read_csv(latest("538_github", "generic_topline_historical.csv"))
    t = t[t.subgroup == "All polls"]
    out = pd.DataFrame({"date": pd.to_datetime(t.modeldate, format="%m/%d/%Y"),
                        "margin_2p": two_party(t.dem_estimate, t.rep_estimate),
                        "n_polls": np.nan, "window_days": np.nan, "source": "FiveThirtyEight average"})
    return out[out.date < START_538_POLLS].sort_values("date")


def polls_538():
    p = pd.read_csv(latest("538_wayback", "generic_ballot_polls_historical.csv"))
    p = p[p.dem.notna() & p.rep.notna() & p.partisan.isna()].copy()
    p["end"] = pd.to_datetime(p.end_date, format="%m/%d/%y")
    p["rank"] = p.population.str.lower().map(POP_RANK).fillna(3)
    p = p.sort_values(["poll_id", "rank", "question_id"]).drop_duplicates("poll_id")
    return pd.DataFrame({"end": p.end, "pollster": p.pollster, "margin_2p": two_party(p.dem, p.rep)})


def polls_votehub():
    rows = []
    for x in json.loads(latest("votehub", "polls.json").read_text(encoding="utf-8")):
        if x.get("poll_type") != "generic-ballot" or x.get("partisan"):
            continue
        a = {y["choice"]: y["pct"] for y in x["answers"]}
        if "Dem" in a and "Rep" in a:
            rows.append({"end": pd.Timestamp(x["end_date"]), "pollster": x["pollster"],
                         "rank": POP_RANK.get((x.get("population") or "").lower(), 3), "margin_2p": two_party(a["Dem"], a["Rep"])})
    p = pd.DataFrame(rows).sort_values(["pollster", "end", "rank"]).drop_duplicates(["pollster", "end"])
    return p[["end", "pollster", "margin_2p"]]


def daily(polls, start, end, source):
    p = polls.sort_values("end")
    rows = []
    for d in pd.date_range(start, end):
        for win in WINDOWS:
            w = p[(p.end <= d) & (p.end > d - pd.Timedelta(days=win))].drop_duplicates("pollster", keep="last")
            if len(w) >= MIN_POLLSTERS:
                break
        rows.append({"date": d, "margin_2p": float(w.margin_2p.mean()) if len(w) else np.nan, "n_polls": len(w),
                     "window_days": win, "source": source})
    return pd.DataFrame(rows)


def build():
    out = pd.concat([topline(),
                     daily(polls_538(), START_538_POLLS, START_VOTEHUB - pd.Timedelta(days=1), "FiveThirtyEight polls, plain average"),
                     daily(polls_votehub(), START_VOTEHUB, END, "VoteHub polls, plain average")])
    out["date"] = out.date.dt.date.astype(str)
    out.round({"margin_2p": 2}).to_csv(OUT, index=False)
    return out


if __name__ == "__main__":
    o = build()
    print(f"{OUT.relative_to(ROOT).as_posix()}: {len(o)} days, {o.date.iloc[0]} to {o.date.iloc[-1]};",
          f"{o.margin_2p.isna().sum()} days without a value;", o.groupby("source").size().to_dict())
    for d in ("2017-11-07", "2018-11-06", "2021-11-02", "2022-11-08", "2024-11-05", "2025-11-04", "2026-11-03"):
        r = o[o.date == d].iloc[0]
        print(d, f"{r.margin_2p:+.1f}", int(r.n_polls) if pd.notna(r.n_polls) else "", r.source)
