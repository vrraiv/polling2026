"""Poll data audit: the forecast's poll source (VoteHub, as of the final run) vs. Wikipedia's polling tables at the same
moment (src/collect/wiki_polls.py).

Never changes the frozen forecast. Reads the pinned VoteHub snapshot data/raw/votehub/2026-11-03/polls.json (plus the
AtlasIntel supplement, as the forecast did) and the frozen data/final/ outputs; writes data/scorecard/poll_audit.json
and data/scorecard/poll_audit_polls.csv.

Per race:
  matching     VoteHub polls the model used (same matching rules and windows as the forecast: Senate from Jun 15, House
               from Jul 1) paired one-to-one with Wikipedia's polls. A pair needs end dates within 3 days plus the same
               sample size or a shared pollster name word; ties go to the closest date. A poll can appear as several rows
               (LV/RV, with/without third parties): the numbers are compared with the closest version.
  missing      Wikipedia polls with no VoteHub pair, by cause: in VoteHub but dropped by our name/answer matching (our
               bug), added to VoteHub only after the final run (lag), or not in VoteHub at all.
  VoteHub only polls Wikipedia didn't list at that moment; pollsters on the blocklist (pollster_blocklist.json) are flagged.
  coverage     whether Wikipedia had a general-election table naming both nominees; without one, VoteHub-only polls are
               unverifiable rather than discrepancies.
  what-if      expected margin (mu) for each published version, recomputed in memory with the forecast's own functions:
               as frozen (must reproduce data/final within 0.01 or the audit stops), without blocklisted polls, plus
               missing polls from pollsters VoteHub carries elsewhere in 2026, plus all missing polls. Race probabilities
               are approximate (one race, national error included; not the full simulation).
Run:  python src/model/poll_audit.py
"""
import glob
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
import pollavg as P  # noqa: E402
import forecast as F  # noqa: E402  (read-only: helpers and constants; run() is never called)

ROOT = HERE.parents[1]
FINAL, SC = ROOT / "data" / "final", ROOT / "data" / "scorecard"
# pollavg dates poll ages from "today"; the frozen forecast was made on the lock date. Relative weights don't depend on
# it, but the count of polls in the last 21 days (which sets the poll-average SD, hence the poll weight) does.
P.ASOF = pd.Timestamp((FINAL / "MADE_AT.txt").read_text().strip()[:10])
SNAP = ROOT / "data/raw/votehub/2026-11-03/polls.json"     # pinned: the snapshot the final forecast used
LATER = sorted(glob.glob(str(ROOT / "data/raw/votehub_audit/*/polls.json")))   # a later VoteHub pull, to tell lag from absence
BLOCK = json.loads((SC / "pollster_blocklist.json").read_text())["pollsters"]
SINCE = {"senate": pd.Timestamp("2026-06-15"), "house": pd.Timestamp("2026-07-01")}
VERSIONS = ["polls_only", "polls_fundamentals", "polls_fundamentals_biasadj"]
STOP = {"polling", "poll", "polls", "research", "group", "strategies", "strategy", "insights", "associates", "college", "university",
        "the", "and", "inc", "llc", "partners", "analytics", "survey", "surveys", "consulting", "communications", "public", "opinion",
        "institute", "center", "for", "of", "co", "company", "data", "media", "news", "&", "pac", "action", "fund", "project"}


def tok_list(name):
    """Distinctive words of a pollster name, in order ("Emerson College Polling" -> ["emerson"])."""
    return [t for t in re.findall(r"[a-z0-9]+", str(name).lower()) if t not in STOP and len(t) > 1]


def tokens(name):
    return set(tok_list(name))


def first_tok(name):
    tl = tok_list(name)
    return tl[0] if tl else ""


def blocked(pollster):
    return next((b for b in BLOCK if b["match"] in str(pollster).lower()), None)


def load_votehub_pinned():
    d = json.loads(SNAP.read_text(encoding="utf-8"))
    have = {P._poll_key(x) for x in d}
    for x in json.loads(P.SUPPLEMENT.read_text(encoding="utf-8"))["polls"]:
        if P._poll_key(x) not in have:
            d.append(dict(x, supplement=True))
    for x in d:
        x["end"] = pd.Timestamp(x["end_date"])
    return d


