"""How confident should we be in the polling-bias adjustment, and can we say more than 'the past average'?

A. Extend the generic-ballot miss series with 2024 (538 archive has 2024 polls; raw_polls stops at 2022) and
   measure it on likely-voter polls only (what today's aggregators approximate).
B. Relate the miss to things: poll level (size of the Dem lead), presidential approval, the pollster mix.
   Pollster house effects: each pollster's historical two-party miss vs results (538 raw_polls, 2014-2022, all
   general-election polls, shrunk toward the mean), weighted by the 2026 generic-ballot and key-Senate pollster mix.
   Methodology: miss by method group.
C. Senate: per-cycle Senate miss vs generic miss (does a generic bias translate 1:1?), and the state-lean pattern as a
   per-race directional estimate for the 2026 battlegrounds.
D. Predictive distribution of the 2026 generic-ballot miss: P(polls overstate Dems), quantiles.
Writes data/processed/bias_confidence.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT, latest  # noqa: E402
import bias_analysis as BA  # noqa: E402
import pollavg as P  # noqa: E402

ELECTION = {2018: "2018-11-06", 2020: "2020-11-03", 2022: "2022-11-08", 2024: "2024-11-05"}


def two_party(d, r):
    return 100 * (d - r) / (d + r)


def generic_recent_by_population():
    """Final-21-day generic-ballot miss, 2018-2024, two-party, by population type and overall."""
    g = pd.read_csv(latest("538_wayback", "generic_ballot_polls_historical.csv"), low_memory=False)
    g["end"] = pd.to_datetime(g.end_date, format="%m/%d/%y", errors="coerce")
    g["m"] = two_party(g.dem, g.rep)
    g["pop"] = g.population.str.lower().replace({"v": "lv"})
    vote = pd.read_csv(ROOT / "data/interim/house_national_vote.csv").set_index("year").two_party_margin_D
    rows = []
    for cyc, eday in ELECTION.items():
        e = pd.Timestamp(eday)
        x = g[(g.cycle == cyc) & (g.end <= e) & (g.end >= e - pd.Timedelta(days=21))]
        # one row per poll (question) - the file has one row per poll already
        row = {"cycle": cyc, "actual": float(vote[cyc]), "n": int(len(x)), "all": float(vote[cyc] - x.m.mean())}   # result - polls: negative = polls overstated Dems
        for pop in ["lv", "rv", "a"]:
            s = x[x["pop"] == pop]
            row[pop] = float(vote[cyc] - s.m.mean()) if len(s) >= 3 else np.nan
            row[f"n_{pop}"] = int(len(s))
        rows.append(row)
    return pd.DataFrame(rows)


def pollster_effects(r, min_n=8, k_shrink=15):
    """Each pollster's mean two-party miss (poll - result), 2014-2022 general-election polls, shrunk toward 0 relative
    to the cycle mean (house effect) and also the raw miss (house effect + the cycle's shared miss)."""
    s = r[(r.cycle >= 2014) & r.type_simple.isin(["Sen-G", "Gov-G", "House-G", "House-G-US", "Pres-G"])].copy()
    s["miss"] = s.poll2 - s.act2
    s["rel"] = s.miss - s.groupby("race_id").miss.transform("mean")          # vs other polls of the same race
    grand_rel = 0.0
    agg = s.groupby("pollster").agg(n=("miss", "size"), miss=("miss", "mean"), rel=("rel", "mean"), last=("cycle", "max"))
    agg["rel_shrunk"] = (agg.n * agg.rel + k_shrink * grand_rel) / (agg.n + k_shrink)
    agg["miss_shrunk"] = (agg.n * agg.miss + k_shrink * s.miss.mean()) / (agg.n + k_shrink)
    return agg, float(s.miss.mean()), float(s.rel.std())


def match_pollster(name, index):
    """Map a VoteHub pollster name onto 538's pollster names (loose match on the first distinctive token)."""
    n = name.lower().replace("the ", "").split("/")[0].strip()
    if name in index:
        return name
    cands = [p for p in index if n and n.split()[0] in p.lower()]
    if len(cands) == 1:
        return cands[0]
    for p in index:
        if p.lower().startswith(n[:8]):
            return p
    return None


def mix_bias(polls_2026, agg, label):
    cnt = pd.Series([x["pollster"] for x in polls_2026]).value_counts()
    rows, matched = [], 0
    for name, c in cnt.items():
        m = match_pollster(name, agg.index)
        if m is not None and agg.loc[m, "n"] >= 5:
            matched += c
            rows.append({"pollster": name, "matched": m, "n_2026": int(c), "n_hist": int(agg.loc[m, "n"]),
                         "house_effect": float(agg.loc[m, "rel_shrunk"]), "raw_miss": float(agg.loc[m, "miss_shrunk"])})
    df = pd.DataFrame(rows)
    w = df.n_2026
    return {"label": label, "n_polls_2026": int(cnt.sum()), "matched_share": float(matched / cnt.sum()) if cnt.sum() else 0,
            "mix_house_effect": float(np.average(df.house_effect, weights=w)) if len(df) else None,
            "mix_raw_miss": float(np.average(df.raw_miss, weights=w)) if len(df) else None,
            "pollsters": df.sort_values("n_2026", ascending=False).head(15).round(2).to_dict("records")}


def main():
    r = BA.load()
    out = {}
    # ---------- A. series with 2024, LV-only
    rec = generic_recent_by_population()
    gen = BA.race_level(r, ["House-G-US"])[["cycle", "poll", "act", "err"]]
    series = gen.set_index("cycle").err.to_dict()
    series[2024] = float(rec.loc[rec.cycle == 2024, "all"].iloc[0])
    s14 = pd.Series(series).sort_index()
    out["series_with_2024"] = {int(k): round(v, 2) for k, v in s14.items()}
    out["recent_by_population"] = rec.round(2).to_dict("records")
    lv = rec.lv.dropna()
    out["lv_only_2018_2024"] = {"mean": float(lv.mean()), "cycles": int(len(lv)), "values": rec[["cycle", "lv"]].round(2).to_dict("records")}
    # LV polls are less Democratic than the all-poll average by this much (positive = LV less D-biased); used as the LV discount
    out["lv_discount_est"] = float(lv.mean() - rec.loc[rec.lv.notna(), "all"].mean())
    print("A. generic miss with 2024:", out["series_with_2024"])
    print("   recent by population:\n", rec.round(2).to_string(index=False))
    print(f"   LV-only mean 2018-2024: {lv.mean():+.2f}; all-polls mean same cycles: {rec['all'].mean():+.2f}")
    # predictive distribution (flat, 14 cycles; and 2010+)
    for lab, x in [("all_14", s14.values), ("2010plus", s14[s14.index >= 2010].values), ("2014plus", s14[s14.index >= 2014].values)]:
        n = len(x); m, sd = x.mean(), x.std(ddof=1)
        pred_sd = sd * np.sqrt(1 + 1 / n)
        tdist = stats.t(df=n - 1, loc=m, scale=pred_sd)
        out[f"pred_{lab}"] = {"n": n, "mean": float(m), "sd": float(sd), "pred_sd": float(pred_sd), "p_overstate_dems": float(tdist.cdf(0)),
                              "p_overstate_by_2plus": float(tdist.cdf(-2)), "q10": float(tdist.ppf(.1)), "q50": float(m), "q90": float(tdist.ppf(.9))}
        print(f"   predictive ({lab}, n={n}): mean {m:+.2f}, pred SD {pred_sd:.2f}, P(polls overstate Dems) {tdist.cdf(0):.0%}, P(by 2+ pts) {tdist.cdf(-2):.0%}, 80% range {tdist.ppf(.1):+.1f}..{tdist.ppf(.9):+.1f}")

    # ---------- B. relate to poll level and approval
    fd = pd.read_csv(ROOT / "data/interim/fundamentals_dataset.csv").set_index("year")
    df = gen.copy()
    df["approval"] = df.cycle.map(fd.approval)
    df["pres_D"] = df.cycle.map(fd.pres_party).eq("D").astype(int)
    df["appr_pres_party"] = np.where(df.pres_D == 1, df.approval, 100 - df.approval)   # approval 'toward Dems'
    df["err_pres"] = np.where(df.pres_D == 1, df.err, -df.err)
    fits = {}
    for f in ["err ~ poll", "err ~ np.abs(poll)", "err ~ approval", "err_pres ~ approval"]:
        m = smf.ols(f, df).fit()
        k = m.params.index[-1]
        fits[f] = {"coef": float(m.params[k]), "se": float(m.bse[k]), "p": float(m.pvalues[k]), "r2": float(m.rsquared)}
    out["covariate_fits"] = fits
    print("B. covariates:", {k: f"{v['coef']:+.2f}±{v['se']:.2f} (p={v['p']:.2f})" for k, v in fits.items()})

    # pollster effects
    agg, grand_miss, rel_sd = pollster_effects(r)
    d = json.loads(sorted((ROOT / "data/raw/votehub").glob("*/polls.json"))[-1].read_text(encoding="utf-8"))
    gen26 = [x for x in d if x["poll_type"] == "generic-ballot" and x["end_date"] >= "2026-01-01"]
    key = {"Texas", "Ohio", "Kansas", "Alaska", "Iowa", "Michigan", "Maine", "North Carolina", "Georgia", "New Hampshire", "Minnesota", "Nebraska"}
    sen26 = [x for x in d if x["poll_type"] == "us-senator" and x["end_date"] >= "2026-08-01" and x["subject"].replace("2026 ", "") in key]
    out["pollster_mix"] = {"generic": mix_bias(gen26, agg, "2026 generic-ballot pollsters (VoteHub)"),
                           "senate_key": mix_bias(sen26, agg, "pollsters of the 12 key Senate races since Aug 1"),
                           "all_pollsters_raw_miss_2014_2022": grand_miss, "house_effect_sd": rel_sd}
    # for the forecast (result - poll convention): expected Senate miss implied by this year's key-race pollsters
    out["senate_mix_bias"] = -out["pollster_mix"]["senate_key"]["mix_raw_miss"]
    out["generic_mix_bias"] = -out["pollster_mix"]["generic"]["mix_raw_miss"]
    for k in ["generic", "senate_key"]:
        v = out["pollster_mix"][k]
        print(f"   pollster mix [{k}]: matched {v['matched_share']:.0%} of {v['n_polls_2026']} polls; mix house effect {v['mix_house_effect']:+.2f} "
              f"(vs other polls of the same race); mix raw miss {v['mix_raw_miss']:+.2f} vs all-pollster {grand_miss:+.2f}")
        print("     ", [(p["pollster"], p["n_2026"], round(p["house_effect"], 1)) for p in v["pollsters"][:10]])
    # methodology
    s = r[(r.cycle >= 2014) & r.type_simple.isin(["Sen-G", "Gov-G", "House-G", "House-G-US", "Pres-G"])].copy()
    s["miss"] = s.poll2 - s.act2; s["rel"] = s.miss - s.groupby("race_id").miss.transform("mean")
    s["meth"] = s.methodology.fillna("unknown").str.replace(r"/.*", " (mixed)", regex=True)
    me = s.groupby("meth").agg(n=("rel", "size"), rel=("rel", "mean"), miss=("miss", "mean")).sort_values("n", ascending=False)
    out["methodology"] = me.round(2).reset_index().to_dict("records")
    print("   by methodology (2014-2022):\n", me.round(2).head(8).to_string())

    # ---------- C. Senate
    sen_cyc = BA.race_level(r, ["Sen-G"]).groupby("cycle").err.mean()
    both = pd.DataFrame({"gen": gen.set_index("cycle").err, "sen": sen_cyc}).dropna()
    m = smf.ols("sen ~ gen", both).fit()
    out["senate_vs_generic"] = {"slope": float(m.params["gen"]), "se": float(m.bse["gen"]), "intercept": float(m.params["Intercept"]),
                                "corr": float(both.corr().iloc[0, 1]), "sen_mean_2014plus": float(both.loc[both.index >= 2014, "sen"].mean()),
                                "sen_by_cycle": both.sen.round(2).to_dict()}
    print(f"C. Senate cycle miss on generic miss: slope {m.params['gen']:.2f} ± {m.bse['gen']:.2f}, intercept {m.params['Intercept']:+.2f}, corr {both.corr().iloc[0,1]:.2f}; "
          f"Senate mean miss 2014+: {both.loc[both.index >= 2014, 'sen'].mean():+.2f}; by cycle {both.sen.round(1).to_dict()}")
    # lean-based per-race directional estimate for 2026 battlegrounds
    ba = json.loads((ROOT / "data/processed/bias_analysis.json").read_text())["state"]
    slope = ba["post2010_symmetric"]["slope"]; slope_se = ba["post2010_symmetric"]["se_cluster"]
    sr = pd.read_csv(ROOT / "data/processed/senate_polls_fundamentals.csv")
    sr = sr[sr.n_polls > 0]
    sr["lean_adj"] = slope * 2 * sr.pvi
    sr["p_now"] = sr.p_dside
    out["lean_based"] = {"slope": slope, "se": slope_se,
                         "races": sr[["state", "pvi", "poll_avg", "mu", "p_dside", "lean_adj"]].round(2).sort_values("p_dside", ascending=False).to_dict("records")}
    print(f"   lean-based differential (slope {slope:.3f} ± {slope_se:.3f} per pt of 2xPVI), key races:")
    print(sr[sr.p_dside.between(0.05, 0.95)][["state", "pvi", "poll_avg", "mu", "p_dside", "lean_adj"]].round(2).sort_values("p_dside", ascending=False).to_string(index=False))
    (ROOT / "data/processed/bias_confidence.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    main()
