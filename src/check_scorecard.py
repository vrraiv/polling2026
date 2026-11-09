"""Check a scorecard refresh before it is published: compares the working copy (after run_scorecard.py) with a
committed reference (default HEAD, the last published run).

    python src/check_scorecard.py              compare the working copy with HEAD
    python src/check_scorecard.py --ref REF    ...with another commit

Two tiers:
  HOLD    don't publish; a person decides. Exit code 1.
  REVIEW  publish only after each item is checked against a second source (the state's official results or the
          Wikipedia page's own cited source) and found right. Exit code 2.
  CLEAN   exit code 0.
The checks are the problems found by hand in the first days of counting (Nov 5-6, 2026): California and New Jersey
counts settling while ballots were still uncounted, finished counts un-settling, and stale Wikipedia boxes.
"""
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "collect"))
from results_margins import SETTLED_DAYS, SLOW_COUNT, SLOW_COUNT_DAYS  # noqa: E402

BIG_MISS = 15.0           # a newly scored race whose count is this far from the forecast's expected margin: verify it
THIN_PAGE = 0.5           # a newly settled House race on a state page where under half the districts have counts


def git_show(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def old_csv(ref, path):
    b = git_show(ref, path)
    return pd.read_csv(io.BytesIO(b)) if b else None


def page_data(text):
    i = text.index("const DATA = ") + len("const DATA = ")
    return json.JSONDecoder().raw_decode(text[i:])[0]


def main(ref):
    hold, review, info = [], [], []

    # 1. the frozen forecast is untouched
    if subprocess.run(["git", "diff", "--quiet", ref, "--", "data/final"], cwd=ROOT).returncode:
        hold.append("data/final/ differs from the reference: the frozen forecast must never change")
    old_page = git_show(ref, "site/index.html")
    new_page = (ROOT / "site/index.html").read_text(encoding="utf-8")
    if old_page:
        a, b = page_data(old_page.decode("utf-8")), page_data(new_page)
        changed = sorted(k for k in set(a) | set(b) if k != "scorecard" and a.get(k) != b.get(k))
        if changed:
            hold.append(f"forecast data on the page changed (only the scorecard may): {changed}")
    if '"final": true' not in new_page:
        hold.append("site/index.html is not the frozen-forecast build")

    # 2. counts and calls
    sc_old = json.loads(git_show(ref, "data/scorecard/scorecard.json"))
    sc = json.loads((ROOT / "data/scorecard/scorecard.json").read_text(encoding="utf-8"))
    for ch in ("senate", "house"):
        so, sn = sc_old[ch]["seats"], sc[ch]["seats"]
        for k in ("dem_seats_called", "rep_seats_called"):
            if sn[k] < so[k]:
                hold.append(f"{ch}: {k} fell {so[k]} -> {sn[k]} (a call was withdrawn or a page failed to parse)")
        info.append(f"{ch}: called D {sn['dem_seats_called']} R {sn['rep_seats_called']}")
        ro, rn = old_csv(ref, f"data/scorecard/results_{ch}.csv"), pd.read_csv(ROOT / f"data/scorecard/results_{ch}.csv")
        m = ro.merge(rn, on="race_key", suffixes=("_old", "")) if ro is not None else rn.iloc[0:0]
        flipped = m[m.winner_party_old.notna() & m.winner_party.notna() & (m.winner_party_old != m.winner_party)]
        for _, r in flipped.iterrows():
            review.append(f"{r.race_key}: winner changed {r.winner_party_old} -> {r.winner_party} ({r.winner_name})")
        uncalled = m[m.winner_party_old.notna() & m.winner_party.isna()]
        for _, r in uncalled.iterrows():
            review.append(f"{r.race_key}: was called for {r.winner_party_old}, now uncalled")
    co, cn = sc_old["margins"]["completeness"], sc["margins"]["completeness"]
    for k in ("senate", "house_all"):
        if cn[k]["counted"] < co[k]["counted"]:
            hold.append(f"{k}: races with counts fell {co[k]['counted']} -> {cn[k]['counted']} (a source failed?)")
    if sc["margins"].get("sign_mismatches"):
        hold.append(f"count and called winner disagree: {sc['margins']['sign_mismatches']}")
    for ch, srcs in (("senate", sc["sources"].get("senate", {})), ("house", sc["sources"].get("house", {}))):
        old_mod = sc_old["sources"].get(ch, {}).get("page_modified")
        if old_mod and srcs.get("page_modified") and srcs["page_modified"] < old_mod:
            hold.append(f"{ch} overview page is older than the reference's ({srcs['page_modified']} < {old_mod})")

    # 3. settled races
    for ch in ("house", "senate"):
        o = old_csv(ref, f"data/scorecard/margins_{ch}.csv")
        n = pd.read_csv(ROOT / f"data/scorecard/margins_{ch}.csv")
        n["st"] = n.race_key.str.split("|").str[1]
        s_new = set(n.race_key[n.settled.fillna(False).astype(bool)])
        s_old = set(o.race_key[o.settled.fillna(False).astype(bool)]) if o is not None else set()
        nn = n.set_index("race_key")
        oo = o.set_index("race_key") if o is not None else None
        for k in sorted(s_old - s_new):
            r = nn.loc[k] if k in nn.index else None
            why = "race missing" if r is None else (f"count {oo.loc[k].cand_sum:,.0f} -> {r.cand_sum:,.0f}"
                                                    if pd.notna(r.cand_sum) else "no count")
            moved = r is not None and pd.notna(r.cand_sum) and abs(r.cand_sum / oo.loc[k].cand_sum - 1) >= 0.01
            held = None if r is None else r.get("held_days")
            if not moved and r is not None and pd.notna(held) and held < (SLOW_COUNT_DAYS if r.st in SLOW_COUNT else SETTLED_DAYS):
                info.append(f"{k}: no longer settled: count unchanged, but not yet held still for the required days ({held:.0f})")
                continue
            (review if moved else hold).append(f"{k}: was settled, no longer ({why})")
        for k in sorted(s_new):
            r = nn.loc[k]
            held = r.get("held_days")
            need = SLOW_COUNT_DAYS if r.st in SLOW_COUNT else SETTLED_DAYS
            if not (pd.notna(held) and held >= need):
                hold.append(f"{k}: settled after {held} days held still (rule is {need})")
        for k in sorted(s_new - s_old):
            r = nn.loc[k]
            info.append(f"newly settled {k}: {r.margin:+.1f} ({r.source}, {r.cand_sum:,.0f} votes)")
            if ch == "house" and r.source == "wikipedia":
                page = n[n.snapshot == r.snapshot]
                share = (page.cand_sum.fillna(0) > 0).mean()
                if share < THIN_PAGE:
                    review.append(f"{k}: settled on a page where only {share:.0%} of districts have counts "
                                  f"(stale box? the NJ-7 case)")
            if isinstance(r.issues, str) and r.issues:
                review.append(f"{k}: settled with a data note: {r.issues}")
        flagged = n[n.count_flag.fillna("") != ""]
        for _, r in flagged.iterrows():
            info.append(f"count flag {r.race_key}: {r.count_flag} (not scored)")

    # 4. newly scored races far from the forecast
    for key in ("senate_margins", "house_margins"):
        old_scored = {r["race"] for r in sc_old["margins"].get(key, []) if r.get("actual") is not None}
        for r in sc["margins"].get(key, []):
            if r.get("actual") is None or r["race"] in old_scored or r.get("mu_polls_fundamentals") is None:
                continue
            err = r["actual"] - r["mu_polls_fundamentals"]
            if abs(err) > BIG_MISS:
                review.append(f"{r['race']}: newly scored {r['actual']:+.1f} vs expected {r['mu_polls_fundamentals']:+.1f} "
                              f"(error {err:+.1f}): confirm the count")
    if sc["margins"]["national"].get("ready") and not sc_old["margins"]["national"].get("ready"):
        review.append(f"national House vote now shown on the page ({sc['margins']['national']['house_vote_margin']:+.1f}): "
                      "confirm it against a published national tally")

    for lab, xs in (("HOLD", hold), ("REVIEW", review), ("info", info)):
        for x in xs:
            print(f"{lab:<6}  {x}")
    result = "HOLD" if hold else "REVIEW" if review else "CLEAN"
    print(f"\nRESULT {result}  ({len(hold)} hold, {len(review)} review)")
    return 1 if hold else 2 if review else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(args[args.index("--ref") + 1] if "--ref" in args else "HEAD"))