def two_party(d, r):
    return 100.0 * (d - r) / (d + r) if np.isfinite(d) and np.isfinite(r) and d + r > 0 else np.nan


def seat_code(st, d):
    return f"{st}-{int(d):02d}" if int(d) else f"{st}-01"


# ---------------- chamber specifics ----------------
class Senate:
    name, poll_type = "senate", "us-senator"

    def __init__(self, polls):
        self.races = F.senate_races(polls)
        self.rk = self.races.set_index("race_key")
        self.frozen = {v: pd.read_csv(FINAL / f"senate_{v}.csv").set_index("race_key") for v in VERSIONS}
        self.sd_nat = {v: json.loads((FINAL / f"summary_{v}.json").read_text())["national"]["sd_nat_senate_used"] for v in VERSIONS}
        self.keys = list(self.frozen["polls_fundamentals"].index)

    def same_race(self, x, key):
        return x["poll_type"] == self.poll_type and key in self.rk.index and x.get("subject") == f"2026 {self.rk.loc[key, 'state_name']}"

    def model_polls(self, polls, key):
        """The VoteHub polls the forecast averaged for this race (pollavg.senate's rules)."""
        if key not in self.rk.index:
            return []
        r = self.rk.loc[key]
        if not isinstance(r.dem_nominee, str) or not isinstance(r.rep_nominee, str):
            return []
        dl, rl = P.lastname(r.dem_nominee), P.lastname(r.rep_nominee)
        out = []
        for x in polls:
            if self.same_race(x, key) and x["end"] >= SINCE["senate"]:
                a = {P.lastname(y["choice"]): y["pct"] for y in x["answers"]}
                if dl in a and rl in a and len(x["answers"]) >= 2:
                    out.append((x, two_party(a[dl], a[rl])))
        return out

    def stamp(self, d, key):
        return dict(d, poll_type=self.poll_type, subject=f"2026 {self.rk.loc[key, 'state_name']}")

    def mu_versions(self, polls, key):
        out, st = {}, key.split("|")[1]
        if key not in self.rk.index:
            return {v: {"mu": float(self.frozen[v].loc[key, "mu"]), "p": None, "n_polls": 0} for v in VERSIONS}
        row = self.rk.loc[key].copy(); row["race_key"] = key
        for v in VERSIONS:
            f = self.frozen[v].loc[key]
            if st in F.MULTI_CANDIDATE:
                pa = P.senate_multi(polls, row)
                if pa:
                    mu, sd = pa["avg"], np.sqrt(F.pollavg_sd(pa) ** 2 + 3.0 ** 2)
            else:
                pa = P.senate(polls, pd.DataFrame([row])).get(key)
                if pa:
                    lean = F.LEAN_SLOPE * 2 * f["pvi"] if v == "polls_fundamentals_biasadj" and F.ADJ_USE_LEAN else 0.0
                    sd_p = F.pollavg_sd(pa)
                    wp = (1 / sd_p ** 2) / (1 / sd_p ** 2 + 1 / F.SD_SENATE_PRIOR ** 2)
                    mu = wp * (pa["avg"] + lean) + (1 - wp) * f["prior"]
                    sd = 1 / np.sqrt(1 / sd_p ** 2 + 1 / F.SD_SENATE_PRIOR ** 2)
            if not pa:
                out[v] = {"mu": float(f["prior"]), "p": None, "n_polls": 0}
                continue
            tot = np.sqrt(sd ** 2 + self.sd_nat[v] ** 2)
            out[v] = {"mu": float(mu), "p": float(stats.t.cdf(mu / (tot * F.T_SCALE), F.DF_T)), "n_polls": int(pa["n_polls"])}
        return out


