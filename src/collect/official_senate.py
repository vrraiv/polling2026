"""Official state results for the close Senate races: a cross-check of (and replacement for) the Wikipedia margins.

Races: every Senate race any published version gave the Democratic side between 5% and 95% (17 races), fixed from
data/final/. Each state publishes results in its own system, so each has a small adapter: fetch the state's own
results file (raw copy saved under data/raw/official/<ST>/<date>/), return the Senate contest's candidates and votes.

Margins use exactly the Wikipedia path's definitions (results_margins.margins_rcv): the D-side nominee (an
independent in NE and ID, matched by surname) vs. the leading Republican, two-party; Montana raw best non-Republican
minus Republican; ranked-choice states: the final round once published, first choice until then.

Writes data/scorecard/official_senate.csv: one row per race with the official margin, the Wikipedia margin from the
same day, and the difference. results_margins.py uses the official row in place of Wikipedia's when there is one.

Run:  python src/collect/official_senate.py          (fetch + parse every adapter)
      python src/collect/official_senate.py parse    (re-parse the latest raw copies)
"""
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import ROOT, RAW, SESSION, fetch, latest  # noqa: E402
from results import FINAL, OUT, fold  # noqa: E402
from results_margins import MULTI_CANDIDATE, margins_rcv  # noqa: E402

LO, HI = 0.05, 0.95
# States checked on 2026-11-04 with no official source a script may fetch. Bot checks are never bypassed.
UNAVAILABLE = {
    "AK": "the Division of Elections site requires a human-verification check (and ranked-choice tabulation comes ~15 days after the election)",
    "ME": "the Secretary of State site blocks scripted requests",
    "NH": "the Secretary of State site blocks scripted requests",
    "ID": "the results site requires a browser check",
    "KS": "the election-night results site refuses requests from this network's location",
    "MS": "the state posts no election-night results, only certified PDFs after the canvass",
    "OH": "the Secretary of State results site requires a browser check",
    "FL": "the live results site requires a browser check, and the results archive doesn't have the 2026 general yet",
    "MI": "the results site didn't respond",
}


def close_races():
    v = ["polls_only", "polls_fundamentals", "polls_fundamentals_biasadj"]
    p = pd.DataFrame({x: pd.read_csv(FINAL / f"senate_{x}.csv").set_index("race_key").p_dside for x in v})
    return list(p.index[((p > LO) & (p < HI)).any(axis=1)])


def party_code(p):
    p = str(p or "").strip().lower()
    if re.match(r"^(d|dem|democrat|democratic|dfl|democratic-farmer-labor)\b", p):
        return "D"
    if re.match(r"^(r|rep|gop|republican)\b", p):
        return "R"
    if re.match(r"^(i|ind|independent|npa|npp|no party|nonpartisan|non-partisan|unaffiliated|una)\b", p):
        return "I"
    return "O"


class Adapter:
    """Base: files_for(st) -> [(saved file name, url)]; parse(paths) -> {"candidates", "as_of", "reporting", "url"}."""
    name = ""

    @classmethod
    def files_for(cls, st):
        return []

    @classmethod
    def fetch(cls, st):
        out = []
        for n, u in cls.files_for(st):
            out.append(get(st, n, u))
            time.sleep(1.0)
        return out

    @classmethod
    def saved(cls, st):
        return [latest(f"official/{st}", n) for n, _ in cls.files_for(st)]


# ---------------- adapters ----------------
# Each adapter: fetch(state) -> list of raw file paths; parse(paths) -> {"candidates": [{"name","party","votes"}],
# "as_of": str, "reporting": str, "url": str}. Filled in per state from each state's own results system.
ADAPTERS = {}


def adapter(*states):
    def deco(cls):
        for s in states:
            ADAPTERS[s] = cls
        return cls
    return deco


def get(state, name, url, **kw):
    return fetch(f"official/{state}", name, url, skip_existing=False, **kw)


