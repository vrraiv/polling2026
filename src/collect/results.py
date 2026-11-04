"""Snapshot + parse 2026 results from Wikipedia for the post-election scorecard.

Kept apart from the forecast's inputs: snapshots go to data/raw/wikipedia_results/<date>/ (the forecast reads
data/raw/wikipedia/, never this), parsed tables to data/scorecard/. Nothing in data/interim, data/processed or
data/final is read for writing or touched.

Stage 1 (now): called winners. A race counts as called only when two independent markers on the overview pages agree:
  - the green-tick winner markup in the Candidates cell, and
  - the status text ("Democratic gain", "Republican hold", "Incumbent re-elected", "Interim appointee elected").
Stale status strings left over from the primaries ("Incumbent renominated", "advanced to general") imply no winner, so
those races stay pending. Every disagreement is printed. Races are matched to the frozen forecast by state, district and
regular/special, never by candidate name (Alaska has two Dan Sullivans); names are only compared as a warning.
Stage 2 (once Wikipedia fills in the general-election boxes): vote counts -> two-party margins. Not written yet.

Vandalism guard: if a race that was called in the previous parse changes winner, stop unless ALLOW_RESULT_CHANGES=1.

Run:  python src/collect/results.py            (snapshot + parse)
      python src/collect/results.py parse      (re-parse the latest snapshot)
"""
import os
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, fetch, latest  # noqa: E402
from wiki import STATE_ABBR, clean, party_code  # noqa: E402

SOURCE = "wikipedia_results"
PAGES = {"senate": "2026_United_States_Senate_elections", "house": "2026_United_States_House_of_Representatives_elections"}
FINAL = ROOT / "data" / "final"
OUT = ROOT / "data" / "scorecard"
OUT.mkdir(parents=True, exist_ok=True)
LOC = re.compile(r"^(.+?)\s+(\d+|at-large)$")


def snapshot():
    for p in PAGES.values():
        fetch(SOURCE, p + ".html", f"https://en.wikipedia.org/api/rest_v1/page/html/{p}", skip_existing=False)


def load(page):
    path = latest(SOURCE, PAGES[page] + ".html")
    html = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")
    rev = re.search(r"Special:Redirect/revision/(\d+)", html[:2000])
    mod = soup.find("meta", property="dc:modified")
    return soup, {"page": PAGES[page], "revision": int(rev.group(1)) if rev else None,
                  "page_modified": mod["content"] if mod else None, "snapshot": str(path.relative_to(ROOT))}


def _span(c, k):
    m = re.match(r"\d+", str(c.get(k, "1") or "1"))
    return int(m.group()) if m else 1


def grid(table):
    """Rows of a table with rowspan/colspan expanded, so every row has one entry per column."""
    out, pending = [], {}
    for tr in [tr for tr in table.find_all("tr") if tr.find_parent("table") is table]:
        cells, row, ci, col = tr.find_all(["th", "td"], recursive=False), [], 0, 0
        while ci < len(cells) or any(k >= col for k in pending):
            if col in pending:
                n, c = pending.pop(col)
                if n > 1:
                    pending[col] = (n - 1, c)
                row.append(c)
                col += 1
            elif ci < len(cells):
                c = cells[ci]; ci += 1
                rs = _span(c, "rowspan")
                for _ in range(_span(c, "colspan")):
                    if rs > 1:
                        pending[col] = (rs - 1, c)
                    row.append(c)
                    col += 1
            else:
                row.append(None)
                col += 1
        out.append(row)
    return out


def text(c):
    return clean(c.get_text(" ", strip=True)) if c is not None else ""


def header_labels(rows):
    """Column labels from the leading all-<th> rows."""
    hdr = []
    for r in rows:
        if r and all(c is not None and c.name == "th" for c in r):
            hdr.append(r)
        else:
            break
    n = max((len(r) for r in rows), default=0)
    labels = []
    for j in range(n):
        parts = [text(r[j]) for r in hdr if j < len(r)]
        labels.append(" ".join(dict.fromkeys(p for p in parts if p)))
    return labels, len(hdr)