class House:
    name, poll_type = "house", "us-representative"

    def __init__(self, polls):
        self.races = F.house_races()
        self.rk = self.races.set_index("race_key")
        self.frozen = {v: pd.read_csv(FINAL / f"house_{v}.csv").set_index("race_key") for v in VERSIONS}
        nat = {v: json.loads((FINAL / f"summary_{v}.json").read_text())["national"] for v in VERSIONS}
        self.sd_nat = {v: F.H_G_NAT * nat[v]["sd_nat_house_used"] for v in VERSIONS}
        self.shift = {v: nat[v].get("bias_shift", 0.0) for v in VERSIONS}
        fv = self.frozen["polls_fundamentals"]
        pub = pd.concat([self.frozen[v].p_dem for v in VERSIONS], axis=1)
        close = ((pub > 0.02) & (pub < 0.98)).any(axis=1) & fv.fixed.isna()
        self.keys = list(fv.index[close])           # the scorecard's close races

    def seat(self, key):
        r = self.rk.loc[key]
        return seat_code(r.state, r.district)

    def same_race(self, x, key):
        return x["poll_type"] == self.poll_type and x.get("seat_name") == self.seat(key)

    def model_polls(self, polls, key):
        """The VoteHub polls the forecast averaged for this district (pollavg.house's rules)."""
        r = self.rk.loc[key]
        dls = [P.lastname(n) for n in str(r.dem_cand).split("; ") if n and n != "nan"]
        rls = [P.lastname(n) for n in str(r.rep_cand).split("; ") if n and n != "nan"]
        out = []
        for x in polls:
            if self.same_race(x, key) and x["end"] >= SINCE["house"]:
                a = {P.lastname(y["choice"]): y["pct"] for y in x["answers"]}
                d = [a[l] for l in dls if l in a]
                rr = [a[l] for l in rls if l in a]
                if len(d) == 1 and len(rr) == 1:
                    out.append((x, two_party(d[0], rr[0])))
        return out

    def stamp(self, d, key):
        return dict(d, poll_type=self.poll_type, seat_name=self.seat(key), subject=None)

    def mu_versions(self, polls, key):
        out = {}
        pa = P.house(polls, self.races[self.races.race_key == key]).get(key)
        for v in VERSIONS:
            f = self.frozen[v].loc[key]
            if not pa:
                out[v] = {"mu": float(f["prior"]), "p": None, "n_polls": 0}
                continue
            sd_p = np.sqrt(F.SD_HOUSE_POLL ** 2 + (max(pa["spread_sd"], 4.0) ** 2) / pa["neff"])
            wp = (1 / sd_p ** 2) / (1 / sd_p ** 2 + 1 / F.SD_HOUSE_DISTRICT ** 2)
            mu = wp * pa["avg"] + (1 - wp) * f["prior"] + self.shift[v] * wp
            sd = 1 / np.sqrt(1 / sd_p ** 2 + 1 / F.SD_HOUSE_DISTRICT ** 2)
            tot = np.sqrt(sd ** 2 + self.sd_nat[v] ** 2)
            out[v] = {"mu": float(mu), "p": float(stats.t.cdf(mu / (tot * F.T_SCALE), F.DF_T)), "n_polls": int(pa["n_polls"])}
        return out


# ---------------- matching ----------------
def wiki_groups(w):
    """Wikipedia rows of one race -> polls (pollster + field dates) with their versions: a survey often appears as
    several rows (likely voters and the full sample with different n, with/without third parties, ranked-choice rounds)."""
    out = []
    for (p, s, e), g in w.groupby(["pollster", "start", "end"], dropna=False, sort=False):
        vers = [{"population": r.population if isinstance(r.population, str) else "", "sample": r["sample"], "d": r.d, "r": r.r,
                 "margin": two_party(r.d, r.r), "answers": r.answers, "d_label": r.d_label, "r_label": r.r_label,
                 "round": r.get("rcv_round", np.nan)} for _, r in g.iterrows()]
        samples = [v["sample"] for v in vers if np.isfinite(v["sample"])]
        out.append({"pollster": p, "marker": g.marker.iloc[0] if isinstance(g.marker.iloc[0], str) else "", "start": s,
                    "end": pd.Timestamp(e) if not pd.isna(e) else pd.NaT, "sample": max(samples) if samples else np.nan,
                    "samples": samples, "versions": vers})
    return out


def same_poll(x, w, end_x):
    """Evidence that VoteHub poll x and Wikipedia poll w are the same survey: end dates within 3 days plus the same
    sample size (any version) or a shared distinctive pollster word. Returns (strength, days apart) or None."""
    if pd.isna(w["end"]):
        return None
    dd = abs((end_x - w["end"]).days)
    if dd > 3:
        return None
    same_n = bool(x.get("sample_size")) and any(int(x["sample_size"]) == int(n) for n in w["samples"])
    same_name = bool(tokens(x["pollster"]) & tokens(w["pollster"]))
    return (2 * same_n + same_name, dd) if (same_n or same_name) else None