@adapter("MT")
class Montana(Adapter):
    """Montana Secretary of State election-night results (electionresults.mt.gov). The page is server-rendered; the
    statewide Senate block carries the race and office ids its county JSON service needs. On this site type=SENATE is
    the STATE Senate: the US Senate is RaceName 'UNITED STATES SENATOR' under type=FED. The JSON returns null unless
    party=0 in a general election, and has no timestamp (read it from the page)."""
    name = "Montana Secretary of State"
    PAGE = "https://electionresults.mt.gov/resultsSW.aspx?type=FED&map=CTY"
    DATA = "https://esersws.mt.gov/ResultsAjax.svc/GetMapData?type=FED&category=CTY&raceID={race}&osn={osn}&county=0&party=0"

    @classmethod
    def ids(cls, html):
        i = html.upper().find("UNITED STATES SENATOR")
        if i < 0:
            raise ValueError("no 'UNITED STATES SENATOR' contest on the federal results page")
        m = re.search(r"BuildCounty\('FED',\s*'(\d+)',\s*'(\d+)'", html[i:i + 20000])
        if not m:
            raise ValueError("race/office ids not found next to the US Senate contest")
        return m.group(1), m.group(2)

    @classmethod
    def fetch(cls, st):
        page = get(st, "resultsSW_FED.html", cls.PAGE)
        time.sleep(1.0)
        race, osn = cls.ids(page.read_text(encoding="utf-8", errors="replace"))
        data = get(st, "senate_by_county.json", cls.DATA.format(race=race, osn=osn))
        return [page, data]

    @classmethod
    def saved(cls, st):
        return [latest(f"official/{st}", "resultsSW_FED.html"), latest(f"official/{st}", "senate_by_county.json")]

    @classmethod
    def parse(cls, paths):
        html = Path(paths[0]).read_text(encoding="utf-8", errors="replace")
        rows = json.loads(Path(paths[1]).read_text(encoding="utf-8"))["d"] or []
        if not rows or any(r.get("RaceName", "").upper() != "UNITED STATES SENATOR" for r in rows):
            raise ValueError("county rows missing or not the US Senate contest")
        tot, party = {}, {}
        for r in rows:
            tot[r["calcCandidate"]] = tot.get(r["calcCandidate"], 0) + int(r["calcCandidateVotes"] or 0)
            party[r["calcCandidate"]] = r.get("PartyName") or r.get("PartyCode")
        cnty = {r["CountyID"]: r for r in rows}
        full = sum(int(r.get("PrecinctsReporting") or 0) for r in cnty.values())
        part = sum(int(r.get("PrecinctsPartial") or 0) for r in cnty.values())
        allp = sum(int(r.get("TotalPrecincts") or 0) for r in cnty.values())
        upd = re.search(r"Results last updated:\s*([^<]+)", html)
        return {"candidates": [{"name": n.title(), "party": party[n], "votes": v} for n, v in tot.items()],
                "as_of": (upd.group(1).strip() + " (Montana time)") if upd else None,
                "reporting": f"precincts fully reporting {full}/{allp}, partially {part}", "url": cls.PAGE,
                "complete": allp > 0 and full == allp}


def norm_title(s):
    return re.sub(r"[\s.]+", " ", str(s)).strip().upper()


