"""Governor data for the governors model (PLAN.md, "After the scorecard", item 4).

  history  every gubernatorial election 1998-2025 (even and odd years) from Wikipedia's yearly overview pages
           ("YYYY United States gubernatorial elections"): state, incumbent and party, the result text (re-elected,
           term-limited, lost...), and every candidate's party and vote share. Unpolled races included.
           -> data/interim/governor_history.csv
  pres     state presidential results 1992-2024 from the yearly presidential election pages ("Results by state"),
           for a state lean on every state (the polling data's lean exists only where presidential polls did).
           -> data/interim/state_presidential.csv
  2026     the 2026 races as Wikipedia stood when the final forecast's VoteHub snapshot was taken (Nov 3, before polls
           closed; same as-of time as src/collect/wiki_polls.py): incumbent, party, status, nominees, the ratings
           table's PVI. No results: 2026 governors are a held-out test (PLAN.md), scored once after certification.
           -> data/interim/governor_2026_races.csv

Pages are fetched through the MediaWiki action API (with their revision ids, kept in every output row) and cached in
data/raw/wikipedia_hist/<date>/ (the yearly House pages live there too). A cached page is reused; delete it to refetch.

Run:  python src/collect/governors.py [history|pres|2026|all]   (default all; fetches what isn't cached, then parses)
      python src/collect/governors.py check                     validation report on the parsed files
"""
import json
import re
import sys
import time
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import RAW, ROOT, SESSION, raw_dir  # noqa: E402
from wiki import STATE_ABBR, party_code  # noqa: E402

SOURCE = "wikipedia_hist"
GOV_YEARS = range(1998, 2026)
PRES_YEARS = range(1992, 2025, 4)
INTERIM = ROOT / "data" / "interim"
# Races where the anti-Republican candidate wasn't a Democrat on the overview page; they count as the D side (as the
# Senate model treats Osborn). Found by listing races without both a Democrat and a Republican.
DSIDE_OVERRIDES = {
    (2014, "AK"): ("Bill Walker", "independent on a unity ticket; the Democratic nominee withdrew to be his running mate"),
    (2020, "VT"): ("David Zuckerman", "Progressive/Democratic fusion nominee, listed only as Progressive on the overview page"),
}
MULTI_PCT = 15.0   # a third candidate at or above this share flags the race as multi-candidate
STATE_NAMES = {**STATE_ABBR, "District of Columbia": "DC", "Washington, D.C.": "DC", "D.C.": "DC"}
API = "https://en.wikipedia.org/w/api.php"


# ---------------- fetching ----------------
def _revids_path(d):
    return d / "revisions_governors.json"


def get_page(title, oldid=None, cache_name=None):
    """(html, revid). Cached as <title>.html in the latest data/raw/wikipedia_hist/<date>/ that has it; revision ids in
    revisions_governors.json beside it."""
    name = (cache_name or title) + ".html"
    hits = sorted((RAW / SOURCE).glob(f"*/{name}"))
    if hits:
        revs = json.loads(_revids_path(hits[-1].parent).read_text()) if _revids_path(hits[-1].parent).exists() else {}
        return hits[-1].read_text(encoding="utf-8"), revs.get(name)
    params = {"action": "parse", "prop": "text|revid", "format": "json", "formatversion": 2, "maxlag": 5}
    params.update({"oldid": oldid} if oldid else {"page": title, "redirects": 1})
    for attempt in range(6):
        r = SESSION.get(API, params=params, timeout=120)
        if r.status_code == 429 or "maxlag" in r.text[:200]:
            wait = int(r.headers.get("Retry-After", 0) or 0) or 20 * (attempt + 1)
            print(f"  rate-limited on {title}; waiting {wait} s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        j = r.json()
        if "error" in j:
            raise RuntimeError(f"{title}: {j['error'].get('info')}")
        break
    else:
        raise RuntimeError(f"fetch failed for {title}")
    d = raw_dir(SOURCE)
    (d / name).write_text(j["parse"]["text"], encoding="utf-8")
    revs = json.loads(_revids_path(d).read_text()) if _revids_path(d).exists() else {}
    revs[name] = j["parse"]["revid"]
    _revids_path(d).write_text(json.dumps(revs, indent=1, sort_keys=True))
    time.sleep(3)   # polite pacing between uncached fetches
    return j["parse"]["text"], j["parse"]["revid"]


def read_tables(html):
    """pd.read_html, after replacing non-numeric rowspan/colspan values (unexpanded templates such as
    '{{{vp_count}}}' on some presidential pages) with 1."""
    html = re.sub(r'(rowspan|colspan)="(?!\d+")[^"]*"', r'\1="1"', html)
    return pd.read_html(StringIO(html))


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]", "", str(s)).replace("\xa0", " ")).strip()


