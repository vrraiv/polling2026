"""Polling-bias structure, 1998-2022 (538 raw_polls.csv: final-21-day polls vs. results).

Part A: national bias. Does the generic-ballot (and pooled race-level) miss depend on a time trend,
        the president's party, or midterm vs. presidential years?
Part B: state-level bias. Does the miss depend on state partisan lean (prior presidential margin
        relative to the nation)? This is the measurable footprint of differential non-response by
        party ("shy" voters in red states / enthusiasm gaps in blue states). Leave-one-cycle-out
        backtest of a lean-based correction, symmetric and asymmetric (R-lean vs. D-lean states).

All margins are TWO-PARTY D-R (fixes the earlier raw-margin comparison, which mixed undecideds in).
Positive error = Democrats beat their polls.
Writes data/processed/bias_analysis.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT, latest  # noqa: E402

PRES_PARTY = {1998: "D", 2000: "D", 2002: "R", 2004: "R", 2006: "R", 2008: "R", 2010: "D", 2012: "D", 2014: "D",
              2016: "D", 2018: "R", 2020: "R", 2022: "D", 2026: "R"}  # party holding the White House at election time


def load():
    r = pd.read_csv(latest("538_github", "raw_polls.csv"), low_memory=False)
    r = r[r.cycle % 2 == 0]  # even-year generals only
    d1 = (r.cand1_party == "DEM") & (r.cand2_party == "REP")
    d2 = (r.cand1_party == "REP") & (r.cand2_party == "DEM")
    r = r[d1 | d2].copy()
    dp = np.where(d1[d1 | d2], r.cand1_pct, r.cand2_pct)
    rp = np.where(d1[d1 | d2], r.cand2_pct, r.cand1_pct)
    da = np.where(d1[d1 | d2], r.cand1_actual, r.cand2_actual)
    ra = np.where(d1[d1 | d2], r.cand2_actual, r.cand1_actual)
    r["poll2"] = 100 * (dp - rp) / (dp + rp)
    r["act2"] = 100 * (da - ra) / (da + ra)
    return r


def race_level(r, types):
    s = r[r.type_simple.isin(types)]
    g = s.groupby(["cycle", "type_simple", "location", "race_id"]).agg(poll=("poll2", "mean"), act=("act2", "first"),
                                                                       n=("poll2", "size")).reset_index()
    g["err"] = g.act - g.poll
    return g


def cycle_features(df):
    df = df.copy()
    df["pres_D"] = df.cycle.map(PRES_PARTY).eq("D").astype(int)
    df["midterm"] = (df.cycle % 4 == 2).astype(int)
    df["yr"] = (df.cycle - 2010) / 10.0
    # error measured toward the president's party (+ = president's party beat its polls)
    df["err_pres"] = np.where(df.pres_D == 1, df.err, -df.err)
    return df


def part_a(r):
    gen = cycle_features(race_level(r, ["House-G-US"]))
    pooled = cycle_features(race_level(r, ["Sen-G", "Gov-G"]).groupby("cycle").err.mean().reset_index())
    out = {"generic_by_cycle": gen[["cycle", "poll", "act", "err", "pres_D", "midterm"]].round(2).to_dict("records")}
    for name, df in [("generic", gen), ("senate_gov_cycle_means", pooled)]:
        res = {"n_cycles": int(len(df)), "mean": float(df.err.mean()), "sd": float(df.err.std()),
               "mean_midterm": float(df[df.midterm == 1].err.mean()), "mean_pres_year": float(df[df.midterm == 0].err.mean()),
               "mean_pres_D": float(df[df.pres_D == 1].err.mean()), "mean_pres_R": float(df[df.pres_D == 0].err.mean()),
               "mean_midterm_pres_R": float(df[(df.midterm == 1) & (df.pres_D == 0)].err.mean()),
               "mean_toward_pres_party": float(df.err_pres.mean()),
               "mean_toward_pres_party_midterms": float(df[df.midterm == 1].err_pres.mean())}
        fits = {}
        for f in ["err ~ yr", "err ~ pres_D", "err ~ midterm", "err ~ yr + pres_D + midterm", "err_pres ~ midterm"]:
            m = smf.ols(f, df).fit()
            fits[f] = {k: {"coef": float(m.params[k]), "se": float(m.bse[k]), "p": float(m.pvalues[k])} for k in m.params.index}
        res["fits"] = fits
        out[name] = res
    # also the correlation of the generic miss with the Senate/Gov miss in the same cycle
    mg = gen.set_index("cycle").err.rename("generic").to_frame().join(pooled.set_index("cycle").err.rename("races"))
    out["corr_generic_vs_race_miss"] = float(mg.corr().iloc[0, 1])
    return out, gen, pooled


def state_lean(r):
    """Prior presidential state margin minus national margin (two-party), from raw_polls Pres-G actuals."""
    p = r[r.type_simple == "Pres-G"].drop_duplicates(["cycle", "location"])
    nat = p[p.location == "US"].set_index("cycle").act2
    st = p[(p.location != "US") & (p.location.str.len() == 2)].copy()
    st["lean"] = st.act2 - st.cycle.map(nat)
    return st.set_index(["cycle", "location"]).lean


def part_b(r):
    lean = state_lean(r)
    races = race_level(r, ["Sen-G", "Gov-G"])
    races = races[races.location.str.len() == 2]

    def prior_pres(c):
        return c - 2 if c % 4 == 2 else c - 4  # most recent presidential election before this one
    races["pres_cycle"] = races.cycle.map(prior_pres)
    races["lean"] = [lean.get((pc, loc), np.nan) for pc, loc in zip(races.pres_cycle, races.location)]
    races = races.dropna(subset=["lean"])
    races = cycle_features(races)
    races["cyc_mean"] = races.groupby("cycle").err.transform("mean")
    races["resid"] = races.err - races.cyc_mean
    races["leanR"] = np.minimum(races.lean, 0)   # magnitude of R lean (negative)
    races["leanD"] = np.maximum(races.lean, 0)
    # pooled slopes (within-cycle)
    m_sym = smf.ols("resid ~ lean", races).fit(cov_type="cluster", cov_kwds={"groups": races.cycle})
    m_asym = smf.ols("resid ~ leanR + leanD", races).fit(cov_type="cluster", cov_kwds={"groups": races.cycle})
    by_cycle = []
    for c, g in races.groupby("cycle"):
        mm = smf.ols("resid ~ lean", g).fit()
        by_cycle.append({"cycle": int(c), "n": int(len(g)), "slope": float(mm.params["lean"]), "se": float(mm.bse["lean"]),
                         "pres_party": PRES_PARTY[c], "midterm": bool(c % 4 == 2)})
    # leave-one-cycle-out: does a lean correction (estimated on other cycles) reduce held-out error?
    loco = []
    for c in sorted(races.cycle.unique()):
        tr, te = races[races.cycle != c], races[races.cycle == c].copy()
        b = smf.ols("resid ~ lean", tr).fit().params
        ba = smf.ols("resid ~ leanR + leanD", tr).fit().params
        te["adj_sym"] = b["lean"] * te.lean
        te["adj_asym"] = ba["leanR"] * te.leanR + ba["leanD"] * te.leanD
        te["adj_Ronly"] = ba["leanR"] * te.leanR   # user's framing: correct R-lean (shy voter) only
        row = {"cycle": int(c), "n": int(len(te)), "slope_used": float(b["lean"])}
        for k in ["none", "adj_sym", "adj_asym", "adj_Ronly"]:
            pred = te.poll + (0 if k == "none" else te[k])
            e = te.act - pred
            row[f"mae_{k}"] = float(e.abs().mean())
            row[f"rmse_{k}"] = float(np.sqrt((e ** 2).mean()))
            row[f"winner_{k}"] = float(((pred > 0) == (te.act > 0)).mean())
            # within-cycle error after removing that cycle's (unknowable in advance) shared miss
            row[f"rmse_within_{k}"] = float(np.sqrt(((e - e.mean()) ** 2).mean()))
        loco.append(row)
    loco = pd.DataFrame(loco)
    tot = {k: float(np.average(loco[f"rmse_within_{k}"] ** 2, weights=loco.n) ** 0.5) for k in ["none", "adj_sym", "adj_asym", "adj_Ronly"]}
    tot_raw = {k: float(np.average(loco[f"rmse_{k}"] ** 2, weights=loco.n) ** 0.5) for k in ["none", "adj_sym", "adj_asym", "adj_Ronly"]}
    win = {k: float(np.average(loco[f"winner_{k}"], weights=loco.n)) for k in ["none", "adj_sym", "adj_asym", "adj_Ronly"]}
    recent = loco[loco.cycle >= 2012]
    tot_recent = {k: float(np.average(recent[f"rmse_within_{k}"] ** 2, weights=recent.n) ** 0.5) for k in ["none", "adj_sym", "adj_asym", "adj_Ronly"]}
    # REAL-TIME test: for each cycle >= 2014, estimate slopes only from earlier cycles since 2010
    # (the post-2010 regime), apply to the held-out cycle.
    rt = []
    for c in sorted(races.cycle.unique()):
        if c < 2014:
            continue
        tr, te = races[(races.cycle < c) & (races.cycle >= 2010)], races[races.cycle == c].copy()
        b = smf.ols("resid ~ lean", tr).fit().params
        ba = smf.ols("resid ~ leanR + leanD", tr).fit().params
        adj = {"none": 0, "sym": b["lean"] * te.lean, "asym": ba["leanR"] * te.leanR + ba["leanD"] * te.leanD,
               "Ronly": ba["leanR"] * te.leanR}
        row = {"cycle": int(c), "n": int(len(te)), "slope": float(b["lean"]), "slopeR": float(ba["leanR"]), "slopeD": float(ba["leanD"])}
        for k, a_ in adj.items():
            e = te.act - (te.poll + a_)
            row[f"rmse_within_{k}"] = float(np.sqrt(((e - e.mean()) ** 2).mean()))
            row[f"winner_{k}"] = float(((te.poll + a_ > 0) == (te.act > 0)).mean())
        rt.append(row)
    rt = pd.DataFrame(rt)
    rt_tot = {k: float(np.average(rt[f"rmse_within_{k}"] ** 2, weights=rt.n) ** 0.5) for k in ["none", "sym", "asym", "Ronly"]}
    rt_win = {k: float(np.average(rt[f"winner_{k}"], weights=rt.n)) for k in ["none", "sym", "asym", "Ronly"]}
    post = races[races.cycle >= 2010]
    m_post = smf.ols("resid ~ lean", post).fit(cov_type="cluster", cov_kwds={"groups": post.cycle})
    m_post_a = smf.ols("resid ~ leanR + leanD", post).fit(cov_type="cluster", cov_kwds={"groups": post.cycle})
    out = {
        "realtime": rt.round(3).to_dict("records"), "realtime_rmse_within": rt_tot, "realtime_winner": rt_win,
        "post2010_symmetric": {"slope": float(m_post.params["lean"]), "se_cluster": float(m_post.bse["lean"]), "p": float(m_post.pvalues["lean"])},
        "post2010_asymmetric": {k: {"slope": float(m_post_a.params[k]), "se_cluster": float(m_post_a.bse[k]), "p": float(m_post_a.pvalues[k])} for k in ["leanR", "leanD"]},
        "n_races": int(len(races)),
        "pooled_symmetric": {"slope": float(m_sym.params["lean"]), "se_cluster": float(m_sym.bse["lean"]), "p": float(m_sym.pvalues["lean"])},
        "pooled_asymmetric": {k: {"slope": float(m_asym.params[k]), "se_cluster": float(m_asym.bse[k]), "p": float(m_asym.pvalues[k])} for k in ["leanR", "leanD"]},
        "slope_by_cycle": by_cycle,
        "loco": loco.round(3).to_dict("records"),
        "loco_rmse_within": tot, "loco_rmse_raw": tot_raw, "loco_winner_acc": win, "loco_rmse_within_2012plus": tot_recent,
    }
    races.to_csv(ROOT / "data/processed/bias_race_level.csv", index=False)
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    r = load()
    a, gen, pooled = part_a(r)
    b = part_b(r)
    print("=== A. National (two-party) ===")
    print(gen[["cycle", "poll", "act", "err", "pres_D", "midterm"]].round(2).to_string(index=False))
    for k in ["generic", "senate_gov_cycle_means"]:
        x = a[k]
        print(f"\n[{k}] n={x['n_cycles']} mean {x['mean']:+.2f} sd {x['sd']:.2f} | midterm {x['mean_midterm']:+.2f} pres-yr {x['mean_pres_year']:+.2f} | "
              f"pres D {x['mean_pres_D']:+.2f} pres R {x['mean_pres_R']:+.2f} | midterm & R pres {x['mean_midterm_pres_R']:+.2f} | toward pres party {x['mean_toward_pres_party']:+.2f}")
        for f, v in x["fits"].items():
            print("   ", f, {kk: f"{vv['coef']:+.2f} (se {vv['se']:.2f}, p={vv['p']:.2f})" for kk, vv in v.items() if kk != "Intercept"})
    print("corr(generic miss, Senate/Gov miss) =", round(a["corr_generic_vs_race_miss"], 2))
    print("\n=== B. State lean ===")
    print("races", b["n_races"], "pooled slope", b["pooled_symmetric"], "\nasym", b["pooled_asymmetric"])
    print(pd.DataFrame(b["slope_by_cycle"]).round(3).to_string(index=False))
    print(pd.DataFrame(b["loco"])[["cycle", "n", "slope_used", "rmse_within_none", "rmse_within_adj_sym", "rmse_within_adj_asym", "rmse_within_adj_Ronly",
                                   "winner_none", "winner_adj_sym", "winner_adj_Ronly"]].to_string(index=False))
    print("LOCO within-cycle RMSE:", {k: round(v, 3) for k, v in b["loco_rmse_within"].items()})
    print("LOCO within-cycle RMSE 2012+:", {k: round(v, 3) for k, v in b["loco_rmse_within_2012plus"].items()})
    print("LOCO winner acc:", {k: round(v, 3) for k, v in b["loco_winner_acc"].items()})
    print("\nREAL-TIME (train 2010..c-2, test c):")
    print(pd.DataFrame(b["realtime"]).to_string(index=False))
    print("real-time within RMSE:", {k: round(v, 3) for k, v in b["realtime_rmse_within"].items()}, "winner:", {k: round(v, 3) for k, v in b["realtime_winner"].items()})
    print("post-2010 slope:", b["post2010_symmetric"], "asym:", b["post2010_asymmetric"])
    (ROOT / "data/processed/bias_analysis.json").write_text(json.dumps({"national": a, "state": b}, indent=1, default=float))