class Clarity(Adapter):
    """Scytl/Clarity election-night reporting: current_ver.txt -> {ver}/json/en/summary.json (contests: C title, CH choice
    names, P party codes, V votes, T total) + electionsettings.json (websiteupdatedat, precinct counts). Contest keys
    change every election, so the Senate contest is matched on its normalized title."""
    base, title = "", ""

    @classmethod
    def fetch(cls, st):
        ver = get(st, "current_ver.txt", f"{cls.base}/current_ver.txt").read_text().strip()
        time.sleep(1.0)
        a = get(st, "summary.json", f"{cls.base}/{ver}/json/en/summary.json")
        time.sleep(1.0)
        b = get(st, "electionsettings.json", f"{cls.base}/{ver}/json/en/electionsettings.json")
        return [a, b]

    @classmethod
    def saved(cls, st):
        return [latest(f"official/{st}", "summary.json"), latest(f"official/{st}", "electionsettings.json")]

    @classmethod
    def parse(cls, paths):
        summ = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
        sett = json.loads(Path(paths[1]).read_text(encoding="utf-8"))
        hits = [c for c in summ if norm_title(c.get("C")) == norm_title(cls.title)]
        if len(hits) != 1:
            raise ValueError(f"{len(hits)} contests titled {cls.title!r}")
        c = hits[0]
        cands = []
        for name, p, v in zip(c["CH"], c.get("P") or [""] * len(c["CH"]), c["V"]):
            name = re.sub(rf"^{re.escape(p)}\s+", "", name) if p else name   # SC prefixes the party: "REP Darline Graham"
            cands.append({"name": name, "party": p, "votes": int(v)})
        if sum(x["votes"] for x in cands) != int((c.get("T") or [sum(x["votes"] for x in cands)])[0]):
            raise ValueError("candidate votes don't add up to the contest total")
        # timestamp and statewide precinct counts are top-level keys of electionsettings.json (not under "settings")
        return {"candidates": cands, "as_of": sett.get("websiteupdatedat"), "url": cls.base,
                "reporting": f"counties reporting {c.get('PR')}/{c.get('TP')} for this contest; precincts "
                             f"{sett.get('stateprecinctsreporting')}/{sett.get('stateprecinctsparticipating')}",
                # complete only when the statewide precinct counts AND the contest's own county counts agree (Iowa's
                # file said 1659/1659 precincts while the Senate contest showed 95/99 counties)
                "complete": bool(sett.get("stateprecinctsparticipating")) and sett.get("stateprecinctsreporting") == sett.get("stateprecinctsparticipating")
                            and not sett.get("stateprecinctspartiallyreporting") and bool(c.get("TP")) and c.get("PR") == c.get("TP")}


@adapter("SC")
class SouthCarolina(Clarity):
    name = "South Carolina Election Commission (Clarity)"
    base, title = "https://www.enr-scvotes.org/SC/127300", "U.S. Senate"


@adapter("IA")
class Iowa(Clarity):
    name = "Iowa Secretary of State (Clarity)"
    base, title = "https://electionresults.iowa.gov/IA/127077", "United States Senator"


@adapter("GA")
class Georgia(Adapter):
    """Georgia Secretary of State results (results.sos.ga.gov): the election's id comes from the jurisdiction's election
    list (election date 2026-11-03); the data JSON lists ballot items. Candidate names carry '(I)' for incumbent, not
    independent, so the party comes only from party.abbreviation."""
    name = "Georgia Secretary of State"
    API = "https://results.sos.ga.gov/results/public/api"

    @classmethod
    def fetch(cls, st):
        lst = get(st, "jurisdiction.json", f"{cls.API}/jurisdictions/Georgia")
        els = json.loads(lst.read_text(encoding="utf-8"))
        els = els.get("elections", els) if isinstance(els, dict) else els
        eid = next(e["publicElectionId"] for e in els if str(e.get("electionDate", "")).startswith("2026-11-03"))
        time.sleep(1.0)
        return [get(st, "election_data.json", f"{cls.API}/elections/Georgia/{eid}/data")]

    @classmethod
    def saved(cls, st):
        return [latest(f"official/{st}", "election_data.json")]

    @classmethod
    def parse(cls, paths):
        d = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
        en = lambda names: next((n["text"] for n in names if n.get("languageCode", "en").startswith("en")), names[0]["text"] if names else "")
        items = [b for b in d["ballotItems"] if norm_title(en(b["name"])) == "US SENATE" and not b.get("parentJurisdictionName")]
        if len(items) != 1:
            raise ValueError(f"{len(items)} statewide 'US Senate' ballot items")
        b = items[0]
        cands = [{"name": re.sub(r"(\s*\([^)]*\))+\s*$", "", en(o["name"])).strip(), "party": (o.get("party") or {}).get("abbreviation", ""),
                  "votes": int(o["voteCount"])} for o in b["summaryResults"]["ballotOptions"]]
        loc = (d.get("jurisdiction") or {}).get("childLocalities") or []
        full = sum(1 for x in loc if float(x.get("percentReporting") or 0) >= 1.0)
        el = d.get("election", {})
        return {"candidates": cands, "as_of": el.get("asOf"), "url": cls.API + "/elections/Georgia",
                "reporting": f"counties fully reporting {full}/{len(loc)}; official: {el.get('isOfficialResults')}",
                "complete": bool(loc) and full == len(loc)}


