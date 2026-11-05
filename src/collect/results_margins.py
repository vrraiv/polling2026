"""Stage 2 of the results collector: vote counts from the per-state Wikipedia pages -> margins.

Pages: every "2026 United States Senate (special) election in X" and "2026 United States House of Representatives
election(s) in X" page linked from the overview snapshots. They are 1-5 MB each (~150 MB per full snapshot), so they
are stored under data/raw/wikipedia_results_pages/ (gitignored). The parsed tables record each page's revision id,
which pins the exact version used (https://en.wikipedia.org/w/index.php?oldid=<id>).

From each page, the general-election result box (inside a "General election" section; caption not a primary, runoff
or convention): party, candidate and votes per row. Ranked-choice boxes (Alaska; Maine if needed) have one Votes
column per round: both the first choice and the final round are kept.

Margins, matching the forecast's definitions (src/model/forecast.py):
  - two-party: 100*(D side - R)/(D side + R). D side = the frozen forecast's D-side nominee (an independent in NE, ID,
    SD), matched by last name; otherwise the leading Democrat. R = the leading Republican (CA-6: Kiley, I, ex-R).
  - MT Senate (MULTI_CANDIDATE in forecast.py): raw margin, best non-Republican minus Republican as % of all votes.
  - Ranked choice: the final round. Georgia: the Nov 3 count (no runoff).
Checks per box: candidate votes add up to the box's total (within 0.5%), listed % match the votes (within 0.3 pts). The
sign of each margin is checked against the called winner in scorecard.py.

Run:  python src/collect/results_margins.py          (snapshot every state page + parse; ~5 min, rate-limited)
      python src/collect/results_margins.py resume   (finish an interrupted snapshot: skip pages already fetched today)
      python src/collect/results_margins.py parse    (re-parse the latest snapshot)
Writes data/scorecard/margins_senate.csv, margins_house.csv (one row per race), candidates_*.csv (one row per candidate).
"""
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, RAW, fetch, latest  # noqa: E402
from results import FINAL, OUT, PAGES, SOURCE, clean, col, fold, grid, header_labels, text  # noqa: E402
from wiki import STATE_ABBR, party_code  # noqa: E402

PAGE_SOURCE = "wikipedia_results_pages"
MULTI_CANDIDATE = {"MT"}
SKIP_ROW = re.compile(r"^(total|turnout|registered|majority|plurality|blank|void|invalid|rejected|over ?votes|under ?votes|"
                      r"inactive|exhausted|.*\b(hold|gain)\b)", re.I)
ORD = re.compile(r"(\d+)(?:st|nd|rd|th)\s+congressional district", re.I)


# ---------------- page list + snapshot ----------------
def page_titles():
    """Per-state result pages linked from the latest overview snapshots: {"senate": {race_key: title}, "house": {ST: title}}."""
    titles = set()
    for p in PAGES.values():
        s = BeautifulSoup(latest(SOURCE, p + ".html").read_text(encoding="utf-8"), "lxml")
        titles |= {a["href"][2:].split("#")[0] for a in s.find_all("a", href=True)
                   if re.match(r"\./2026_United_States_(Senate|House_of_Representatives)_(special_)?elections?_in_", a["href"])}
    sen, hou = {}, {}
    for t in sorted(titles):
        m = re.match(r"2026_United_States_(Senate|House_of_Representatives)_(special_)?elections?_in_(.+)$", t)
        st = STATE_ABBR.get(m.group(3).replace("_", " "))
        if not st:
            continue  # territories
        if m.group(1) == "Senate":
            sen[f"2026|{st}|S|{'special' if m.group(2) else 'regular'}"] = t
        else:
            hou[st] = t
    return {"senate": sen, "house": hou}


def snapshot(pause=2.0, resume=False):
    """Fetch every state page. Wikipedia rate-limits uncached page renders (HTTP 429), so go slowly and back off;
    resume=True skips pages already fetched today (to finish an interrupted run)."""
    for chamber, d in page_titles().items():
        for t in d.values():
            for attempt in range(4):
                try:
                    fetch(PAGE_SOURCE, t + ".html", f"https://en.wikipedia.org/api/rest_v1/page/html/{t}", skip_existing=resume)
                    break
                except RuntimeError as e:
                    if "429" not in str(e) or attempt == 3:
                        raise
                    print(f"  rate-limited on {t}; waiting {60 * (attempt + 1)} s")
                    time.sleep(60 * (attempt + 1))
            time.sleep(pause)


