"""FEC money for Senate general-election nominees, point-in-time (through the pre-general report).

For each candidate we sum *individual contributions* (itemized + unitemized) over the two-year cycle, using only
reports whose coverage ends on or before the pre-general (12G) report's end date (or Oct 20 if no 12G was filed).
Individual money excludes self-funding, party money and committee transfers. No ytd fields are used (they drift
between amendments); each (committee, report_type, coverage_end) keeps its most recent filing.

  python src/collect/fec_money.py hist     # 2002-2022 nominees from 538 raw_polls (Sen-G)
  python src/collect/fec_money.py 2026     # 2026 nominees from data/processed/senate_polls_only.csv

Raw API responses are cached under data/raw/fec/<date>/money/ so reruns are free.
Writes data/interim/fec_money_hist.csv and data/interim/fec_money_2026.csv
"""
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SESSION, env_key, raw_dir  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
KEY = env_key("fec_api_key", "DEMO_KEY")
API = "https://api.open.fec.gov/v1"
CACHE = raw_dir("fec") / "money"
CACHE.mkdir(parents=True, exist_ok=True)


def get(path, params, tag):
    f = CACHE / f"{tag}.json"
    if f.exists():
        return json.loads(f.read_text())
    out, page = [], 1
    while True:
        for attempt in range(8):
            r = SESSION.get(f"{API}{path}", params={**params, "api_key": KEY, "per_page": 100, "page": page}, timeout=90)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        j = r.json()
        out += j["results"]
        if page >= j["pagination"]["pages"]:
            break
        page += 1
        time.sleep(0.25)
    f.write_text(json.dumps(out))
    time.sleep(0.25)
    return out


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]", " ", s)


SUFFIX = {"JR", "SR", "II", "III", "IV", "MD", "DR"}


def last(name):
    """538 names are 'First M. Last [Jr.]'; FEC names are 'LAST, FIRST M'."""
    s = str(name)
    if "," in s:
        return norm(s.split(",")[0]).split()[-1]
    toks = [t for t in norm(s).split() if t not in SUFFIX]
    return toks[-1] if toks else ""


def candidates(cycle):
    rows = get("/candidates/totals/", {"cycle": cycle, "election_year": cycle, "office": "S", "sort": "-receipts"},
               f"cands_S_{cycle}")
    return pd.DataFrame([{"candidate_id": r["candidate_id"], "fec_name": r["name"], "state": r["state"],
                          "party": r.get("party"), "inc": r.get("incumbent_challenge"),
                          "receipts_full": r.get("receipts") or 0.0} for r in rows])


def money(cand_id, cycle):
    reps = get("/reports/house-senate/", {"candidate_id": cand_id, "cycle": cycle}, f"rep_{cycle}_{cand_id}")
    if not reps:
        return None
    df = pd.DataFrame(reps)
    df["end"] = pd.to_datetime(df.coverage_end_date)
    df["start"] = pd.to_datetime(df.coverage_start_date)
    df["receipt"] = pd.to_datetime(df.receipt_date, errors="coerce")
    df = df.sort_values(["receipt", "most_recent"], na_position="first")
    df = df.drop_duplicates(["committee_id", "report_type", "end"], keep="last")
    g12 = df[df.report_type == "12G"]
    cutoff = g12.end.max() if len(g12) else pd.Timestamp(f"{cycle}-10-20")
    win = df[(df.end <= cutoff) & (df.start >= pd.Timestamp(f"{cycle - 1}-01-01"))]
    num = lambda c: pd.to_numeric(win.get(c), errors="coerce").fillna(0.0)  # noqa: E731
    return {"indiv": float(num("total_individual_contributions_period").sum()),
            "receipts_pit": float(num("total_receipts_period").sum()),
            "self": float((num("candidate_contribution_period") + num("loans_made_by_candidate_period")).sum()),
            "cutoff": str(cutoff.date()), "has_12g": bool(len(g12)), "n_reports": int(len(win))}


