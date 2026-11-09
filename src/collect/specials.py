"""U.S. House special elections 2007-2026, for the special-election model (PLAN.md, "After the scorecard", item 5).

Source: the "Special elections" tables on the yearly House election pages already cached for the House history
(data/raw/wikipedia_hist/: 2008-2024), the 2026 page in the final pre-election snapshot (data/raw/wikipedia/,
Nov 3, 2026), and the odd-year pages (2007-2025), which hold only specials (fetched once into wikipedia_hist/). Each row: district, the vacating member and party, the
election date (from the results text), every candidate's share.

Joined to the district's lean on the lines in force (Cook PVI from data/interim/house_history.csv for the last
regular election before the special) and that election's result. Specials held on a regular general-election day
are dropped (their environment is the general's), as are races without both a Democrat and a Republican in the
deciding round (all-party formats that end D vs D or R vs R). Margin: all Democrats' share against all Republicans'
in the deciding round (the runoff when there was one), so all-party formats aren't read off the top two alone.

Run:  python src/collect/specials.py
Writes data/interim/house_specials.csv
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import RAW, ROOT  # noqa: E402
from governors import STATE_NAMES, clean, outcome, parse_candidates, read_tables  # noqa: E402

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
GENERAL_DAYS = {pd.Timestamp(d) for d in ("2006-11-07", "2008-11-04", "2010-11-02", "2012-11-06", "2014-11-04", "2016-11-08",
                                           "2018-11-06", "2020-11-03", "2022-11-08", "2024-11-05", "2026-11-03")}


def pages():
    """[(page path, whole page is specials?)]: the even-year pages' special-election sections, and the odd-year pages
    ("2017 United States House of Representatives elections"), which hold only that year's specials."""
    from governors import get_page
    out = [(sorted(RAW.glob(f"wikipedia_hist/*/{y}_United_States_House_of_Representatives_elections.html"))[-1], False)
           for y in range(2008, 2025, 2)]
    out.append((sorted(RAW.glob("wikipedia/*/2026_United_States_House_of_Representatives_elections.html"))[-1], False))
    for y in range(2007, 2026, 2):
        t = f"{y}_United_States_House_of_Representatives_elections"
        try:
            get_page(t)
        except RuntimeError as e:
            print(f"  {t}: {e}")
            continue
        out.append((sorted(RAW.glob(f"wikipedia_hist/*/{t}.html"))[-1], True))
    return out


def district(cell):
    s = clean(cell)
    m = re.match(r"(.+?)\s+(\d+|at-large|At-large|AL)\b", s)
    if not m or m.group(1) not in STATE_NAMES:
        return None, None
    return STATE_NAMES[m.group(1)], 0 if not m.group(2).isdigit() else int(m.group(2))


def special_date(text):
    """Date the seat was filled: the last date in the results text ('died March 5, 2025. New member elected
    January 31, 2026, after a runoff')."""
    found = re.findall(rf"(?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}", clean(text))
    return pd.Timestamp(found[-1]) if found else None


def special_tables(html, whole_page=False):
    """Tables under a heading mentioning special elections (the regular tables also mention deaths and resignations);
    every table on an odd-year page."""
    from io import StringIO
    from bs4 import BeautifulSoup
    from results_margins import section_headings
    from wiki_polls import headings_before
    for tb in BeautifulSoup(html, "lxml").find_all("table"):
        secs = section_headings(tb) or headings_before(tb)
        if whole_page or any(re.search(r"special", s_, re.I) for s_ in secs):
            for t in read_tables(str(tb)):
                yield t


def deciding_round(cands):
    """Candidates of the deciding round: everything after a 'Runoff:' marker when the cell lists both rounds."""
    idx = next((i for i, c in enumerate(cands) if re.match(r"\s*Runoff:", c[0])), None)
    if idx is None:
        return cands
    out = [list(c) for c in cands[idx:]]
    out[0][0] = re.sub(r"^\s*Runoff:\s*", "", out[0][0])
    return out