@adapter("LA")
class Louisiana(Adapter):
    """Louisiana Secretary of State live results (voterportal.sos.la.gov/graphical): JSON blobs named .htm. Race and
    candidate names in RacesCandidates_Multiparish, votes in Votes_Multiparish, joined on race and choice ids; party
    is the '(PARTY)' suffix of the candidate description."""
    name = "Louisiana Secretary of State"
    DATA = "https://voterportal.sos.la.gov/ElectionResults/ElectionResults/Data?blob=20261103/{}"

    @classmethod
    def files_for(cls, st):
        return [("RacesCandidates_Multiparish.json", cls.DATA.format("RacesCandidates_Multiparish.htm")),
                ("Votes_Multiparish.json", cls.DATA.format("Votes_Multiparish.htm"))]

    @classmethod
    def parse(cls, paths):
        rc = json.loads(Path(paths[0]).read_text(encoding="utf-8"))["Races"]
        vt = json.loads(Path(paths[1]).read_text(encoding="utf-8"))["Races"]
        races = rc["Race"] if isinstance(rc["Race"], list) else [rc["Race"]]
        hit = [r for r in races if norm_title(r.get("GeneralTitle")) == "U S SENATOR" or norm_title(r.get("SpecificTitle")) == "U S SENATOR"]
        if len(hit) != 1:
            raise ValueError(f"{len(hit)} races titled 'U.S. Senator'")
        race = hit[0]
        votes = next(r for r in (vt["Race"] if isinstance(vt["Race"], list) else [vt["Race"]]) if r["ID"] == race["ID"])
        vmap = {c["ID"]: int(c["VoteTotal"]) for c in (votes["Choice"] if isinstance(votes["Choice"], list) else [votes["Choice"]])}
        cands = []
        for c in race["Choice"] if isinstance(race["Choice"], list) else [race["Choice"]]:
            m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", c["Desc"])
            cands.append({"name": (m.group(1) if m else c["Desc"]).replace('"', ""), "party": m.group(2) if m else "", "votes": vmap[c["ID"]]})
        return {"candidates": cands, "as_of": f"{rc.get('WriteTime')} (Louisiana time)", "url": "https://voterportal.sos.la.gov/graphical",
                "reporting": f"precincts {votes.get('PrecinctsReporting')}/{votes.get('PrecinctsExpected')}, absentee "
                             f"{votes.get('NumAbsenteeReporting')}/{votes.get('NumAbsenteeExpected')}",
                "complete": votes.get("PrecinctsReporting") == votes.get("PrecinctsExpected") and votes.get("NumAbsenteeReporting") == votes.get("NumAbsenteeExpected")}