def headline_version(w):
    """The version used when a Wikipedia poll is added to an average: the final ranked-choice round if there are rounds,
    then likely voters, then the first row."""
    vs = w["versions"]
    rounds = [v["round"] for v in vs if np.isfinite(v["round"])]
    if rounds:
        vs = [v for v in vs if v["round"] == max(rounds)]
    return next((v for v in vs if v["population"] == "lv"), vs[0])


def pair(vh, wk):
    """Greedy one-to-one pairing of VoteHub polls [(poll, margin)] with Wikipedia poll groups: strongest evidence first,
    then the closest end date, so two polls from one tracking pollster can't claim the same Wikipedia row."""
    cands = []
    for i, (x, _) in enumerate(vh):
        for j, w in enumerate(wk):
            s = same_poll(x, w, x["end"])
            if s:
                cands.append((-s[0], s[1], i, j))
    used_i, used_j, pairs = set(), set(), []
    for _, _, i, j in sorted(cands):
        if i not in used_i and j not in used_j:
            used_i.add(i); used_j.add(j); pairs.append((i, j))
    return pairs


def find_in(polls, w, ch, key):
    """A VoteHub poll for this race (any date, any answers) that looks like Wikipedia poll w."""
    for x in polls:
        if ch.same_race(x, key) and same_poll(x, w, pd.Timestamp(x["end_date"])):
            return x
    return None


def to_votehub(w, ch, key, vh_pollsters):
    """A Wikipedia poll in VoteHub's schema, for the what-if averages. Version: likely voters if listed, else the first
    row. Sponsor flag: Wikipedia's (D)/(R) marker counts as sponsored, except where VoteHub carries the same pollster and
    never lists a sponsor for it (then the forecast's rule for established pollsters applies)."""
    v = headline_version(w)
    nom = lambda lab: re.sub(r"\s*\([^)]*\)\s*$", "", str(lab)).strip()
    dn, rn = nom(v["d_label"]), nom(v["r_label"])
    taken = {P.lastname(dn), P.lastname(rn)}
    # nominees from the identified columns; other candidates only if their surname can't be confused with a nominee's
    # (Alaska lists Dan S. Sullivan, the nominee, and Dan J. Sullivan at 3%)
    answers = [{"choice": dn, "pct": float(v["d"])}, {"choice": rn, "pct": float(v["r"])}] + \
        [{"choice": k, "pct": float(p)} for k, p in json.loads(v["answers"]).items()
         if isinstance(p, (int, float)) and np.isfinite(p) and k not in (dn, rn) and P.lastname(k) not in taken]
    partisan = {"D": "DEM", "R": "REP"}.get(w["marker"]) or None
    vh_same = vh_pollsters.get(first_tok(w["pollster"]), None)
    sponsors = [] if (partisan and vh_same is not None and not vh_same) else ([f"Wikipedia ({w['marker']}) marker"] if partisan else [])
    return ch.stamp({"id": f"wiki-{w['pollster']}-{w['end'].date()}", "pollster": w["pollster"], "population": v["population"] or "lv",
                     "sample_size": int(v["sample"]) if np.isfinite(v["sample"]) else None, "start_date": str(w["start"]),
                     "end_date": str(w["end"].date()), "partisan": partisan, "sponsors": sponsors, "answers": answers,
                     "end": w["end"], "from_wikipedia": True}, key)


# ---------------- the audit ----------------
def load_wiki(ch):
    wiki = pd.read_csv(SC / f"wiki_polls_{ch.name}.csv")
    wiki["end"] = pd.to_datetime(wiki.end)
    wiki["start"] = wiki.start.astype(str)
    if "rcv_round" not in wiki:
        wiki["rcv_round"] = np.nan
    return wiki