# ---------------- parsing ----------------
def section_headings(t):
    """Headings of the sections enclosing a table, innermost first."""
    out = []
    for sec in t.find_parents("section"):
        for child in sec.find_all(recursive=False):
            h = child if re.match(r"^h[1-6]$", child.name or "") else child.find(re.compile(r"^h[1-6]$")) \
                if "mw-heading" in (child.get("class") or []) else None
            if h is not None:
                out.append(h.get_text(" ", strip=True))
                break
    return out


def num(s):
    s = re.sub(r"\[.*?\]", "", str(s)).replace(",", "").replace("%", "").replace("−", "-").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_box(t):
    """Rows of one result box: [{party, party_code, candidate, votes_first, votes_final, pct_first}], total, rounds."""
    g = grid(t)
    labels, nh = header_labels(g)
    vcols = [j for j, l in enumerate(labels) if re.search(r"\bvotes\b", l, re.I)]
    ccol = col(labels, "Candidate")
    pcols = [j for j, l in enumerate(labels) if l.lower().startswith("party")]
    if not vcols or ccol is None:
        return None
    rows, total = [], np.nan
    for r in g[nh:]:
        if len(r) <= max(vcols + [ccol]):
            continue
        cand = re.sub(r"\(incumbent\)", "", text(r[ccol]), flags=re.I).strip()
        first_cell = text(r[0]) if r[0] is not None else ""
        if re.match(r"^total", cand, re.I) or re.match(r"^total", first_cell, re.I):
            total = num(text(r[vcols[0]]))
            continue
        if not cand or SKIP_ROW.match(cand) or SKIP_ROW.match(first_cell):
            continue
        party = next((text(r[j]) for j in pcols if r[j] is not None and text(r[j])), "")
        votes = [num(text(r[j])) for j in vcols]
        pct_j = vcols[0] + 1
        rows.append({"party": party, "party_code": party_code(party), "candidate": cand, "votes_by_round": votes,
                     "pct_first": num(text(r[pct_j])) if pct_j < len(r) and r[pct_j] is not None else np.nan})
    if not rows:
        return None
    # final round: the last Votes column in which at least two candidates have a count
    k_final = max((k for k in range(len(vcols)) if sum(np.isfinite(x["votes_by_round"][k]) for x in rows) >= 2), default=0)
    for x in rows:
        x["votes_first"], x["votes_final"] = x["votes_by_round"][0], x["votes_by_round"][k_final]
    return {"rows": rows, "total": total, "n_rounds": len(vcols), "final_round": k_final}


def margins_rcv(rows, first=False, **kw):
    """margins() on the final round, or on the last round where both the D side and the Republican are still in
    (a ranked-choice count can eliminate one of them first; Alaska 2022 Senate ended R vs R)."""
    nr = len(rows[0].get("votes_by_round", [None])) if rows else 0
    rounds = [0] if first or nr <= 1 else range(nr - 1, -1, -1)
    for k in rounds:
        res = margins([{**x, "votes_final": x["votes_by_round"][k] if "votes_by_round" in x else x["votes_final"]}
                       for x in rows], **kw)
        if np.isfinite(res[0]):
            return (*res, k + 1)
    return (np.nan, np.nan, np.nan, "", None)


def general_boxes(soup, chamber, year=2026):
    """[(district or None, caption, box)] for the general-election boxes on a page."""
    out = []
    for t in soup.find_all("table"):
        cap = t.find("caption")
        cap = clean(cap.get_text(" ", strip=True)) if cap else ""
        if not cap or re.search(r"primary|runoff|convention|caucus|by county|by district", cap, re.I):
            continue
        secs = section_headings(t)
        if not any(re.match(r"general election", s, re.I) for s in secs):
            continue
        if chamber == "senate" and "senate" not in cap.lower():
            continue
        dist, note = None, ""
        if chamber == "house":
            if re.search(r"special", cap, re.I):
                continue
            # the section heading decides; the caption is a fallback (editors copy boxes between districts and forget to
            # update the caption: FL-12's box was captioned "Florida's 8th" on Nov 4)
            h = next((re.match(r"District\s+(\d+)", s) for s in secs if re.match(r"District\s+\d+", s)), None)
            m = ORD.search(cap)
            cap_dist = int(m.group(1)) if m else 0 if re.search(r"at-large", cap, re.I) else None
            dist = int(h.group(1)) if h else cap_dist
            if dist is None:
                continue
            if h and cap_dist is not None and cap_dist != dist:
                note = f"caption says district {cap_dist}, section says {dist}"
        box = parse_box(t)
        if box:
            box["note"] = note
            out.append((dist, cap, box))
    return out