def col(labels, *keys):
    for j, l in enumerate(labels):
        if all(k.lower() in l.lower() for k in keys):
            return j
    return None


def candidates(cell):
    """[(name, party_code, party_text, is_winner)] from a Candidates cell."""
    out = []
    for li in cell.find_all("li") or [cell]:
        li = BeautifulSoup(str(li), "lxml")  # work on a copy
        win = bool(li.find("img", alt=re.compile(r"green tick|check", re.I)))
        for s in li.find_all("span", style=re.compile(r"display:\s*none")):
            win = win or s.get_text(strip=True) == "Y"
            s.decompose()
        for s in li.find_all("sup"):
            s.decompose()
        t = clean(li.get_text(" ", strip=True)).replace("▌", "").strip()
        m = re.match(r"^(.+?)\s*\(([^()]+)\)\s*$", t) or re.match(r"^(.+?)\s*\(([^()]+)\)", t)
        if m:
            out.append((re.sub(r"\s+", " ", m.group(1)).strip(), party_code(m.group(2).strip()), m.group(2).strip(), win))
    return out


def implied_winner(status, inc_party):
    """Party the status text says won, or None if it doesn't say (stale primary-season text, TBD, retiring...)."""
    m = re.search(r"\b(Democratic|DFL|Republican|Independent)\b[^.]{0,20}?\b(hold|gain)\b", status)
    if m:
        return party_code(m.group(1))
    if re.search(r"\bre-?elected\b|\bappointee elected\b|\belected to (?:a )?full term\b", status, re.I) \
            and not re.search(r"lost re-?election", status, re.I):
        return inc_party if inc_party in ("D", "R", "I") else None
    return None


def decide(cands, status, inc_party):
    winners = [c for c in cands if c[3]]
    tick = winners[0] if len(winners) == 1 else None
    imp = implied_winner(status, inc_party)
    if len(winners) > 1:
        flag = "multiple_ticks"
    elif tick and imp:
        flag = "agree" if tick[1] == imp else "conflict"
    elif tick:
        flag = "tick_only"
    elif imp:
        flag = "status_only"
    else:
        flag = "pending"
    called = flag == "agree"
    return dict(called=called, flag=flag, winner_name=tick[0] if tick else "", winner_party=tick[1] if tick else "",
                winner_party_text=tick[2] if tick else "", status_party=imp or "", status=status,
                candidates="; ".join(f"{n} ({p})" for n, p, _, _ in cands))


def senate():
    soup, prov = load("senate")
    frozen = pd.read_csv(FINAL / "senate_polls_fundamentals.csv").set_index("race_key")
    rows = []
    for table in soup.find_all("table"):
        g = grid(table)
        labels, nh = header_labels(g)
        cc, sc, stc = col(labels, "Candidates"), col(labels, "Results") or col(labels, "Status"), col(labels, "State")
        if cc is None or sc is None or stc is None or col(labels, "Ratings") is not None:
            continue
        for r in g[nh:]:
            if max(stc, cc, sc) >= len(r) or r[cc] is None:
                continue
            st_raw = text(r[stc])
            st = re.sub(r"\s*\(.*\)", "", st_raw).strip()
            if st not in STATE_ABBR:
                continue
            special = bool(re.search(r"\(Class \d\)|special", st_raw, re.I))
            key = f"2026|{STATE_ABBR[st]}|S|{'special' if special else 'regular'}"
            inc = frozen.inc_party.get(key, "")
            rows.append(dict(race_key=key, state=STATE_ABBR[st], special=special,
                             **decide(candidates(r[cc]), text(r[sc]), inc), **prov))
    return check(pd.DataFrame(rows), frozen, "senate")


