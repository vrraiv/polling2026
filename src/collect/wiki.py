"""Snapshot + parse Wikipedia 2026 House/Senate pages into race tables.

Outputs (data/interim/):
  house_2026_races.csv   435 districts: PVI on 2026 lines, incumbent, party, status, candidates
  senate_2026_races.csv  35 races: PVI, incumbent, expert ratings (benchmark only)
  generic_ballot_aggregates_2026.csv
"""
import re
import sys
from io import StringIO
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, fetch, latest  # noqa: E402

PAGES = ["2026_United_States_House_of_Representatives_elections", "2026_United_States_Senate_elections",
         "2025–2026_United_States_redistricting", "Opinion_polling_on_the_second_Trump_presidency"]
INTERIM = ROOT / "data" / "interim"
INTERIM.mkdir(parents=True, exist_ok=True)

STATE_ABBR = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
              "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
              "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
              "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
              "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
              "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
              "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
              "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
              "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
              "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"}


def snapshot():
    for p in PAGES:
        fetch("wikipedia", p + ".html", f"https://en.wikipedia.org/api/rest_v1/page/html/{p}", skip_existing=False)


def flat(t):
    t.columns = [" ".join(dict.fromkeys(map(str, c))) if isinstance(c, tuple) else str(c) for c in t.columns]
    return t


def pvi(s):
    """'R+5' -> -5 ; 'D+3' -> +3 ; 'EVEN' -> 0 (positive = Democratic lean)."""
    s = str(s).strip()
    m = re.match(r"([DR])\+(\d+)", s)
    if m:
        return int(m.group(2)) * (1 if m.group(1) == "D" else -1)
    return 0 if "EVEN" in s.upper() else None


def party_code(p):
    p = str(p)
    if p.startswith("Democratic") or p in ("DFL", "Democratic–Farmer–Labor"):
        return "D"
    if p.startswith("Republican"):
        return "R"
    return "I" if "Independent" in p or "Nonpartisan" in p else "O"


CAND = re.compile(r"▌\s*([^▌(]+?)\s*\(([^)]+)\)")


def candidates(text):
    out = {}
    for name, party in CAND.findall(str(text)):
        party = party.strip()
        key = party_code(party)
        out.setdefault(key, []).append(re.sub(r"\[.*?\]", "", name).strip())
    return out


def clean(s):
    return re.sub(r"\[.*?\]", "", str(s)).replace(" ", " ").strip()