def first(name):
    s = str(name)
    if "," in s:
        t = norm(s.split(",", 1)[1]).split()
    else:
        t = norm(s).split()
    return t[0] if t else ""


def match(cands, state, name, party=None):
    st = cands[cands.state == state]
    ln = last(name)
    c = st[st.fec_name.map(last) == ln]
    if not len(c):  # FEC files under a married/legal surname (e.g. 'ARENHOLZ, ASHLEY HINSON')
        c = st[st.fec_name.map(lambda n: ln in norm(n).split())]
    if party and len(c) > 1:
        c2 = c[c.party.fillna("").str.startswith(party[:3])]
        c = c2 if len(c2) else c
    if len(c) > 1:  # same surname: first name decides (SC 2026 Darline vs Lindsey Graham)
        fn = first(name)
        c2 = c[c.fec_name.map(first) == fn]
        if not len(c2):
            c2 = c[c.fec_name.map(lambda n: first(n).startswith(fn) or fn.startswith(first(n)))]
        c = c2 if len(c2) else c
    if len(c) > 1:  # still tied (AK 2026, two Dan Sullivans): the incumbent, else the bigger raiser
        inc = c[c.inc == "I"]
        c = inc if len(inc) == 1 else c.sort_values("receipts_full", ascending=False)
    return c.iloc[0] if len(c) else None


def build(races, cycle_col="cycle"):
    out = []
    cache = {}
    for _, r in races.iterrows():
        cy = int(r[cycle_col])
        if cy not in cache:
            cache[cy] = candidates(cy)
        row = {k: r[k] for k in races.columns}
        for side in ["d", "r"]:
            m = match(cache[cy], r.state, r[f"{side}_name"], r.get(f"{side}_party"))
            if m is None:
                row[f"{side}_fec"] = None
                continue
            row[f"{side}_fec"], row[f"{side}_inc"] = m.candidate_id, m.inc
            mo = money(m.candidate_id, cy) or {}
            for k, v in mo.items():
                row[f"{side}_{k}"] = v
        out.append(row)
        print(cy, r.state, r.d_name, "|", r.r_name, "|", row.get("d_indiv"), row.get("r_indiv"), flush=True)
    return pd.DataFrame(out)


def hist():
    f = next((ROOT / "data/raw/538_github").glob("*/raw_polls.csv"))
    p = pd.read_csv(f, low_memory=False)
    p = p[(p.type_simple == "Sen-G") & (p.cycle % 2 == 0) & (p.cycle >= 2002)]
    races = p.drop_duplicates("race_id")[["cycle", "race_id", "race", "location", "cand1_name", "cand1_party",
                                          "cand2_name", "cand2_party"]]
    races = races.rename(columns={"location": "state", "cand1_name": "d_name", "cand1_party": "d_party",
                                  "cand2_name": "r_name", "cand2_party": "r_party"})
    races = races[races.r_party == "REP"]          # need an R opponent
    races["d_party"] = races.d_party.map({"DEM": "DEM", "IND": "IND"}).fillna(races.d_party)
    d = build(races)
    d.to_csv(ROOT / "data/interim/fec_money_hist.csv", index=False)
    print("wrote", len(d))


def y2026():
    s = pd.read_csv(ROOT / "data/processed/senate_polls_only.csv")
    races = pd.DataFrame({"cycle": 2026, "race_key": s.race_key, "state": s.state, "d_name": s.dem, "r_name": s.rep,
                          "d_party": s.dside.map({"D": "DEM", "I": "IND"}), "r_party": "REP"})
    d = build(races)
    d.to_csv(ROOT / "data/interim/fec_money_2026.csv", index=False)
    print("wrote", len(d))


if __name__ == "__main__":
    for w in sys.argv[1:] or ["hist", "2026"]:
        {"hist": hist, "2026": y2026}[w]()