def state_of(cell):
    """('NY', special?) from a State cell such as 'New York', 'Oregon (special)', 'Utah[a]'; None if not a state."""
    s = clean(cell)
    special = bool(re.search(r"special", s, re.I))
    s = re.sub(r"\s*\(.*?\)\s*", "", s).strip()
    return (STATE_NAMES.get(s), special) if s in STATE_NAMES else (None, special)


# ---------------- candidates ----------------
def parse_candidates(text):
    """[(name, party_code, party_text, pct or None)] from a Candidates cell: 'Name (Party) 49.2% Name (Party) 48.0%'
    (with or without the ▌ markers; fusion tickets such as '(Democratic) (Working Families)' count as Democratic;
    pre-election cells have no percentages)."""
    t = clean(text)
    out = []
    has_pct = "%" in t
    chunks = t.split("%") if has_pct else re.split(r"▌", t)
    for ch in chunks:
        ch = ch.replace("▌", " ").strip()
        if not ch:
            continue
        m = re.search(r"([^()]+?)\s*((?:\([^()]+\)\s*)+)(\d+(?:\.\d+)?)?\s*$", ch)
        if not m:
            continue
        name = re.sub(r"^(?:[\d.\s]+|Others?\s+|Write-?ins?\s+|Replacement candidates?\s+)+", "", m.group(1)).strip(" ,;")
        parties = re.findall(r"\(([^()]+)\)", m.group(2))
        codes = [party_code(x.strip()) for p in parties for x in re.split(r"[/,]", p)]   # "Progressive/Democratic" counts as D
        code = "D" if "D" in codes else "R" if "R" in codes else codes[0]
        pct = float(m.group(3)) if has_pct and m.group(3) else None
        if name and not re.fullmatch(r"(Write-?ins?|Others?|Scattering|None of these candidates|Blank.*)", name, re.I):
            out.append((name, code, "/".join(p.strip() for p in parties), pct))
    return out


def colmap(cols):
    """Column positions in an overview table, by header keyword."""
    names = [clean(" ".join(dict.fromkeys(map(str, c))) if isinstance(c, tuple) else c) for c in cols]
    find = lambda *keys: next((i for i, n in enumerate(names) if any(k.lower() in n.lower() for k in keys)), None)
    return {"state": find("State"), "incumbent": find("Incumbent", "Governor"), "party": find("Party"),
            "first": find("First elected", "Elected"), "status": find("Result", "Status"), "cands": find("Candidates", "General election")}


def overview_rows(html, year, revid):
    rows = []
    for t in read_tables(html):
        c = colmap(t.columns)
        if c["state"] is None or c["cands"] is None or c["status"] is None:
            continue
        for _, r in t.iterrows():
            st, special = state_of(r.iloc[c["state"]])
            if not st:
                continue
            cands = parse_candidates(r.iloc[c["cands"]])
            row = {"year": year, "state": st, "special": special,
                   "incumbent": clean(r.iloc[c["incumbent"]]) if c["incumbent"] is not None else None,
                   "inc_party_text": clean(r.iloc[c["party"]]) if c["party"] is not None else None,
                   "first_elected": clean(r.iloc[c["first"]]) if c["first"] is not None else None,
                   "status": clean(r.iloc[c["status"]]), "candidates": json.dumps(cands), "revision": revid}
            row["inc_party"] = party_code(row["inc_party_text"]) if row["inc_party_text"] else None
            rows.append(row)
    return rows