@adapter("TX")
class Texas(Adapter):
    """Texas Secretary of State election-night returns (Civix app linked from sos.state.tx.us). Every section of the
    election JSON is base64-wrapped JSON. The app's 'current election' pointer is stale, so the November 2026 general's
    id comes from electionInfo['2026']['GE'] in the constants."""
    name = "Texas Secretary of State (Civix election-night returns)"
    API = "https://goelect.txelections.civixapps.com/api-ivis-system/api/s3/enr"

    @staticmethod
    def unwrap(x):
        import base64
        return json.loads(base64.b64decode(x))

    @classmethod
    def election_id(cls, consts):
        """electionInfo['2026']['GE'] is {id: {"ID", "N" (name), ...}}: take the November general."""
        ge = consts.get("electionInfo", {}).get("2026", {}).get("GE") or {}
        hits = [v for v in ge.values() if isinstance(v, dict) and "GENERAL" in str(v.get("N", "")).upper()]
        if len(hits) != 1:
            raise ValueError(f"{len(hits)} 2026 general elections in the constants: {[v.get('N') for v in hits]}")
        return str(hits[0]["ID"])

    @classmethod
    def fetch(cls, st):
        c = get(st, "electionConstants.json", f"{cls.API}/electionConstants")
        eid = cls.election_id(cls.unwrap(json.loads(c.read_text(encoding="utf-8"))["upload"]))
        time.sleep(1.0)
        return [get(st, "election.json", f"{cls.API}/election/{eid}")]

    @classmethod
    def saved(cls, st):
        return [latest(f"official/{st}", "election.json")]

    @classmethod
    def parse(cls, paths):
        d = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
        fed, home = cls.unwrap(d["Federal"]), cls.unwrap(d["Home"])
        races = [r for r in fed["Races"] if norm_title(r["N"]) == "U S SENATOR"]
        if len(races) != 1:
            raise ValueError(f"{len(races)} races named 'U. S. SENATOR'")
        r = races[0]
        cands = [{"name": c["N"].title(), "party": c.get("P", ""), "votes": int(c["V"])} for c in r["C"]] if "C" in r else \
                [{"name": c["N"].title(), "party": c.get("P", ""), "votes": int(c["V"])} for c in r["Candidates"]]
        if "T" in r and sum(c["votes"] for c in cands) != int(r["T"]):
            raise ValueError("candidate votes don't add up to the race total")
        cr = home.get("CountiesReporting", {})
        # LastUpdatedTime tracks the server clock (it sat within a minute of each response), so it can't show whether the
        # count moved: the "as of" evidence is a fingerprint of the Senate numbers themselves, which only changes when
        # they do. A stalled feed therefore never looks freshly updated; Texas settles through its own "complete" flag.
        import hashlib
        fp = hashlib.sha1(json.dumps(cands, sort_keys=True).encode()).hexdigest()[:12]
        return {"candidates": cands, "as_of": f"Senate numbers {fp} (server time {home.get('LastUpdatedTime')})".split(" (server")[0],
                "server_time": home.get("LastUpdatedTime"), "url": "https://goelect.txelections.civixapps.com/ivis-enr-ui/races",
                "reporting": f"counties reporting {cr.get('CR')}/{cr.get('CT')}", "complete": bool(cr.get("CT")) and cr.get("CR") == cr.get("CT")}