def party_margin(cands):
    """Two-party margin from all Democrats' and all Republicans' shares in the round (all-party formats such as
    California's special primary split a party's vote across several candidates); replaces the top-candidate margin."""
    d = sum(c[3] for c in cands if c[1] == "D" and c[3] is not None)
    r = sum(c[3] for c in cands if c[1] == "R" and c[3] is not None)
    return {"d_total": d, "r_total": r, "margin_2p": 100 * (d - r) / (d + r) if d + r > 0 else np.nan, "contested": d > 0 and r > 0}


def collect():
    rows = []
    for p, whole in pages():
        for t in special_tables(p.read_text(encoding="utf-8"), whole):
            names = [clean(" ".join(dict.fromkeys(map(str, c))) if isinstance(c, tuple) else c) for c in t.columns]
            if not (any("District" in n for n in names) and any("Candidates" in n for n in names)
                    and any("Results" in n or "Status" in n for n in names)):
                continue
            ci = {k: next((i for i, n in enumerate(names) if k in n), None) for k in ("District", "Party", "Results", "Candidates", "Member")}
            if ci["Results"] is None:
                ci["Results"] = next(i for i, n in enumerate(names) if "Status" in n)
            for _, r in t.iterrows():
                status = clean(r.iloc[ci["Results"]])
                st, dist = district(r.iloc[ci["District"]])
                date = special_date(status)
                if not st or date is None:
                    continue
                cands = deciding_round(parse_candidates(r.iloc[ci["Candidates"]]))
                rows.append({"state": st, "district": dist, "date": date.date().isoformat(), "page": p.name,
                             "vacating": clean(r.iloc[ci["Member"]]) if ci["Member"] is not None else None,
                             "vacating_party_text": clean(r.iloc[ci["Party"]]) if ci["Party"] is not None else None,
                             "status": status, "candidates": json.dumps(cands), **outcome(cands), **party_margin(cands)})
    df = pd.DataFrame(rows).drop_duplicates(["state", "district", "date"])
    df["date"] = pd.to_datetime(df.date)
    return df


def join_lean(df):
    """Lean and previous result on the lines in force: the last regular election (even year) before the special."""
    h = pd.read_csv(ROOT / "data/interim/house_history.csv").set_index(["year", "state", "district"])
    df["lines_year"] = [max(y for y in range(2006, 2027, 2) if pd.Timestamp(f"{y}-11-01") < d) for d in df.date]
    look = lambda y, s, dd, col: h[col].get((y, s, dd), np.nan) if (y, s, dd) in h.index else np.nan
    df["pvi"] = [look(y, s, dd, "pvi") for y, s, dd in zip(df.lines_year, df.state, df.district)]
    df["prev_margin"] = [look(y, s, dd, "margin") for y, s, dd in zip(df.lines_year, df.state, df.district)]
    df["prev_inc"] = [look(y, s, dd, "inc") for y, s, dd in zip(df.lines_year, df.state, df.district)]
    df["lean2"] = 2 * df.pvi
    return df


def main():
    df = collect()
    n_all = len(df)
    df = df[~df.date.isin(GENERAL_DAYS)]
    n_offday = len(df)
    df = df[df.contested.fillna(False).astype(bool)]
    df = join_lean(df)
    from wiki import party_code  # noqa: E402
    df["vacating_party"] = df.vacating_party_text.map(lambda s: party_code(s) if isinstance(s, str) else None)
    # a third candidate at 15%+ (NY-23 2009: the Republican withdrew; the Conservative was the real opponent)
    df["max_other_pct"] = [max([c[3] for c in json.loads(x) if c[1] not in "DR" and c[3] is not None], default=0.0) for x in df.candidates]
    df["multi_candidate"] = df.max_other_pct >= 15.0
    df = df.sort_values("date")
    df.to_csv(ROOT / "data/interim/house_specials.csv", index=False)
    print(f"house_specials.csv: {n_all} special elections found; {n_offday} not on a general-election day; "
          f"{len(df)} with a Democrat and a Republican; PVI for {int(df.pvi.notna().sum())}")
    print(df.groupby(df.date.dt.year).size().to_dict())
    return df


if __name__ == "__main__":
    main()