def inc_running(status):
    """True if the incumbent was (or, before the election, will be) on the general-election ballot: re-elected or lost
    it afterwards; renominated or running beforehand. 'Incumbent elected to finish term' (an appointee or successor
    winning a special) counts as running."""
    s = status.lower()
    if re.search(r"term[- ]limited|retir|resign|lost (re)?nomination|lost (the )?(primary|nomination)|renominated but withdrew"
                 r"|did not run|died|vacant|not seeking|recalled", s):
        return False
    return bool(re.search(r"re-?elected|lost re-?election|defeated|lost election|incumbent lost|elected to (a )?full term"
                          r"|elected to finish|renominated|nominated (to|for) (a )?full term|incumbent running|seeking re-?election|running for re-?election", s))


def outcome(cands):
    """Two-party and raw margins (D minus R, points) from the top Democrat and top Republican; the winner's party."""
    with_pct = [c for c in cands if c[3] is not None]
    if not with_pct:
        return {}
    top = lambda code: max((c for c in with_pct if c[1] == code), key=lambda c: c[3], default=None)
    d, r, w = top("D"), top("R"), max(with_pct, key=lambda c: c[3])
    out = {"dem_cand": d[0] if d else None, "rep_cand": r[0] if r else None, "d_pct": d[3] if d else 0.0,
           "r_pct": r[3] if r else 0.0, "winner": w[0], "winner_party": w[1], "winner_pct": w[3],
           "other_pct": round(sum(c[3] for c in with_pct) - (d[3] if d else 0) - (r[3] if r else 0), 2),
           "sum_pct": round(sum(c[3] for c in with_pct), 2)}
    out["margin_raw"] = out["d_pct"] - out["r_pct"]
    out["margin_2p"] = 100 * out["margin_raw"] / (out["d_pct"] + out["r_pct"]) if out["d_pct"] + out["r_pct"] > 0 else np.nan
    out["contested"] = bool(d and r)
    return out


# ---------------- the three datasets ----------------
def history():
    rows = []
    for y in GOV_YEARS:
        try:
            html, rev = get_page(f"{y}_United_States_gubernatorial_elections")
        except RuntimeError as e:
            print(f"  {y}: {e}")
            continue
        got = overview_rows(html, y, rev)
        print(f"  {y}: {len(got)} races (revision {rev})")
        rows += got
    df = pd.DataFrame(rows).drop_duplicates(["year", "state", "special"])
    df["inc_running"] = df.status.map(inc_running)

    def with_dside(y, st, cands):
        o = DSIDE_OVERRIDES.get((y, st))
        return [[c[0], "D" if o and c[0] == o[0] else c[1], c[2], c[3]] for c in cands]
    cands = [with_dside(y, st, json.loads(c)) for y, st, c in zip(df.year, df.state, df.candidates)]
    df["dside_override"] = [DSIDE_OVERRIDES.get((y, st), (None, None))[1] for y, st in zip(df.year, df.state)]
    df = pd.concat([df, pd.DataFrame([outcome(c) for c in cands], index=df.index)], axis=1)
    df["max_other_pct"] = [max([c[3] for c in cs if c[1] not in "DR" and c[3] is not None], default=0.0) for cs in cands]
    df["multi_candidate"] = df.max_other_pct >= MULTI_PCT
    # recall elections: CA 2003 and 2021 say so in their status; WI 2012 (Walker's recall) is listed as an ordinary race
    df["recall"] = df.status.str.contains("recall", case=False) | pd.Series(list(zip(df.year, df.state)), index=df.index).isin({(2012, "WI")})
    df["midterm"] = df.year % 4 == 2
    df["off_year"] = df.year % 2 == 1
    df.to_csv(INTERIM / "governor_history.csv", index=False)
    print(f"governor_history.csv: {len(df)} races, {df.year.min()}-{df.year.max()}")
    return df