def house():
    soup, prov = load("house")
    frozen = pd.read_csv(FINAL / "house_polls_fundamentals.csv").set_index("race_key")
    rows = []
    for table in soup.find_all("table"):
        g = grid(table)
        labels, nh = header_labels(g)
        cc, sc, lc = col(labels, "Candidates"), col(labels, "Status"), col(labels, "Location")
        if cc is None or sc is None or lc is None or col(labels, "2026 PVI") is None:
            continue
        for r in g[nh:]:
            if max(lc, cc, sc) >= len(r) or r[cc] is None:
                continue
            m = LOC.match(text(r[lc]).replace(" ", " "))
            if not m or m.group(1) not in STATE_ABBR:
                continue
            st, dist = STATE_ABBR[m.group(1)], 0 if m.group(2) == "at-large" else int(m.group(2))
            key = f"2026|{st}|H|{dist}"
            inc = frozen.inc_party.get(key, "")
            rows.append(dict(race_key=key, state=st, district=dist, **decide(candidates(r[cc]), text(r[sc]), inc), **prov))
    df = pd.DataFrame(rows)
    # two incumbents paired in one district appear as two rows sharing the Candidates cell: keep one row per district,
    # preferring a row whose status names the winner
    df["_rank"] = df.flag.map({"agree": 0, "conflict": 1, "multiple_ticks": 1, "tick_only": 2, "status_only": 3, "pending": 4})
    df = df.sort_values("_rank").drop_duplicates("race_key").drop(columns="_rank")
    return check(df, frozen, "house")


def fold(s):
    """Lower-case and strip accents, for name comparisons (García = Garcia)."""
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).lower()


def check(df, frozen, chamber):
    missing = sorted(set(frozen.index) - set(df.race_key))
    extra = sorted(set(df.race_key) - set(frozen.index))
    dup = df.race_key[df.race_key.duplicated()].tolist()
    if missing or extra or dup:
        raise SystemExit(f"{chamber}: races don't match the frozen forecast: missing {missing} extra {extra} duplicated {dup}")
    df = df.set_index("race_key").loc[frozen.index].reset_index()
    # name check (warning only): the called winner should be one of the frozen nominees
    names = {"senate": ("dem", "rep"), "house": ("dem_cand", "rep_cand")}[chamber]
    for _, r in df[df.called].iterrows():
        f = frozen.loc[r.race_key]
        nominees = " ; ".join(str(f.get(c, "")) for c in names) + " ; " + str(f.get("ind_cand", ""))
        last = fold(r.winner_name.split()[-1]) if r.winner_name else ""
        if last and last not in fold(nominees):
            print(f"  [name check] {r.race_key}: winner {r.winner_name!r} is not among frozen nominees {nominees!r}")
    path = OUT / f"results_{chamber}.csv"
    guard(df, path)
    df.to_csv(path, index=False)
    c = df.flag.value_counts().to_dict()
    print(f"{chamber}: {int(df.called.sum())} of {len(df)} called (rev {df.revision.iloc[0]}, page modified {df.page_modified.iloc[0]}); flags {c}")
    for _, r in df[df.flag.isin(["conflict", "multiple_ticks", "tick_only", "status_only"])].iterrows():
        print(f"  [{r.flag}] {r.race_key}: tick {r.winner_name!r} ({r.winner_party}) vs status {r.status!r}")
    return df


def guard(new, path):
    if not path.exists():
        return
    old = pd.read_csv(path).set_index("race_key")
    hits = []
    for _, r in new[new.called].iterrows():
        if r.race_key in old.index and bool(old.loc[r.race_key, "called"]) and old.loc[r.race_key, "winner_party"] != r.winner_party:
            hits.append(f"{r.race_key}: {old.loc[r.race_key, 'winner_party']} -> {r.winner_party}")
    uncalled = [k for k in old.index[old.called.astype(bool)] if not new.set_index("race_key").loc[k, "called"]]
    for k in uncalled:
        print(f"  [result change] {k} was called, now isn't")
    if hits and os.environ.get("ALLOW_RESULT_CHANGES") != "1":
        raise SystemExit("STOP: called winners changed since the last parse: " + "; ".join(hits) +
                         ". Check the Wikipedia revision history; rerun with ALLOW_RESULT_CHANGES=1 if legitimate.")


if __name__ == "__main__":
    if sys.argv[1:] != ["parse"]:
        snapshot()
    senate()
    house()