def page_meta(html, path):
    rev = re.search(r"Special:Redirect/revision/(\d+)", html[:2000])
    mod = re.search(r'property="dc:modified" content="([^"]+)"', html[:4000])
    return {"revision": int(rev.group(1)) if rev else None, "page_modified": mod.group(1) if mod else None,
            "snapshot": str(path.relative_to(ROOT)) if str(path).startswith(str(ROOT)) else str(path)}


def cand_sum(rows):
    """Sum of first-round candidate votes: the count-progress measure (the box's "Total votes" row can lag the candidate
    rows when an editor updates one and not the other; AK-H on Nov 4)."""
    v = [x["votes_first"] for x in rows if np.isfinite(x["votes_first"])]
    return float(sum(v)) if v else np.nan


def checks(box):
    rows = box["rows"]
    s = np.nansum([x["votes_first"] for x in rows])
    issues = []
    if np.isfinite(box["total"]) and box["total"] > 0 and s > 0 and abs(s - box["total"]) / box["total"] > 0.005:
        issues.append(f"candidate votes {s:,.0f} vs total {box['total']:,.0f}")
    if s > 0:
        for x in rows:
            if np.isfinite(x["votes_first"]) and np.isfinite(x["pct_first"]):
                base = box["total"] if np.isfinite(box["total"]) and box["total"] > 0 else s
                if abs(100 * x["votes_first"] / base - x["pct_first"]) > 0.3:
                    issues.append(f"{x['candidate']}: {x['pct_first']}% listed vs {100 * x['votes_first'] / base:.2f}% from votes")
    return issues


def margins(rows, dside_name=None, dside_party="D", multi=False, alt_opponent=None):
    """Margin of the D side over the leading Republican from a box's rows (final-round votes)."""
    v = [(x, x["votes_final"]) for x in rows if np.isfinite(x["votes_final"])]
    if len(v) < 2:
        return np.nan, np.nan, np.nan, ""
    reps = sorted([(x, n) for x, n in v if x["party_code"] == "R"], key=lambda z: -z[1])
    if not reps and alt_opponent:
        reps = sorted([(x, n) for x, n in v if fold(alt_opponent) in fold(x["candidate"])], key=lambda z: -z[1])
    if multi:
        nonr = sorted([(x, n) for x, n in v if x["party_code"] != "R"], key=lambda z: -z[1])
        tot = sum(n for _, n in v)
        if not reps or not nonr:
            return np.nan, np.nan, np.nan, ""
        return 100 * (nonr[0][1] - reps[0][1]) / tot, nonr[0][1], reps[0][1], nonr[0][0]["candidate"]
    if dside_party == "I" and dside_name:
        last = fold(dside_name.split()[-1])
        ds = sorted([(x, n) for x, n in v if last in fold(x["candidate"])], key=lambda z: -z[1])
    else:
        ds = sorted([(x, n) for x, n in v if x["party_code"] == "D"], key=lambda z: -z[1])
    if not ds or not reps:
        return np.nan, (ds[0][1] if ds else np.nan), (reps[0][1] if reps else np.nan), ds[0][0]["candidate"] if ds else ""
    d, r = ds[0][1], reps[0][1]
    return 100 * (d - r) / (d + r), d, r, ds[0][0]["candidate"]


def parse_senate(paths=None):
    """paths: {race_key: html path}; default = the latest snapshot of every Senate page."""
    frozen = pd.read_csv(FINAL / "senate_polls_fundamentals.csv").set_index("race_key")
    paths = paths or {k: latest(PAGE_SOURCE, t + ".html") for k, t in page_titles()["senate"].items()}
    rows, cands = [], []
    for key, path in paths.items():
        html = Path(path).read_text(encoding="utf-8")
        boxes = general_boxes(BeautifulSoup(html, "lxml"), "senate")
        meta = page_meta(html, Path(path))
        f = frozen.loc[key] if key in frozen.index else None
        row = {"race_key": key, "source": "wikipedia", **meta, "n_boxes": len(boxes)}
        if boxes:
            cap, box = boxes[0][1], boxes[0][2]
            st = key.split("|")[1]
            kw = dict(dside_name=f["dem"] if f is not None else None, dside_party=f["dside"] if f is not None else "D",
                      multi=st in MULTI_CANDIDATE)
            m, d, r, dname, k = margins_rcv(box["rows"], **kw)
            m1 = margins_rcv(box["rows"], first=True, **kw)[0]
            row.update(caption=cap, margin=m, margin_first_choice=m1, dside_votes=d, rep_votes=r, dside_candidate=dname,
                       total=box["total"], cand_sum=cand_sum(box["rows"]), n_rounds=box["n_rounds"], margin_round=k,
                       margin_type="raw best non-R minus R" if st in MULTI_CANDIDATE else "two-party",
                       issues="; ".join(checks(box)))
            cands += [{"race_key": key, **{k: v for k, v in x.items() if k != "votes_by_round"}} for x in box["rows"]]
        rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(cands)