def pres():
    rows = []
    for y in PRES_YEARS:
        html, rev = get_page(f"{y}_United_States_presidential_election")
        best = None
        for t in read_tables(html):
            if not isinstance(t.columns, pd.MultiIndex) or len(t) < 50:
                continue
            tops = [clean(" ".join(map(str, c[:-1]))) for c in t.columns]
            subs = [clean(c[-1]) for c in t.columns]
            vote = lambda party: next((i for i, (a, b) in enumerate(zip(tops, subs)) if party in a and b in ("#", "Votes", "Vote", "Votes #")), None)
            di, ri = vote("Democratic"), vote("Republican")
            if di is None or ri is None:
                continue
            sts = t.iloc[:, 0].map(lambda s: STATE_NAMES.get(re.sub(r"\s*\(.*?\)|†|\*", "", clean(s)).strip()))
            k = sts.notna()
            if k.sum() >= 50:
                num = lambda col: pd.to_numeric(t.iloc[:, col].astype(str).str.replace(r"[^\d]", "", regex=True), errors="coerce")
                best = pd.DataFrame({"year": y, "state": sts[k], "d_votes": num(di)[k], "r_votes": num(ri)[k], "revision": rev})
                break
        if best is None:
            print(f"  {y}: no results-by-state table found")
            continue
        best = best.drop_duplicates("state")
        rows.append(best)
        print(f"  {y}: {len(best)} states (revision {rev})")
    df = pd.concat(rows, ignore_index=True)
    df["margin_2p"] = 100 * (df.d_votes - df.r_votes) / (df.d_votes + df.r_votes)
    nat = df.groupby("year").apply(lambda g: 100 * (g.d_votes.sum() - g.r_votes.sum()) / (g.d_votes.sum() + g.r_votes.sum()), include_groups=False)
    df["national_margin_2p"] = df.year.map(nat)
    df["lean_2p"] = df.margin_2p - df.national_margin_2p      # margin units; Cook PVI ~ lean / 2
    df.to_csv(INTERIM / "state_presidential.csv", index=False)
    print(f"state_presidential.csv: {len(df)} rows; national two-party margins", {int(k): round(v, 2) for k, v in nat.items()})
    return df


def races_2026():
    sys.path.insert(0, str(Path(__file__).parent))
    from wiki_polls import asof_utc, revision_at  # noqa: E402
    title = "2026_United_States_gubernatorial_elections"
    when = asof_utc()
    rev, ts = revision_at(title, when)
    html, rev = get_page(title, oldid=rev, cache_name=f"{title}__asof_{rev}")
    rows = overview_rows(html, 2026, rev)
    df = pd.DataFrame(rows).drop_duplicates(["state", "special"])
    df["inc_running"] = df.status.map(inc_running)
    for code, col in (("D", "dem_cand"), ("R", "rep_cand"), ("I", "ind_cand"), ("O", "other_cand")):
        df[col] = [", ".join(c[0] for c in json.loads(x) if c[1] == code) or None for x in df.candidates]
    if df.candidates.map(lambda x: any(c[3] is not None for c in json.loads(x))).any():
        raise SystemExit("STOP: the as-of 2026 page already shows vote shares; the held-out test needs a pre-election revision")
    pvi = {}
    for t in read_tables(html):
        names = [clean(" ".join(dict.fromkeys(map(str, c))) if isinstance(c, tuple) else c) for c in t.columns]
        si = next((i for i, n in enumerate(names) if re.search(r"\bState\b", n)), None)
        pc = next((i for i, n in enumerate(names) if re.search(r"\bPVI\b", n)), None)
        if si is not None and pc is not None:
            for _, r in t.iterrows():
                st, _ = state_of(r.iloc[si])
                m = re.match(r"([DR])\+(\d+)", clean(r.iloc[pc]))
                if st:
                    pvi[st] = (int(m.group(2)) * (1 if m.group(1) == "D" else -1)) if m else (0 if "EVEN" in clean(r.iloc[pc]).upper() else None)
            break
    df["pvi"] = df.state.map(pvi)
    df["asof_utc"], df["revision_timestamp"] = when.strftime("%Y-%m-%dT%H:%M:%SZ"), ts
    df.drop(columns=["candidates"]).to_csv(INTERIM / "governor_2026_races.csv", index=False)
    print(f"governor_2026_races.csv: {len(df)} races as of {when:%Y-%m-%d %H:%M} UTC (revision {rev}, {ts}); PVI for {df.pvi.notna().sum()}")
    return df