@adapter("MN")
class Minnesota(Adapter):
    """Minnesota Secretary of State media files: a semicolon-delimited text file per office (no header): name f[7],
    party f[10], precincts reporting/total f[11]/f[12], votes f[13], office total f[15]. The file has no timestamp; the
    HTTP Last-Modified header is kept beside it."""
    name = "Minnesota Secretary of State (media text files)"
    URL = "https://electionresultsfiles.sos.mn.gov/20261103/ussenate.txt"

    @classmethod
    def fetch(cls, st):
        from common import raw_dir
        r = SESSION.get(cls.URL, timeout=60)
        r.raise_for_status()
        d = raw_dir(f"official/{st}")
        (d / "ussenate.txt").write_bytes(r.content)
        (d / "ussenate.headers.json").write_text(json.dumps({"Last-Modified": r.headers.get("Last-Modified"), "url": cls.URL}))
        return [d / "ussenate.txt", d / "ussenate.headers.json"]

    @classmethod
    def saved(cls, st):
        return [latest(f"official/{st}", "ussenate.txt"), latest(f"official/{st}", "ussenate.headers.json")]

    @classmethod
    def parse(cls, paths):
        lines = [l.split(";") for l in Path(paths[0]).read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        rows = [f for f in lines if len(f) >= 16 and norm_title(f[4]) == "U S SENATOR"]
        if not rows:
            raise ValueError("no 'U.S. Senator' rows")
        cands = [{"name": f[7], "party": f[10], "votes": int(f[13])} for f in rows]
        if sum(c["votes"] for c in cands) != int(rows[0][15]):
            raise ValueError("candidate votes don't add up to the office total")
        h = json.loads(Path(paths[1]).read_text())
        return {"candidates": cands, "as_of": h.get("Last-Modified"), "url": cls.URL,
                "reporting": f"precincts {rows[0][11]}/{rows[0][12]}", "complete": rows[0][11].strip() == rows[0][12].strip()}


@adapter("NE")
class Nebraska(Adapter):
    """Nebraska Secretary of State results: statewide CSV export (its CurrentDateTime is the export time, so the data
    time is read from the results page). Osborn's party code is PET (petition); the D side is matched by surname."""
    name = "Nebraska Secretary of State"
    CSV = "https://electionresults.nebraska.gov/resultsCSV.aspx?text=All&type=SW&map=CTY"
    PAGE = "https://electionresults.nebraska.gov/"

    @classmethod
    def files_for(cls, st):
        return [("statewide.csv", cls.CSV), ("index.html", cls.PAGE)]

    @classmethod
    def parse(cls, paths):
        import csv
        import io
        rows = list(csv.DictReader(io.StringIO(Path(paths[0]).read_text(encoding="utf-8-sig", errors="replace"))))
        sen = [r for r in rows if "UNITED STATES SENATOR" in norm_title(r.get("RaceName"))]
        if not sen:
            raise ValueError("no 'United States Senator' rows")
        if len({r["RaceID"] for r in sen}) != 1:
            raise ValueError("more than one United States Senator race in the export")
        cands = [{"name": " ".join(r["CandidateName"].split()), "party": r.get("PartyCode", ""), "votes": int(r["CandidateVotes"])} for r in sen]
        html = Path(paths[1]).read_text(encoding="utf-8", errors="replace")
        upd = re.search(r"Results last updated:\s*(?:</span>\s*<span>)?\s*([^<]+)", html, re.I)
        return {"candidates": cands, "as_of": upd.group(1).strip() if upd else None, "url": cls.PAGE,
                "reporting": "precincts " + str(sen[0].get("PrecinctsReporting", "")).strip('="'),
                "complete": (lambda a: len(a) == 2 and a[0] == a[1])(str(sen[0].get("PrecinctsReporting", "")).strip('="').split("/"))}


# ---------------- margins and comparison ----------------
def official_margin(key, cands, frozen):
    """Margin from official candidate rows, with the same rules as the Wikipedia path."""
    f = frozen.loc[key]
    st = key.split("|")[1]
    rows = [{"candidate": c["name"], "party_code": c.get("party_code") or party_code(c.get("party")),
             "votes_first": float(c["votes"]), "votes_final": float(c.get("votes_final", c["votes"])),
             **({"votes_by_round": c["votes_by_round"]} if "votes_by_round" in c else {})} for c in cands]
    m, d, r, dname, k = margins_rcv(rows, dside_name=f["dem"], dside_party=f["dside"], multi=st in MULTI_CANDIDATE)
    return m, d, r, dname, float(sum(x["votes_first"] for x in rows))


def merge_into_margins(off):
    """Official numbers replace Wikipedia's in data/scorecard/margins_senate.csv for the races that have them (the
    Wikipedia margin is kept alongside as a cross-check), then each race's settledness is re-judged on its own source."""
    import results_margins as RM
    path, wpath = OUT / "margins_senate.csv", OUT / "margins_senate_wiki.csv"
    if not wpath.exists():
        return
    m = pd.read_csv(wpath)   # the Wikipedia rows of the last parse (results_margins.py)
    keep = [c for c in m.columns if c not in ("prev_day", "prev_cand_sum", "growth_since_prev", "count_flag", "count_stable", "settled")]
    m = m[keep].copy()
    m["wiki_margin"] = m.margin
    m["complete"] = False
    for c in ("source", "revision", "page_modified", "snapshot", "caption", "dside_candidate", "issues"):
        m[c] = m[c].astype(object) if c in m else None   # text goes into columns pandas may have typed as numbers
    ok = off[(off.status == "ok") & off.margin.notna()] if len(off) else off
    for _, o in ok.iterrows():
        i = m.index[m.race_key == o.race_key]
        if not len(i):
            continue
        m.loc[i, ["source", "revision", "page_modified", "snapshot", "caption", "margin", "dside_votes", "rep_votes",
                  "dside_candidate", "cand_sum", "total", "complete", "issues"]] = \
            [f"official ({o.source})", None, str(o.as_of), o.snapshot, o.url, o.margin, o.dside_votes, o.rep_votes,
             o.dside_candidate, o.cand_sum, o.cand_sum, bool(o.complete),
             "" if not np.isfinite(o.margin_diff_vs_wiki) or abs(o.margin_diff_vs_wiki) <= 0.5
             else f"official margin differs from Wikipedia by {o.margin_diff_vs_wiki:+.2f}"]
    m = RM.settledness(m, "senate")
    m.to_csv(path, index=False)


def main(parse_only=False):
    frozen = pd.read_csv(FINAL / "senate_polls_fundamentals.csv").set_index("race_key")
    wp = OUT / "margins_senate_wiki.csv"
    wiki = pd.read_csv(wp).set_index("race_key") if wp.exists() else pd.DataFrame()
    rows = []
    for key in close_races():
        st = key.split("|")[1]
        row = {"race_key": key, "state": st}
        A = ADAPTERS.get(st)
        if A is None:
            rows.append({**row, "status": f"no scripted source: {UNAVAILABLE.get(st, 'not checked')}; checked at certification"})
            continue
        try:
            paths = A.saved(st) if parse_only else A.fetch(st)
            res = A.parse(paths)
        except Exception as e:  # noqa: BLE001  (one state's site failing must not stop the rest)
            rows.append({**row, "status": f"error: {type(e).__name__}: {str(e)[:160]}"})
            continue
        m, d, r, dname, s = official_margin(key, res["candidates"], frozen)
        w = wiki.loc[key] if key in wiki.index else None
        wm = float(w["margin"]) if w is not None and pd.notna(w.get("margin")) else np.nan
        row.update(status="ok", source=A.name, url=res.get("url"), as_of=res.get("as_of"), reporting=res.get("reporting"),
                   complete=bool(res.get("complete")),
                   margin=m, dside_votes=d, rep_votes=r, dside_candidate=dname, cand_sum=s,
                   candidates=json.dumps(res["candidates"]), snapshot=str(Path(paths[0]).relative_to(ROOT)) if paths else "",
                   wiki_margin=wm, wiki_cand_sum=float(w["cand_sum"]) if w is not None and pd.notna(w.get("cand_sum")) else np.nan,
                   margin_diff_vs_wiki=(m - wm) if np.isfinite(m) and np.isfinite(wm) else np.nan)
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "official_senate.csv", index=False)
    merge_into_margins(df)
    ok = df[df.status == "ok"]
    print(f"official: {len(ok)} of {len(df)} close Senate races; no scripted source: {(df.status.str.startswith('no scripted')).sum()}; "
          f"errors: {(df.status.str.startswith('error')).sum()}")
    for _, r in df.iterrows():
        extra = f"margin {r.margin:+.2f} (Wikipedia {r.wiki_margin:+.2f}; diff {r.margin_diff_vs_wiki:+.2f}) votes {r.cand_sum:,.0f} | {r.reporting} | {r.as_of}" \
            if r.status == "ok" and pd.notna(r.get("margin")) else ""
        print(f"  {r.race_key:20s} {r.status[:60]:60s} {extra}")
    return df


if __name__ == "__main__":
    main(parse_only=sys.argv[1:] == ["parse"])