def parse_house(paths=None):
    """paths: {state: html path}; default = the latest snapshot of every House state page."""
    frozen = pd.read_csv(FINAL / "house_polls_fundamentals.csv").set_index("race_key")
    paths = paths or {st: latest(PAGE_SOURCE, t + ".html") for st, t in page_titles()["house"].items()}
    rows, cands = [], []
    for st, path in paths.items():
        html = Path(path).read_text(encoding="utf-8")
        meta = page_meta(html, Path(path))
        seen = set()
        for dist, cap, box in general_boxes(BeautifulSoup(html, "lxml"), "house"):
            key = f"2026|{st}|H|{dist}"
            if key in seen:
                continue
            seen.add(key)
            f = frozen.loc[key] if key in frozen.index else None
            alt = "Kiley" if f is not None and isinstance(f.get("special_case"), str) and "Kiley" in f["special_case"] else None
            m, d, r, dname, k = margins_rcv(box["rows"], alt_opponent=alt)
            m1 = margins_rcv(box["rows"], first=True, alt_opponent=alt)[0]
            rows.append({"race_key": key, "source": "wikipedia", **meta, "caption": cap, "margin": m, "margin_first_choice": m1,
                         "dside_votes": d, "rep_votes": r, "dside_candidate": dname, "total": box["total"],
                         "cand_sum": cand_sum(box["rows"]), "n_rounds": box["n_rounds"],
                         "margin_round": k, "margin_type": "two-party", "issues": "; ".join(checks(box) + ([box["note"]] if box.get("note") else [])),
                         "d_votes_all": sum(x["votes_first"] for x in box["rows"] if x["party_code"] == "D" and np.isfinite(x["votes_first"])),
                         "r_votes_all": sum(x["votes_first"] for x in box["rows"] if x["party_code"] == "R" and np.isfinite(x["votes_first"]))})
            cands += [{"race_key": key, **{k: v for k, v in x.items() if k != "votes_by_round"}} for x in box["rows"]]
    return pd.DataFrame(rows), pd.DataFrame(cands)


# ---------------- California: the Secretary of State's results API (official) ----------------
# Wikipedia's California page has no per-district result boxes, and the state publishes JSON, so California House
# margins come from the official source. California counts mail ballots for weeks: "Reporting" counts precincts, not
# outstanding ballots, so these numbers keep moving until certification.
CA_API = "https://api.sos.ca.gov/returns/us-rep/district/{d}"
CA_PARTY = {"Dem": "D", "Rep": "R", "NPP": "I"}


def snapshot_ca(pause=0.5, resume=False):
    for d in range(1, 53):
        fetch("ca_sos", f"us-rep-{d}.json", CA_API.format(d=d), skip_existing=resume)
        time.sleep(pause)