def poll_averages():
    """Final-three-week governor poll averages (538 raw polls: every poll in the last 21 days, D vs R two-party), all
    cycles including odd years. Same construction as bias_analysis.load()/race_level(), which keeps even years only."""
    from common import latest  # noqa: E402
    r = pd.read_csv(latest("538_github", "raw_polls.csv"), low_memory=False)
    r = r[r.type_simple == "Gov-G"]
    d1 = (r.cand1_party == "DEM") & (r.cand2_party == "REP")
    d2 = (r.cand1_party == "REP") & (r.cand2_party == "DEM")
    r = r[d1 | d2].copy()
    k = d1[d1 | d2].values
    dp, rp = np.where(k, r.cand1_pct, r.cand2_pct), np.where(k, r.cand2_pct, r.cand1_pct)
    r["poll2"] = 100 * (dp - rp) / (dp + rp)
    g = r.groupby(["cycle", "location", "race_id"]).agg(poll_avg=("poll2", "mean"), n_polls=("poll2", "size")).reset_index()
    g = g.sort_values("n_polls").drop_duplicates(["cycle", "location"], keep="last")    # specials: keep the main race
    g = g.rename(columns={"cycle": "year", "location": "state"})[["year", "state", "poll_avg", "n_polls"]]
    g["poll_source"] = "538 raw_polls"
    return pd.concat([g, votehub_2025()], ignore_index=True)


ELECTION_2025 = pd.Timestamp("2025-11-04")


def votehub_2025():
    """2025 Virginia and New Jersey (538's raw polls end in 2022): VoteHub polls ending in the final 21 days, two-party
    margin between the nominees in governor_history.csv (matched by last name), averaged as above."""
    from common import latest  # noqa: E402
    polls = json.loads(latest("votehub", "polls.json").read_text(encoding="utf-8"))
    polls = polls if isinstance(polls, list) else polls.get("polls", [])
    h = pd.read_csv(INTERIM / "governor_history.csv")
    rows = []
    for _, r in h[h.year == 2025].iterrows():
        name = next(k for k, v in STATE_ABBR.items() if v == r.state)
        last = lambda s: str(s).split()[-1].lower()
        vals = []
        for x in polls:
            if x.get("poll_type") != "governor" or x.get("subject") != f"2025 {name}":
                continue
            if not (ELECTION_2025 - pd.Timedelta(days=21) <= pd.Timestamp(x["end_date"]) <= ELECTION_2025):
                continue
            pick = lambda nm: next((a["pct"] for a in x["answers"] if last(nm) in a["choice"].lower()), None)
            d, rp = pick(r.dem_cand), pick(r.rep_cand)
            if d and rp:
                vals.append(100 * (d - rp) / (d + rp))
        if vals:
            rows.append({"year": 2025, "state": r.state, "poll_avg": float(np.mean(vals)), "n_polls": len(vals), "poll_source": "VoteHub"})
    return pd.DataFrame(rows)


