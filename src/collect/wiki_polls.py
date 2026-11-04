"""Wikipedia's per-race polling tables, as they stood when the final forecast's VoteHub snapshot was taken.

For the poll audit (src/model/poll_audit.py): a second, independently curated record of the polls, to check what
VoteHub (the forecast's poll source) missed or carried that it shouldn't have.

As-of time: the retrieval time in data/raw/votehub/2026-11-03/manifest.json (local ET) converted to UTC. For each race
page, the MediaWiki API gives the revision current at that moment; that revision's HTML is fetched (Parsoid) and
stored under data/raw/wikipedia_polls_asof/ (gitignored, large; the parsed CSV keeps every revision id).

Parsed: general-election polling tables whose columns name both of the race's actual nominees (the frozen forecast's
D-side and Republican nominees, matched by last name), so primaries and hypothetical match-ups drop out. One row per
table row (a poll can have several rows: likely/registered voters, with/without third parties).

Run:  python src/collect/wiki_polls.py [senate|house|all] [parse]
Writes data/scorecard/wiki_polls_<chamber>.csv
"""
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parents[1] / "model"))
from common import ROOT, SESSION, fetch, latest  # noqa: E402
from results import FINAL, OUT, clean, grid, header_labels, text  # noqa: E402
from results_margins import page_titles, section_headings  # noqa: E402

SOURCE = "wikipedia_polls_asof"
VOTEHUB_SNAPSHOT = ROOT / "data/raw/votehub/2026-11-03"
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9


def asof_utc():
    m = json.loads((VOTEHUB_SNAPSHOT / "manifest.json").read_text())
    local = dt.datetime.fromisoformat(m["polls.json"]["retrieved"]).replace(tzinfo=ZoneInfo("America/New_York"))
    return local.astimezone(dt.timezone.utc)