def parse_ca():
    import json
    frozen = pd.read_csv(FINAL / "house_polls_fundamentals.csv").set_index("race_key")
    rows, cands = [], []
    for d in range(1, 53):
        try:
            path = latest("ca_sos", f"us-rep-{d}.json")
        except FileNotFoundError:
            continue
        j = json.loads(path.read_text(encoding="utf-8"))
        key = f"2026|CA|H|{d}"
        cs = [{"party": c.get("Party", ""), "party_code": CA_PARTY.get(c.get("Party", ""), "O"), "candidate": c.get("Name", ""),
               "votes_first": num(c.get("Votes")), "votes_final": num(c.get("Votes")), "pct_first": num(c.get("Percent"))}
              for c in j.get("candidates", [])]
        f = frozen.loc[key] if key in frozen.index else None
        alt = "Kiley" if f is not None and isinstance(f.get("special_case"), str) and "Kiley" in f["special_case"] else None
        m, dv, rv, dname, k = margins_rcv(cs, alt_opponent=alt)
        issues = []
        if "2026" not in str(j.get("ReportingTime", "")):
            issues.append(f"reporting time {j.get('ReportingTime')!r} is not 2026")
        if not re.search(rf"District {d}\b", str(j.get("raceTitle", ""))):
            issues.append(f"race title {j.get('raceTitle')!r}")
        s = np.nansum([x["votes_first"] for x in cs])
        for x in cs:
            if s > 0 and np.isfinite(x["pct_first"]) and abs(100 * x["votes_first"] / s - x["pct_first"]) > 0.3:
                issues.append(f"{x['candidate']}: {x['pct_first']}% listed vs {100 * x['votes_first'] / s:.2f}% from votes")
        rows.append({"race_key": key, "source": "ca_sos", "revision": None, "page_modified": j.get("ReportingTime"),
                     "snapshot": str(path.relative_to(ROOT)), "caption": j.get("raceTitle"), "reporting": j.get("Reporting"),
                     "margin": m, "margin_first_choice": m, "dside_votes": dv, "rep_votes": rv, "dside_candidate": dname,
                     "total": s, "cand_sum": s, "n_rounds": 1, "margin_round": k, "margin_type": "two-party", "issues": "; ".join(issues),
                     "d_votes_all": sum(x["votes_first"] for x in cs if x["party_code"] == "D" and np.isfinite(x["votes_first"])),
                     "r_votes_all": sum(x["votes_first"] for x in cs if x["party_code"] == "R" and np.isfinite(x["votes_first"]))})
        cands += [{"race_key": key, **x} for x in cs]
    return pd.DataFrame(rows), pd.DataFrame(cands)


SETTLED_GROWTH = 0.01   # a count is stable when its candidate votes grew less than 1% between snapshots on different days
SWING_FLAG = 2.0         # margin moved this many points with almost no new votes: flag, don't trust
# States that count mail ballots for weeks, county by county. A day without movement there proves nothing (California
# re-issues its statewide report while a district's counties add nothing; "100% of precincts" is reported on election
# night), so these settle only once the count has held still for SLOW_COUNT_DAYS.
SLOW_COUNT = {"CA", "WA", "OR", "NV", "AZ", "UT", "AK"}
SLOW_COUNT_DAYS = 7