def dataset():
    """One row per governor race 1998-2025 with what the model needs: result, incumbency, state lean from the last
    presidential election before the race (and the one before), the national House environment (even years), the
    president's party and approval, the state's previous governor margin, and the final poll average where polled.
    -> data/interim/governor_dataset.csv"""
    h = pd.read_csv(INTERIM / "governor_history.csv")
    p = pd.read_csv(INTERIM / "state_presidential.csv").set_index(["year", "state"]).lean_2p
    prev_pres = lambda y: max(py for py in PRES_YEARS if py < y)
    h["lean_pres_year"] = h.year.map(prev_pres)
    h["lean_prev"] = [p.get((py, st), np.nan) for py, st in zip(h.lean_pres_year, h.state)]
    h["lean_prev2"] = [p.get((py - 4, st), np.nan) for py, st in zip(h.lean_pres_year, h.state)]
    h["lean_avg2"] = h[["lean_prev", "lean_prev2"]].mean(axis=1)
    nat = pd.read_csv(INTERIM / "house_national_vote.csv").set_index("year").two_party_margin_D
    h["nat_house"] = h.year.map(nat)                     # odd years: no national House vote (NaN)
    f = pd.read_csv(INTERIM / "fundamentals_dataset.csv").set_index("year")
    pres = {**f.pres_party.to_dict(), 2024: "D"}
    h["pres_party"] = [pres.get(y if y % 2 == 0 else y + 1) for y in h.year]   # odd years: whoever holds office then
    h["approval"] = h.year.map(f.approval)
    h["inc"] = np.where(h.inc_running & (h.inc_party == "D"), 1, np.where(h.inc_running & (h.inc_party == "R"), -1, 0))
    h["open_seat"] = ~h.inc_running.astype(bool)
    h = h.sort_values(["state", "year", "special"])
    ok = ~h.recall
    prev = h[ok].groupby("state")[["year", "margin_2p", "winner_party"]].shift(1)
    h.loc[ok, ["prev_gov_year", "prev_gov_margin", "prev_gov_winner"]] = prev.values
    h = h.merge(poll_averages(), on=["year", "state"], how="left")
    h["n_polls"] = h.n_polls.fillna(0).astype(int)
    cols = ["year", "state", "special", "recall", "multi_candidate", "contested", "midterm", "off_year", "margin_2p",
            "margin_raw", "d_pct", "r_pct", "max_other_pct", "dem_cand", "rep_cand", "winner", "winner_party", "dside_override",
            "incumbent", "inc_party", "inc_running", "inc", "open_seat", "lean_pres_year", "lean_prev", "lean_prev2",
            "lean_avg2", "nat_house", "pres_party", "approval", "prev_gov_year", "prev_gov_margin", "prev_gov_winner",
            "poll_avg", "n_polls", "poll_source", "status", "revision"]
    h[cols].to_csv(INTERIM / "governor_dataset.csv", index=False)
    print(f"governor_dataset.csv: {len(h)} races; polled {int((h.n_polls > 0).sum())}; with lean {int(h.lean_prev.notna().sum())}; "
          f"with previous margin {int(h.prev_gov_margin.notna().sum())}")
    return h[cols]


def check():
    """Validation report: counts by year, parse gaps, and margins against the 538 polled-race actuals."""
    h = pd.read_csv(INTERIM / "governor_history.csv")
    print("races by year:", h.groupby("year").size().to_dict())
    print("no vote shares parsed:", h[h.sum_pct.isna()][["year", "state", "status"]].to_dict("records"))
    print("vote shares summing outside 95-101%:", h[(h.sum_pct < 95) | (h.sum_pct > 101)][["year", "state", "sum_pct"]].to_dict("records"))
    print("incumbent running, by year:", h.groupby("year").inc_running.mean().round(2).to_dict())
    print("status texts not classified as running but mentioning 'incumbent':",
          sorted({s for s, r in zip(h.status, h.inc_running) if not r and "incumbent" in s.lower()} - set())[:15])
    b = pd.read_csv(ROOT / "data/final/bias_race_level.csv")
    b = b[b.type_simple == "Gov-G"].rename(columns={"cycle": "year", "location": "state"})
    j = b.merge(h[~h.special], on=["year", "state"])
    for col in ("margin_2p", "margin_raw"):
        dif = j.act - j[col]
        print(f"vs 538 actuals ({len(j)} polled races): {col}: corr {np.corrcoef(j.act, j[col])[0, 1]:.4f}, "
              f"median |diff| {dif.abs().median():.2f}, >1 pt: {(dif.abs() > 1).sum()}")
    p = pd.read_csv(INTERIM / "state_presidential.csv")
    print("presidential: states per year", p.groupby("year").size().to_dict())
    r26 = pd.read_csv(INTERIM / "governor_2026_races.csv")
    print("2026:", len(r26), "races; incumbents running", int(r26.inc_running.sum()), "; missing a D or R nominee:",
          r26[r26.dem_cand.isna() | r26.rep_cand.isna()].state.tolist())


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what == "check":
        check()
    else:
        if what in ("history", "all"):
            history()
        if what in ("pres", "all"):
            pres()
        if what in ("2026", "all"):
            races_2026()
        if what in ("dataset", "all"):
            dataset()
