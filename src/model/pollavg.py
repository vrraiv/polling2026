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
PARTISAN_SHIFT = 2.0  # sponsored polls: shift against the sponsor's party
POP_DEM_LEAN = {}     # registered-voter / adult polls lean Democratic relative to likely-voter polls (subtracted)
HALF_LIFE = 21
_PS = ROOT / "data/processed/poll_settings.json"
if _PS.exists():  # estimated in src/model/poll_settings.py
    _ch = json.loads(_PS.read_text())["chosen"]
    POP_W = dict(_ch["pop_weight"], v=_ch["pop_weight"]["lv"])
    PARTISAN_SHIFT = float(_ch["partisan_shift_statewide"])
    POP_DEM_LEAN = dict(_ch.get("pop_dem_lean", {}))
    HALF_LIFE = int(_ch["half_life_races"])


def load_votehub():
    d = json.loads(latest("votehub", "polls.json").read_text(encoding="utf-8"))
    for x in d:
        x["end"] = pd.Timestamp(x["end_date"])
    return d


def weight(x, half_life):
    half_life = half_life or HALF_LIFE
    age = (ASOF - x["end"]).days
    n = min(x.get("sample_size") or 600, 3000)
    return 0.5 ** (age / half_life) * np.sqrt(n / 600) * POP_W.get((x.get("population") or "lv").lower(), 0.7)


HOUSE_PARTISAN_SHIFT = float(json.loads(_PS.read_text())["chosen"]["partisan_shift_house"]) if _PS.exists() else 4.0


_PE = ROOT / "data/processed/pollster_effects.json"
PE_EST = json.loads(_PE.read_text()) if _PE.exists() else None
SPONSOR_LOG = {}   # pollster -> adjustment applied (for the site table)


def sponsor_adj(x, shift=PARTISAN_SHIFT, level="statewide"):
    """Sponsored-poll adjustment (added to the poll's D-R margin).
    With pollster_effects.json: pollsters with a track record (>=10 polls in 538's archive) get the within-pollster sponsor
    effect (beta ~1.2); pollsters without one get the thin-history shift (~4 statewide). VoteHub flags some polls by the
    pollster's affiliation rather than a paying client: a flagged poll with NO listed sponsor from an established pollster
    whose 538 record is mostly nonpartisan work (<50% partisan) gets no sponsor adjustment.
    Without the file: the flat shift."""
    p = (x.get("partisan") or "").upper()
    if x.get("internal"):
        p = p or "DEM"
    sg = 1 if p == "DEM" else -1 if p == "REP" else 0
    if sg == 0:
        return 0.0
    if PE_EST is None:
        return -shift * sg
    import pollster_effects as PEm
    _, key = PEm.adjustment(PE_EST, x["pollster"], sg, "tiered")
    if key is not None:
        if not x.get("sponsors") and PE_EST.get("partisan_work", {}).get(key, 1.0) < 0.5:
            adj = 0.0
        else:
            adj = PE_EST["beta"] * sg
    else:
        adj = PE_EST["thin_by_level"][level] * sg
    SPONSOR_LOG[(x["pollster"], p, bool(x.get("sponsors")))] = adj
    return -adj


def weighted_avg(rows, half_life, shift=PARTISAN_SHIFT, level="statewide"):
    """rows: list of (poll, margin). Down-weight pollsters with many polls (each pollster ~ sqrt(k) total weight)."""
    if not rows:
        return None
    df = pd.DataFrame([{"pollster": p["pollster"], "m": m + sponsor_adj(p, shift, level) - POP_DEM_LEAN.get((p.get("population") or "lv").lower(), 0.0),
                        "w": weight(p, half_life),
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
    """Surname key for matching poll answers to nominees. Strips suffixes (Jr., Sr., III) and accents."""
    import unicodedata
    s = re.sub(r"\s+(Jr|Sr|III|II|IV)\.?\s*$", "", str(s)).replace(".", " ").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.split()[-1].lower() if s else ""


def senate(polls, races, since="2026-06-15", half_life=None):
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


def house(polls, races, since="2026-07-01", half_life=None):
    """District polls; matched to nominees by last name."""
    half_life = half_life or HALF_LIFE
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
        res = weighted_avg(rows, half_life, shift=HOUSE_PARTISAN_SHIFT, level="house")
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


def senate_multi(polls, race, since="2026-08-01", half_life=None):
    """3-way races: raw margin of the best non-R candidate over the Republican (no two-party conversion)."""
    half_life = half_life or HALF_LIFE
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


def senate_poll_list(polls, races, since="2026-06-15", limit=12):
    """Latest matched polls per Senate race, for display (same matching rules as the averages)."""
    out = {}
    for _, r in races.iterrows():
        dn, rn = r.get("dem_nominee"), r.get("rep_nominee")
        if not isinstance(dn, str) or not isinstance(rn, str):
            continue
        dl, rl = lastname(dn), lastname(rn)
        rows = []
        for x in polls:
            if x["poll_type"] != "us-senator" or x["subject"] != f"2026 {r['state_name']}" or x["end"] < pd.Timestamp(since):
                continue
            a = {lastname(y["choice"]): y["pct"] for y in x["answers"]}
            if dl in a and rl in a:
                others = [y for y in x["answers"] if lastname(y["choice"]) not in (dl, rl)]
                rows.append({"end": x["end_date"], "start": x.get("start_date"), "pollster": x["pollster"],
                             "n": x.get("sample_size"), "pop": (x.get("population") or "").upper(),
                             "d": a[dl], "r": a[rl], "other": round(sum(y["pct"] for y in others), 1) if others else None,
                             "partisan": x.get("partisan"), "sponsors": x.get("sponsors") or [], "url": x.get("url"),
                             "margin2": round(two_party(a[dl], a[rl]), 1)})
        rows.sort(key=lambda z: z["end"], reverse=True)
        out[r["race_key"]] = {"n_total": len(rows), "polls": rows[:limit]}
    return out