def guard_changes(new, path, key="race_key", hard=("pvi", "inc_party"), soft=("status", "dem_cand", "rep_cand", "ind_cand",
                  "cands_D", "cands_R", "cands_I", "incumbent")):
    """Compare a freshly parsed race table with the previous one before overwriting it (vandalism guard).
    Prints every changed field; stops the pipeline if PVI or incumbent party changed, unless ALLOW_WIKI_CHANGES=1."""
    import os
    if not path.exists():
        return
    old = pd.read_csv(path)
    m = old.merge(new, on=key, how="outer", suffixes=("_old", "_new"), indicator=True)
    added, dropped = m[m._merge == "right_only"][key].tolist(), m[m._merge == "left_only"][key].tolist()
    m = m[m._merge == "both"]
    hard_hits = []
    for c in hard + soft:
        if f"{c}_old" not in m.columns:
            continue
        a = m[f"{c}_old"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
        b = m[f"{c}_new"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
        for _, r in m[a != b].iterrows():
            print(f"  [wiki change] {r[key]} {c}: {str(r[c + '_old'])[:60]!r} -> {str(r[c + '_new'])[:60]!r}")
            if c in hard:
                hard_hits.append((r[key], c))
    if added or dropped:
        print(f"  [wiki change] races added {added} dropped {dropped}")
    if (hard_hits or added or dropped) and os.environ.get("ALLOW_WIKI_CHANGES") != "1":
        raise SystemExit(f"STOP: {len(hard_hits)} PVI/party changes and {len(added) + len(dropped)} added/dropped races vs the previous "
                         f"snapshot ({path.name}). Inspect the Wikipedia revision history; rerun with ALLOW_WIKI_CHANGES=1 if legitimate.")


def house():
    html = latest("wikipedia", PAGES[0] + ".html").read_text(encoding="utf-8")
    rows = []
    for t in pd.read_html(StringIO(html)):
        t = flat(t)
        pcol = [c for c in t.columns if "2026 PVI" in c and c.startswith("District")]
        if not pcol or "Incumbent Status" not in t.columns:
            continue
        ccol = [c for c in t.columns if c.startswith("Candidates")][0]
        for _, r in t.iterrows():
            loc = r["District Location"]
            if not isinstance(loc, str):
                continue
            m = re.match(r"(.+?)\s+(\d+|at-large)$", loc.replace(" ", " ").strip())
            if not m:
                continue
            st, dist = m.group(1), m.group(2)
            cands = candidates(r[ccol])
            status = clean(r["Incumbent Status"])
            rows.append(dict(
                state=STATE_ABBR[st], district=0 if dist == "at-large" else int(dist),
                pvi=pvi(r[pcol[0]]), incumbent=clean(r["Incumbent Member"]),
                inc_party=party_code(clean(r["Incumbent Party"])),
                status=status,
                open_seat=not bool(re.search(r"renominated|advanced|re-elected|running", status, re.I)) or
                          bool(re.search(r"retir|lost|resign|died|vacant|running for", status, re.I)),
                n_dem=len(cands.get("D", [])), n_rep=len(cands.get("R", [])),
                dem_cand="; ".join(cands.get("D", [])), rep_cand="; ".join(cands.get("R", [])),
                ind_cand="; ".join(cands.get("I", [])), candidates_raw=clean(r[ccol])))
    df = pd.DataFrame(rows).drop_duplicates(["state", "district"])
    df["race_key"] = "2026|" + df.state + "|H|" + df.district.astype(str)
    guard_changes(df, INTERIM / "house_2026_races.csv")
    df.to_csv(INTERIM / "house_2026_races.csv", index=False)
    print("house rows", len(df), "missing pvi", df.pvi.isna().sum())
    return df


def generic_aggregates():
    html = latest("wikipedia", PAGES[0] + ".html").read_text(encoding="utf-8")
    for t in pd.read_html(StringIO(html)):
        t = flat(t)
        if "Source of poll aggregation" in t.columns:
            t.to_csv(INTERIM / "generic_ballot_aggregates_2026.csv", index=False)
            print(t.to_string())
            return


def senate():
    html = latest("wikipedia", PAGES[1] + ".html").read_text(encoding="utf-8")
    tables = [flat(t) for t in pd.read_html(StringIO(html))]
    ratings = next(t for t in tables if any(c.startswith("Ratings Cook") for c in t.columns))
    summary = next(t for t in tables if "Candidates" in t.columns and "Results" in t.columns)
    rcols = [c for c in ratings.columns if c.startswith("Ratings")]
    rows = []
    for _, r in ratings.iterrows():
        st_raw = clean(r["Constituency State"])
        st = re.sub(r"\s*\(.*\)", "", st_raw).strip()
        if st not in STATE_ABBR:
            continue
        special = "special" in st_raw.lower()
        row = dict(state=STATE_ABBR[st], special=special, pvi=pvi(r[[c for c in ratings.columns if "PVI" in c][0]]),
                   incumbent=clean(r["Incumbent Senator"]), last_result=clean(r[[c for c in ratings.columns if "Last" in c][0]]))
        for c in rcols:
            row["rating_" + re.sub(r"Ratings (\S+(?: NOW)?).*", r"\1", c).replace(" ", "")] = clean(r[c])
        rows.append(row)
    df = pd.DataFrame(rows)
    summ = {}
    for _, r in summary.iterrows():
        st = clean(r["Constituency State"])
        if st in STATE_ABBR:
            summ[STATE_ABBR[st]] = (clean(r["Incumbent Party"]), clean(r["Results"]), r["Candidates"])
    df["inc_party"] = [party_code(summ[s][0]) if s in summ else "" for s in df.state]
    df["status"] = [summ.get(s, ("", ""))[1] for s in df.state]
    for k in "DRI":
        df[f"cands_{k}"] = ["; ".join(candidates(summ[s][2]).get(k, [])) if s in summ and not sp else ""
                            for s, sp in zip(df.state, df.special)]
    df["race_key"] = "2026|" + df.state + "|S|" + df.special.map({True: "special", False: "regular"})
    guard_changes(df, INTERIM / "senate_2026_races.csv")
    df.to_csv(INTERIM / "senate_2026_races.csv", index=False)
    print("senate rows", len(df))
    print(df[["race_key", "pvi", "incumbent", "inc_party", "cands_D", "cands_R", "cands_I", "rating_Cook"]].to_string())
    return df


if __name__ == "__main__":
    for w in sys.argv[1:] or ["house", "senate", "generic_aggregates"]:
        globals()[w]()