def pass1(ch, polls, wiki):
    """Pair each race's polls: {race_key: (VoteHub polls used, Wikipedia rows, Wikipedia polls, pairs, paired j, extra versions)}."""
    per = {}
    for key in ch.keys:
        vh = ch.model_polls(polls, key)
        w_all = wiki[wiki.race_key == key]
        wk = wiki_groups(w_all[w_all.end >= SINCE[ch.name]])
        pairs = pair(vh, wk)
        pj = {j for _, j in pairs}
        # a VoteHub record left over after one-to-one pairing that has the same pollster and end date as a paired
        # Wikipedia poll is another version of that poll (VoteHub sometimes enters LV and RV separately)
        extra = {}
        for i, (x, _) in enumerate(vh):
            if i in {a for a, _ in pairs}:
                continue
            j = next((j for a, j in pairs if tokens(x["pollster"]) & tokens(wk[j]["pollster"]) and abs((x["end"] - wk[j]["end"]).days) <= 1), None)
            if j is not None:
                extra[i] = j
        per[key] = (vh, w_all, wk, pairs, pj, extra)
    return per


def coverage_of(per):
    """How much of each pollster's work (in these races and the window) VoteHub carried, by first distinctive name word."""
    cov, names = {}, {}
    for key, (vh, w_all, wk, pairs, pj, extra) in per.items():
        for j, w in enumerate(wk):
            t = first_tok(w["pollster"])
            c = cov.setdefault(t, [0, 0])
            c[0] += j in pj
            c[1] += 1
            names.setdefault(t, {}).setdefault(w["pollster"], 0)
            names[t][w["pollster"]] += 1
    return cov, names