def settledness(df, chamber):
    """Append today's counts to data/scorecard/margins_history_<chamber>.csv (one row per race and snapshot day) and
    judge each race against the previous day's snapshot:
      count_stable  candidate votes moved less than SETTLED_GROWTH, AND there is new evidence: the Wikipedia page was
                    edited (revision changed) or California re-issued its report (report time changed). An unedited page
                    proves nothing about whether counting has stopped.
      count_flag    the count moved the way a count in progress can't: candidate votes fell, or the margin swung more than
                    SWING_FLAG points with under SETTLED_GROWTH new votes. Flagged races are never settled.
                    In SLOW_COUNT states the count must also have held still for SLOW_COUNT_DAYS.
      settled       count_stable, no flag, and a margin exists (scores use settled races only).
    count_stable doesn't need a margin, so uncontested and same-party races still count toward the national House vote."""
    hist_path = OUT / f"margins_history_{chamber}.csv"
    day = df.snapshot.astype(str).str.extract(r"(\d{4}-\d{2}-\d{2})")[0]
    evidence = np.where(df.source.eq("wikipedia"), df.revision.astype(str), df.page_modified.astype(str))   # official/CA: report time
    src = df.source.astype(str).str.replace(r"\s*\(.*\)$", "", regex=True) if "source" in df else "wikipedia"
    now = pd.DataFrame({"race_key": df.race_key, "source": src, "day": day, "cand_sum": df.cand_sum, "margin": df.margin, "evidence": evidence})
    hist = pd.read_csv(hist_path, dtype={"evidence": str}) if hist_path.exists() else now.iloc[0:0]
    if "cand_sum" not in hist:   # history written before the switch to candidate sums: start over
        hist = now.iloc[0:0]
    if "source" not in hist:
        hist["source"] = np.where(hist.race_key.str.contains(r"\|CA\|H\|"), "ca_sos", "wikipedia")
    idx = ["race_key", "source", "day"]
    hist = pd.concat([hist[~hist.set_index(idx).index.isin(now.set_index(idx).index)], now])
    hist = hist[hist.cand_sum.fillna(0) > 0].sort_values(idx)
    hist.to_csv(hist_path, index=False)
    # compare with the previous day's count from the SAME source (official vs official, Wikipedia vs Wikipedia)
    prev = hist.merge(now[["race_key", "source", "day"]], on=["race_key", "source"], suffixes=("", "_now"))
    prev = prev[prev.day < prev.day_now].groupby("race_key").last()
    df = df.copy()
    df["prev_day"] = df.race_key.map(prev.day)
    df["prev_cand_sum"] = df.race_key.map(prev.cand_sum)
    df["growth_since_prev"] = df.cand_sum / df.prev_cand_sum - 1
    new_evidence = pd.Series(evidence, index=df.index) != df.race_key.map(prev.evidence).astype(str)
    swing = (df.margin - df.race_key.map(prev.margin)).abs()
    df["count_flag"] = np.where(df.growth_since_prev < -0.001, "votes fell since the previous snapshot",
                                np.where(swing.gt(SWING_FLAG) & df.growth_since_prev.abs().lt(SETTLED_GROWTH),
                                         "margin swung with almost no new votes", ""))
    # an official source whose own report says the count is complete needs no newer timestamp: a finished count stops
    # updating (Wikipedia pages get no such pass: an unedited page proves nothing)
    complete = df["complete"].fillna(False).astype(bool) if "complete" in df else pd.Series(False, index=df.index)
    df["count_stable"] = df.cand_sum.gt(0) & df.prev_cand_sum.notna() & df.growth_since_prev.abs().lt(SETTLED_GROWTH) \
        & (new_evidence | (complete & ~df.source.eq("wikipedia"))) & df.count_flag.eq("")
    # slow-count states: the count must have held within SETTLED_GROWTH of today's for SLOW_COUNT_DAYS
    same = hist.merge(now[["race_key", "source", "day", "cand_sum"]], on=["race_key", "source"], suffixes=("", "_now"))
    same = same[same.day <= same.day_now]
    moved = same[(same.cand_sum / same.cand_sum_now - 1).abs() >= SETTLED_GROWTH].groupby("race_key").day.max()
    first = same.groupby("race_key").day.min()
    plateau_from = pd.to_datetime(df.race_key.map(moved)).add(pd.Timedelta(days=1)).fillna(pd.to_datetime(df.race_key.map(first)))
    held_days = (pd.to_datetime(day) - plateau_from).dt.days
    slow = df.race_key.str.split("|").str[1].isin(SLOW_COUNT)
    df["held_days"] = held_days
    df["count_stable"] = df.count_stable & (~slow | held_days.ge(SLOW_COUNT_DAYS))
    df["settled"] = df.count_stable & df.margin.notna()
    for _, r in df[df.count_flag != ""].iterrows():
        print(f"  [count] {r.race_key}: {r.count_flag} ({r.prev_cand_sum:,.0f} -> {r.cand_sum:,.0f})")
    return df


def main(parse_only=False, resume=False):
    if not parse_only:
        snapshot(resume=resume)
        snapshot_ca(resume=resume)
    for chamber, fn in (("senate", parse_senate), ("house", parse_house)):
        df, cands = fn()
        if chamber == "house":   # official California numbers replace any Wikipedia California rows
            ca, ca_c = parse_ca()
            if len(ca):
                df = pd.concat([df[~df.race_key.isin(ca.race_key)], ca], ignore_index=True)
                cands = pd.concat([cands[~cands.race_key.isin(ca.race_key)], ca_c], ignore_index=True)
        frozen = pd.read_csv(FINAL / f"{chamber}_polls_fundamentals.csv")
        missing = sorted(set(frozen.race_key) - set(df.race_key))
        df = settledness(df, chamber)
        df.to_csv(OUT / f"margins_{chamber}.csv", index=False)
        if chamber == "senate":   # official_senate.py starts from these Wikipedia rows when it swaps in official numbers
            df.to_csv(OUT / "margins_senate_wiki.csv", index=False)
        cands.to_csv(OUT / f"candidates_{chamber}.csv", index=False)
        have = df.margin.notna().sum() if len(df) else 0
        print(f"{chamber}: {len(df)} result boxes, {have} with counts; {len(missing)} frozen races without a box"
              + (f" (e.g. {missing[:6]})" if missing else ""))
        for _, r in df[df.issues.fillna("") != ""].iterrows():
            print(f"  [check] {r.race_key}: {r.issues}")


if __name__ == "__main__":
    main(parse_only=sys.argv[1:] == ["parse"], resume=sys.argv[1:] == ["resume"])