def revision_at(title, when):
    for attempt in range(5):
        r = SESSION.get("https://en.wikipedia.org/w/api.php", timeout=60, params={
            "action": "query", "prop": "revisions", "titles": title.replace("_", " "), "rvlimit": 1, "redirects": 1,
            "rvstart": when.strftime("%Y-%m-%dT%H:%M:%SZ"), "rvdir": "older", "rvprop": "ids|timestamp",
            "format": "json", "formatversion": 2, "maxlag": 5})
        if r.status_code == 429 or "maxlag" in r.text[:200]:
            wait = int(r.headers.get("Retry-After", 0) or 0) or 30 * (attempt + 1)
            print(f"  rate-limited looking up {title}; waiting {wait} s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        pages = r.json()["query"]["pages"]
        revs = pages[0].get("revisions") if pages else None
        return (revs[0]["revid"], revs[0]["timestamp"]) if revs else (None, None)
    raise RuntimeError(f"revision lookup failed for {title}")


def snapshot(chamber, pause=2.0):
    """Look up each page's revision at the as-of time and fetch that revision. Progress is saved after every page, so an
    interrupted run resumes where it stopped."""
    when = asof_utc()
    titles = page_titles()
    keys = titles["senate"].items() if chamber == "senate" else titles["house"].items()
    d = ROOT / "data/raw" / SOURCE / dt.date.today().isoformat()
    d.mkdir(parents=True, exist_ok=True)
    idx_path = d / f"revisions_{chamber}.json"
    index = json.loads(idx_path.read_text())["pages"] if idx_path.exists() else {}
    for k, t in keys:
        if t not in index:
            rev, ts = revision_at(t, when)
            index[t] = {"revision": rev, "rev_timestamp": ts, "key": k}
            idx_path.write_text(json.dumps({"asof_utc": when.isoformat(), "pages": index}, indent=1))
            time.sleep(1.0)
        rev = index[t]["revision"]
        if rev is None:
            continue
        for attempt in range(4):
            try:
                fetch(SOURCE, f"{t}.html", f"https://en.wikipedia.org/api/rest_v1/page/html/{t}/{rev}", skip_existing=True)
                break
            except RuntimeError as e:
                if re.search(r"\b50[0234]\b", str(e)) and attempt >= 1:
                    # rendering an old revision of a very large page times out (FL House, 504, twice): take the same
                    # revision from the action API's parser instead (legacy HTML: no <section> tags, so the parser
                    # rebuilds headings from the preceding <h2>-<h6>)
                    legacy(t, rev, d)
                    break
                if not re.search(r"\b(429|50[0234])\b", str(e)) or attempt == 3:
                    raise
                print(f"  {'rate-limited' if '429' in str(e) else 'server error'} on {t}; waiting {60 * (attempt + 1)} s")
                time.sleep(60 * (attempt + 1))
        time.sleep(pause)
    return idx_path


def legacy(title, rev, d):
    r = SESSION.get("https://en.wikipedia.org/w/api.php", timeout=300, params={
        "action": "parse", "oldid": rev, "prop": "text|revid", "format": "json", "formatversion": 2})
    r.raise_for_status()
    j = r.json()["parse"]
    if int(j["revid"]) != int(rev):
        raise RuntimeError(f"{title}: asked for revision {rev}, got {j['revid']}")
    (d / f"{title}.html").write_text(f"<!-- legacy parser output of revision {rev} -->\n" + j["text"], encoding="utf-8")
    print(f"  {title}: revision {rev} taken from the action API parser")


def headings_before(tb):
    """Heading path for a table in legacy parser HTML (innermost first): the nearest preceding heading of each higher level."""
    out, level = [], 7
    for h in tb.find_all_previous(re.compile(r"^h[2-6]$")):
        lv = int(h.name[1])
        if lv < level:
            out.append(re.sub(r"\[\s*edit\s*\]", "", h.get_text(" ", strip=True)).strip())
            level = lv
            if lv == 2:
                break
    return out


# ---------------- parsing ----------------
def parse_dates(s):
    """'October 21–22, 2026' / 'October 29 – November 1, 2026' / 'Oct 20-23, 2026' / 'May 17, 2026' -> (start, end)."""
    t = clean(s).replace("–", "-").replace("—", "-").replace(" ", " ")
    parts = [p.strip() for p in re.split(r"\s*-\s*", t, maxsplit=1)]
    s_txt, e_txt = (parts[0], parts[1]) if len(parts) == 2 else (parts[0], parts[0])

    def md(x):
        m = re.search(r"([A-Za-z]+)\.?\s+(\d{1,2})", x)
        return (MONTHS.get(m.group(1).lower()), int(m.group(2))) if m and MONTHS.get(m.group(1).lower()) else (None, None)
    yr = re.findall(r"(\d{4})", e_txt) or re.findall(r"(\d{4})", s_txt)
    if not yr:
        return None, None
    ey = int(yr[-1])
    em, ed = md(e_txt)
    sm, sd_ = md(s_txt)
    if em is None:            # "22, 2026": month from the start
        dm = re.match(r"(\d{1,2})", e_txt)
        em, ed = sm, int(dm.group(1)) if dm else None
    if sm is None or em is None or ed is None:
        return None, None
    sy_ = re.findall(r"(\d{4})", s_txt)
    sy = int(sy_[0]) if sy_ else (ey - 1 if sm > em else ey)
    try:
        return dt.date(sy, sm, sd_), dt.date(ey, em, ed)
    except ValueError:
        return None, None


def pct(s):
    """'43%' / '43.5%' / '43' -> float; '—', '–', '' -> NaN."""
    m = re.match(r"^\s*<?\s*(\d+(?:\.\d+)?)\s*%?\s*$", clean(s))
    return float(m.group(1)) if m else np.nan


def lastname(s):
    import unicodedata
    s = re.sub(r"\([^)]*\)", "", str(s))
    s = re.sub(r"\s+(Jr|Sr|III|II|IV)\.?\s*$", "", s).replace(".", " ").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.split()[-1].lower() if s.split() else ""


def nominees(chamber):
    """{race_key: (D-side last names, R last names, D-side name, R name)} from the frozen forecast."""
    f = pd.read_csv(FINAL / f"{chamber}_polls_fundamentals.csv")
    out = {}
    for _, r in f.iterrows():
        if chamber == "senate":
            out[r.race_key] = ({lastname(r.dem)}, {lastname(r.rep)}, r.dem, r.rep)
        else:
            if isinstance(r.get("fixed"), str):
                continue
            ds = [n for n in str(r.dem_cand).split("; ") if n and n != "nan"]
            rs = [n for n in str(r.rep_cand).split("; ") if n and n != "nan"]
            if isinstance(r.get("special_case"), str) and "Kiley" in r.special_case:
                rs = rs + ["Kevin Kiley"]
            if ds and rs:
                out[r.race_key] = ({lastname(n) for n in ds}, {lastname(n) for n in rs}, "; ".join(ds), "; ".join(rs))
    return out


def parse_page(html, chamber, state, noms):
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for ti, tb in enumerate(soup.find_all("table")):
        g = grid(tb)
        labels, nh = header_labels(g)
        if not any("Poll source" in l for l in labels):
            continue
        secs = section_headings(tb) or headings_before(tb)
        if not any(re.match(r"general election", s, re.I) for s in secs):
            continue
        if any(re.search(r"primary|runoff|first round", s, re.I) for s in secs):
            continue
        if chamber == "senate":
            special = any(re.search(r"special", s, re.I) for s in secs)
            cands = [k for k in noms if k.startswith(f"2026|{state}|S|")]
            key = next((k for k in cands if k.endswith("special") == special), cands[0] if len(cands) == 1 else None)
        else:
            h = next((re.match(r"District\s+(\d+)", s) for s in secs if re.match(r"District\s+\d+", s)), None)
            dist = int(h.group(1)) if h else (0 if f"2026|{state}|H|0" in noms else None)
            key = f"2026|{state}|H|{dist}" if dist is not None else None
        if key not in noms:
            continue
        dl, rl, dname, rname = noms[key]
        ci = {j: lastname(l) for j, l in enumerate(labels)}
        dcol = next((j for j, ln in ci.items() if ln in dl), None)
        rcol = next((j for j, ln in ci.items() if ln in rl), None)
        if dcol is None or rcol is None:
            continue
        jsrc, jdate = labels.index(next(l for l in labels if "Poll source" in l)), next((j for j, l in enumerate(labels) if "Date" in l), None)
        jn = next((j for j, l in enumerate(labels) if "Sample" in l), None)
        jround = next((j for j, l in enumerate(labels) if re.search(r"\bround\b", l, re.I)), None)   # ranked-choice polls (Alaska)
        cand_cols = [j for j, l in enumerate(labels) if j not in (jsrc, jdate, jn, jround)
                     and not re.search(r"margin of error|^other|undecided|^lead|^$|\bround\b", l, re.I)]
        for ri, r in enumerate(g[nh:]):
            if len(r) <= max(jsrc, dcol, rcol) or r[jsrc] is None:
                continue
            src = text(r[jsrc])
            if not src or re.search(r"primary election|general election|^$", src, re.I) or r[jsrc] is r[dcol]:
                continue
            s, e = parse_dates(text(r[jdate])) if jdate is not None else (None, None)
            nm = text(r[jn]) if jn is not None and jn < len(r) else ""
            n = re.search(r"([\d,]+)", nm)
            pop = re.search(r"\((LV|RV|A)\)", nm)
            mk = re.search(r"\((D|R)\)\s*$", src)
            answers = {re.sub(r"\s*\([^)]*\)\s*$", "", labels[j]).strip(): pct(text(r[j])) for j in cand_cols if j < len(r)}
            rows.append({"race_key": key, "table": ti, "row": ri, "pollster_raw": src,
                         "pollster": re.sub(r"\s*\((D|R)\)\s*$", "", src).strip(), "marker": mk.group(1) if mk else "",
                         "start": s, "end": e, "sample": int(n.group(1).replace(",", "")) if n else np.nan,
                         "population": pop.group(1).lower() if pop else "", "d": pct(text(r[dcol])), "r": pct(text(r[rcol])),
                         "rcv_round": pct(text(r[jround])) if jround is not None and jround < len(r) else np.nan,
                         "d_label": labels[dcol], "r_label": labels[rcol], "answers": json.dumps(answers)})
    return rows


def parse(chamber):
    idx = json.loads(sorted((ROOT / "data/raw" / SOURCE).glob(f"*/revisions_{chamber}.json"))[-1].read_text())
    noms = nominees(chamber)
    titles = page_titles()[chamber]
    rows = []
    for k, t in titles.items():
        meta = idx["pages"].get(t, {})
        if not meta.get("revision"):
            continue
        st = k.split("|")[1] if chamber == "senate" else k
        html = latest(SOURCE, f"{t}.html").read_text(encoding="utf-8")
        for x in parse_page(html, chamber, st, noms):
            rows.append({**x, "page": t, "revision": meta["revision"], "rev_timestamp": meta["rev_timestamp"]})
    df = pd.DataFrame(rows).drop_duplicates(["race_key", "table", "row", "page"])
    df["asof_utc"] = idx["asof_utc"]
    df.to_csv(OUT / f"wiki_polls_{chamber}.csv", index=False)
    print(f"{chamber}: {len(df)} poll rows from {df.page.nunique()} pages, {df.race_key.nunique()} races; "
          f"undated rows {int(df.end.isna().sum())}")
    return df


if __name__ == "__main__":
    which = [a for a in sys.argv[1:] if a in ("senate", "house", "all")] or ["senate"]
    chambers = ["senate", "house"] if which == ["all"] else which
    for ch in chambers:
        if "parse" not in sys.argv[1:]:
            print(ch, "revisions index:", snapshot(ch))
        parse(ch)