def audit(ch, polls, later, cov_pool=None):
    """cov_pool: pollster coverage pooled over both chambers (a pollster gets one gap-or-curation verdict)."""
    wiki = load_wiki(ch)
    asof = wiki.asof_utc.iloc[0]
    vh_pollsters = {}   # pollsters VoteHub carries anywhere in 2026 (by first distinctive word) -> lists sponsors for them?
    for x in polls:
        t = first_tok(x["pollster"])
        if t:
            vh_pollsters[t] = vh_pollsters.get(t, False) or bool(x.get("sponsors"))
    asof_day = pd.Timestamp(asof[:10])
    is_out = lambda x: bool(blocked(x["pollster"])) and pd.Timestamp(blocked(x["pollster"])["public_since"]) <= asof_day
    polls_nob = [x for x in polls if not is_out(x)]   # pollsters publicly discredited before the final run, removed

    per = pass1(ch, polls, wiki)
    # a missing poll from a pollster VoteHub mostly carries (>= half its polls in these races, both chambers pooled)
    # is probably a gap; one from a pollster it mostly leaves out is probably its curation
    cov, cov_names = coverage_of(per)
    pool = cov_pool or cov
    carried = lambda name: (lambda c: c[1] > 0 and c[0] / c[1] >= 0.5)(pool.get(first_tok(name), [0, 0]))

    rows, races_out = [], []
    for key, (vh, w_all, wk, pairs, pj, extra) in per.items():
        rec = {"race_key": key, "wikipedia_table": bool(len(w_all)), "n_votehub": len(vh), "n_wikipedia": len(wk),
               "matched": [], "missing": [], "votehub_only": [], "number_mismatch": []}
        for i, j in list(pairs) + list(extra.items()):
            x, m = vh[i]
            w = wk[j]
            diffs = [abs(m - v["margin"]) for v in w["versions"] if np.isfinite(v["margin"])]
            best = min(diffs) if diffs else np.nan
            b = blocked(x["pollster"])
            item = {"pollster": x["pollster"], "wiki_pollster": w["pollster"], "end": x["end_date"], "n": x.get("sample_size"),
                    "votehub_margin": round(m, 2), "closest_wiki_margin_diff": None if np.isnan(best) else round(best, 2),
                    "supplement": bool(x.get("supplement")), "blocklisted": b["name"] if b else "",
                    "extra_version": i in extra}
            rec["matched"].append(item)
            if np.isfinite(best) and best > 1.0:
                rec["number_mismatch"].append(item)
            rows.append({"chamber": ch.name, "race_key": key, "status": "matched", **item})
        miss_w = []
        for j, w in enumerate(wk):
            if j in pj:
                continue
            raw = find_in(polls, w, ch, key)
            used_ids = {id(x) for x, _ in vh}
            if raw is not None and id(raw) in used_ids:
                # the matching VoteHub entry was used and already paired with another Wikipedia row: Wikipedia lists
                # this survey twice (different dates or versions), so nothing is missing
                cause = "listed twice on Wikipedia"
                detail = f"VoteHub's entry (end {raw['end_date']}) is already matched to another row"
            elif raw is not None:
                cause = "in VoteHub, not used by the forecast"
                detail = f"VoteHub end {raw['end_date']}; answers: " + ", ".join(f"{a['choice']} {a['pct']}" for a in raw.get("answers", []))
            elif later and find_in(later, w, ch, key) is not None:
                cause, detail = "added to VoteHub after the final run", ""
            else:
                cause, detail = "not in VoteHub", ""
            if cause == "listed twice on Wikipedia":
                rows.append({"chamber": ch.name, "race_key": key, "status": "duplicate on Wikipedia", "pollster": w["pollster"],
                             "end": str(w["end"].date()), "detail": detail})
                continue
            v0 = headline_version(w)
            c = pool.get(first_tok(w["pollster"]), [0, 0])
            item = {"pollster": w["pollster"], "marker": w["marker"], "end": str(w["end"].date()),
                    "n": None if pd.isna(v0["sample"]) else int(v0["sample"]), "wiki_margin": None if np.isnan(v0["margin"]) else round(v0["margin"], 2),
                    "cause": cause, "detail": detail, "pollster_carried": f"{c[0]} of {c[1]}",
                    "kind": "probably a gap" if carried(w["pollster"]) else "probably VoteHub's choice"}
            rec["missing"].append(item)
            rows.append({"chamber": ch.name, "race_key": key, "status": "missing", **item})
            miss_w.append(w)
        for i, (x, m) in enumerate(vh):
            if i in {a for a, _ in pairs} or i in extra:
                continue
            b = blocked(x["pollster"])
            item = {"pollster": x["pollster"], "end": x["end_date"], "n": x.get("sample_size"), "votehub_margin": round(m, 2),
                    "blocklisted": b["name"] if b else "", "supplement": bool(x.get("supplement")), "verifiable": bool(len(w_all))}
            rec["votehub_only"].append(item)
            rows.append({"chamber": ch.name, "race_key": key, "status": "votehub only", **item})
        # what-if expected margins; the forecast's own functions pick each race's polls from the full list
        add_gaps = [to_votehub(w, ch, key, vh_pollsters) for w in miss_w if carried(w["pollster"])]
        add_all = [to_votehub(w, ch, key, vh_pollsters) for w in miss_w]
        variants = {"as_frozen": polls, "without_blocklisted": polls_nob,
                    "plus_probable_gaps": polls_nob + add_gaps, "plus_all_missing": polls_nob + add_all}
        rec["what_if"] = {k: ch.mu_versions(ps, key) for k, ps in variants.items()}
        for v in VERSIONS:   # the recomputation must reproduce the frozen forecast, or nothing here can be trusted
            got, want = rec["what_if"]["as_frozen"][v]["mu"], float(ch.frozen[v].loc[key, "mu"])
            if abs(got - want) > 0.01:
                raise SystemExit(f"STOP: as-frozen recomputation of {key} ({v}) gives mu {got:.3f}, frozen {want:.3f}")
        rec["mu_change_fv"] = {k: round(rec["what_if"][k]["polls_fundamentals"]["mu"] - rec["what_if"]["as_frozen"]["polls_fundamentals"]["mu"], 3)
                               for k in variants if k != "as_frozen"}
        races_out.append(rec)
    pdf = pd.DataFrame(rows)
    is_sup = pdf["supplement"].fillna(False).astype(bool) if "supplement" in pdf else pd.Series(False, index=pdf.index)
    blk = pdf["blocklisted"].fillna("").astype(str).ne("") if "blocklisted" in pdf else pd.Series(False, index=pdf.index)
    miss = pdf[pdf.status == "missing"]
    tot = {"races": len(races_out), "races_with_wikipedia_table": sum(r["wikipedia_table"] for r in races_out),
           "votehub_polls_used": int(sum(r["n_votehub"] for r in races_out)), "wikipedia_polls": int(sum(r["n_wikipedia"] for r in races_out)),
           "matched_wikipedia_polls": int(sum(len({(m["wiki_pollster"], m["end"]) for m in r["matched"] if not m["extra_version"]}) for r in races_out)),
           "missing": int(len(miss)), "missing_probable_gaps": int((miss.kind == "probably a gap").sum()) if len(miss) else 0,
           "missing_by_cause": miss.cause.value_counts().to_dict() if len(miss) else {},
           "duplicates_on_wikipedia": int((pdf.status == "duplicate on Wikipedia").sum()),
           "votehub_only": int((pdf.status == "votehub only").sum()),
           "votehub_only_unverifiable": int(sum(1 for r in races_out for m in r["votehub_only"] if not m["verifiable"])),
           "blocklisted_used": int(((pdf.status != "missing") & blk).sum()),
           "number_mismatches": int(sum(len(r["number_mismatch"]) for r in races_out)),
           "supplement_polls": int(is_sup.sum()), "supplement_polls_matched": int(((pdf.status == "matched") & is_sup).sum()),
           "supplement_mismatches": [m for r in races_out for m in r["number_mismatch"] if m.get("supplement")],
           "pollster_coverage": [{"pollster": max(cov_names[k], key=cov_names[k].get), "carried": v[0], "on_wikipedia": v[1]}
                                 for k, v in sorted(cov.items(), key=lambda kv: (-kv[1][1], kv[0]))]}
    return {"asof_utc": asof, "votehub_snapshot": str(SNAP.relative_to(ROOT)), "later_votehub": LATER[-1] if LATER else None,
            "window_start": str(SINCE[ch.name].date()), "totals": tot, "races": races_out}, pdf


