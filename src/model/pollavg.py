"""Poll averaging from the VoteHub snapshot.

All margins are TWO-PARTY D-R margins in points: 100*(D-R)/(D+R).
For Nebraska the independent (Osborn) is treated as the anti-R candidate.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT, latest  # noqa: E402

ASOF = pd.Timestamp.today().normalize()  # polls are weighted by age as of today
POP_W = {"lv": 1.0, "rv": 0.8, "a": 0.5, "v": 0.9}
PARTISAN_SHIFT = 2.0  # sponsored polls: shift 2 pts against the sponsor's party


def load_votehub():
    d = json.loads(latest("votehub", "polls.json").read_text(encoding="utf-8"))
    for x in d:
        x["end"] = pd.Timestamp(x["end_date"])
    return d


def weight(x, half_life):
    age = (ASOF - x["end"]).days
    n = min(x.get("sample_size") or 600, 3000)
    return 0.5 ** (age / half_life) * np.sqrt(n / 600) * POP_W.get((x.get("population") or "lv").lower(), 0.7)


HOUSE_PARTISAN_SHIFT = 4.0  # district polls: sponsored polls are mostly party/PAC releases (48 of 132 DEM-sponsored)


def sponsor_adj(x, shift=PARTISAN_SHIFT):
    p = (x.get("partisan") or "").upper()
    if x.get("internal"):
        p = p or "DEM"  # VoteHub sets none today; placeholder so internals are never unadjusted
    return -shift if p == "DEM" else shift if p == "REP" else 0.0


def weighted_avg(rows, half_life, shift=PARTISAN_SHIFT):
    """rows: list of (poll, margin). Down-weight pollsters with many polls (each pollster ~ sqrt(k) total weight)."""
    if not rows:
        return None
    df = pd.DataFrame([{"pollster": p["pollster"], "m": m + sponsor_adj(p, shift), "w": weight(p, half_life),
                        "end": p["end"], "n": p.get("sample_size") or 600} for p, m in rows])
    df["k"] = df.groupby("pollster").pollster.transform("size")
    df["w"] = df.w / np.sqrt(df.k)
    avg = float(np.average(df.m, weights=df.w))
    neff = df.w.sum() ** 2 / (df.w ** 2).sum()
    return {"avg": avg, "n_polls": len(df), "n_pollsters": df.pollster.nunique(), "neff": float(neff),
            "latest": str(df.end.max().date()), "spread_sd": float(np.sqrt(np.average((df.m - avg) ** 2, weights=df.w)))}


def two_party(d, r):
    return 100.0 * (d - r) / (d + r)


def generic_ballot(polls, since="2026-08-01", half_life=14):
    rows = []
    for x in polls:
        if x["poll_type"] != "generic-ballot" or x["end"] < pd.Timestamp(since):
            continue
        a = {y["choice"]: y["pct"] for y in x["answers"]}
        if "Dem" in a and "Rep" in a:
            rows.append((x, two_party(a["Dem"], a["Rep"])))
    return weighted_avg(rows, half_life)


def lastname(s):
    s = re.sub(r"\b(Jr\.?|Sr\.?|III|II|IV)\b", "", s).strip()
    return s.split()[-1].lower() if s else ""


def senate(polls, races, since="2026-06-15", half_life=21):
    out = {}
    for _, r in races.iterrows():
        st_name = r["state_name"]
        dn, rn = r["dem_nominee"], r["rep_nominee"]
        if not isinstance(dn, str) or not isinstance(rn, str):
            continue
        dl, rl = lastname(dn), lastname(rn)
        rows = []
        for x in polls:
            if x["poll_type"] != "us-senator" or x["subject"] != f"2026 {st_name}" or x["end"] < pd.Timestamp(since):
                continue
            a = {lastname(y["choice"]): y["pct"] for y in x["answers"]}
            if dl in a and rl in a and len(x["answers"]) >= 2:
                rows.append((x, two_party(a[dl], a[rl])))
        res = weighted_avg(rows, half_life)
        if res:
            out[r["race_key"]] = res
    return out


def house(polls, races, since="2026-07-01", half_life=21):
    """District polls; matched to nominees by last name."""
    out = {}
    idx = {f"{s}-{d:02d}" if d else f"{s}-01": k for s, d, k in zip(races.state, races.district, races.race_key)}
    for seat in {x.get("seat_name") for x in polls if x["poll_type"] == "us-representative"}:
        if not seat or seat not in idx:
            continue
        key = idx[seat]
        r = races.set_index("race_key").loc[key]
        dls = [lastname(n) for n in str(r.dem_cand).split("; ") if n and n != "nan"]
        rls = [lastname(n) for n in str(r.rep_cand).split("; ") if n and n != "nan"]
        rows = []
        for x in polls:
            if x["poll_type"] != "us-representative" or x.get("seat_name") != seat or x["end"] < pd.Timestamp(since):
                continue
            a = {lastname(y["choice"]): y["pct"] for y in x["answers"]}
            d = [a[l] for l in dls if l in a]
            rr = [a[l] for l in rls if l in a]
            if len(d) == 1 and len(rr) == 1:
                rows.append((x, two_party(d[0], rr[0])))
        res = weighted_avg(rows, half_life, shift=HOUSE_PARTISAN_SHIFT)
        if res:
            out[key] = res
    return out


def approval(polls, subject="Donald Trump", since="2026-09-01", half_life=14):
    rows = []
    for x in polls:
        if x["poll_type"] != "approval" or x.get("subject") != subject or x["end"] < pd.Timestamp(since):
            continue
        a = {y["choice"].lower(): y["pct"] for y in x["answers"]}
        if "approve" in a and "disapprove" in a:
            rows.append((x, a["approve"]))
    res = weighted_avg([(p, m) for p, m in rows], half_life)
    return res


def senate_multi(polls, race, since="2026-08-01", half_life=21):
    """3-way races: raw margin of the best non-R candidate over the Republican (no two-party conversion)."""
    rl = lastname(race["rep_nominee"])
    rows = []
    for x in polls:
        if x["poll_type"] != "us-senator" or x["subject"] != f"2026 {race['state_name']}" or x["end"] < pd.Timestamp(since):
            continue
        a = {lastname(y["choice"]): y["pct"] for y in x["answers"]}
        if rl in a and len(a) >= 3:
            others = [v for k, v in a.items() if k != rl]
            rows.append((x, max(others) - a[rl]))
    return weighted_avg(rows, half_life)