def main(chambers=("senate", "house")):
    polls = load_votehub_pinned()
    later = json.loads(Path(LATER[-1]).read_text(encoding="utf-8")) if LATER else []
    path = SC / "poll_audit.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    out["blocklist"] = BLOCK
    frames, chs, pool = [], {}, {}
    for name in ("senate", "house"):   # coverage is pooled over both chambers whichever is being re-run
        if not (SC / f"wiki_polls_{name}.csv").exists():
            print(f"{name}: no Wikipedia polls parsed yet (run src/collect/wiki_polls.py {name})")
            continue
        chs[name] = Senate(polls) if name == "senate" else House(polls)
        for t, (a_, b_) in coverage_of(pass1(chs[name], polls, load_wiki(chs[name])))[0].items():
            pool.setdefault(t, [0, 0]); pool[t][0] += a_; pool[t][1] += b_
    for name in chambers:
        if name not in chs:
            continue
        ch = chs[name]
        out[name], pdf = audit(ch, polls, later, cov_pool=pool)
        frames.append(pdf)
        t = out[name]["totals"]
        print(name.upper(), json.dumps({k: v for k, v in t.items() if k not in ("supplement_mismatches", "pollster_coverage")}))
        for r in out[name]["races"]:
            if r["missing"] or r["votehub_only"] or r["number_mismatch"]:
                wi = r["what_if"]
                chg = r["mu_change_fv"]
                print(f"  {r['race_key']}: VH {r['n_votehub']} / Wiki {r['n_wikipedia']}"
                      f"{'' if r['wikipedia_table'] else ' (no Wikipedia table)'}; missing {[(m['pollster'], m['end'], m['cause'][:9], m['kind'][9:13]) for m in r['missing']]}; "
                      f"VH-only {[(m['pollster'], m['end'], m['blocklisted']) for m in r['votehub_only']]}; "
                      f"mismatch {[(m['pollster'], m['closest_wiki_margin_diff']) for m in r['number_mismatch']]}; mu change {chg}")
    if frames:
        old = pd.read_csv(SC / "poll_audit_polls.csv") if (SC / "poll_audit_polls.csv").exists() else pd.DataFrame()
        new = pd.concat(frames)
        if len(old) and "chamber" in old:
            old = old[~old.chamber.isin(new.chamber.unique())]
        pd.concat([old, new]).to_csv(SC / "poll_audit_polls.csv", index=False)
    path.write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main(tuple(a for a in sys.argv[1:] if a in ("senate", "house")) or ("senate", "house"))


