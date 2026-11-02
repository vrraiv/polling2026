"""Estimate the poll-averaging settings that were assumed:

1. Partisan-sponsor shift   (was 2 pts statewide, 4 pts House districts)
   538 raw_polls 1998-2022, final 21 days, two-party. Within each race, a sponsored poll's miss (poll - result)
   is compared with the race's independent polls: shift = mean(miss_sponsored - mean miss_independent in that race),
   oriented so positive = toward the sponsor's party. Separately for statewide (Sen/Gov) and House district races.
2. Population weights        (was LV 1.0, RV 0.8, adults 0.5)
   538 archived Senate + House polls 2018-2024 (have population), final 60 days, matched to results via raw_polls.
   Within race, each poll's squared miss relative to the race's mean miss; weight_pop = MSE_LV / MSE_pop.
   Also the mean partisan lean of RV/adult polls vs LV in the same race.
3. Recency half-life         (was 21 days races, 14 days generic ballot)
   2018/2022 back-test (archived polls up to 5 days before the election): race-level RMSE across half-lives.
4. Fat tails                 (was t with 5 df)
   Student-t fitted (location 0) to the race-level residuals of final poll averages (cycle mean removed).
Writes data/processed/poll_settings.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT, latest  # noqa: E402
import bias_analysis as BA  # noqa: E402
import backtest as BT  # noqa: E402


def sponsor_shift(r):
    r = r.copy()
    r["miss"] = r.poll2 - r.act2                      # + = poll more Democratic than result
    r["sp"] = r.partisan.fillna("").str.upper()
    r = r[r.sp.isin(["", "DEM", "REP"])]
    ind = r[r.sp == ""].groupby("race_id").miss.mean().rename("ind_miss")
    r = r.join(ind, on="race_id").dropna(subset=["ind_miss"])
    r["rel"] = r.miss - r.ind_miss
    r["toward_sponsor"] = np.where(r.sp == "DEM", r.rel, np.where(r.sp == "REP", -r.rel, np.nan))
    out = {}
    for lab, types in [("statewide", ["Sen-G", "Gov-G"]), ("house_district", ["House-G"])]:
        s = r[r.type_simple.isin(types) & r.toward_sponsor.notna()]
        by = s.groupby("sp").toward_sponsor.agg(["mean", "count", "std"])
        # race-clustered SE
        rm = s.groupby("race_id").toward_sponsor.mean()
        out[lab] = {"shift": float(s.toward_sponsor.mean()), "se": float(rm.std(ddof=1) / np.sqrt(len(rm))), "n_polls": int(len(s)),
                    "n_races": int(len(rm)), "by_party": {k: {"shift": float(v["mean"]), "n": int(v["count"])} for k, v in by.iterrows()}}
    return out


def population_weights(r):
    act = r.drop_duplicates("race_id").set_index("race_id").act2
    rows = []
    for f, office in [("senate_polls_historical.csv", "Sen"), ("house_polls_historical.csv", "House")]:
        p = pd.read_csv(latest("538_wayback", f), low_memory=False)
        p = p[(p.stage == "general") & (p.hypothetical != True) & p.cycle.isin([2018, 2020, 2022, 2024])]  # noqa: E712
        p["end"] = pd.to_datetime(p.end_date, format="%m/%d/%y", errors="coerce")
        q = p[p.party.isin(["DEM", "REP"])].groupby(["question_id", "party"]).pct.max().unstack().dropna()
        q["m"] = 100 * (q.DEM - q.REP) / (q.DEM + q.REP)
        meta = p.drop_duplicates("question_id").set_index("question_id")[["race_id", "cycle", "end", "population", "election_date"]]
        q = q.join(meta)
        q["eday"] = pd.to_datetime(q.election_date, format="%m/%d/%y", errors="coerce")
        q = q[(q.eday - q.end).dt.days.between(0, 60)]
        q["act"] = q.race_id.map(act)
        q = q.dropna(subset=["act"])
        q["office"] = office
        rows.append(q)
    q = pd.concat(rows)
    q["population"] = q.population.str.lower().replace({"v": "lv"})
    q = q[q.population.isin(["lv", "rv", "a"])]
    q["miss"] = q.m - q.act
    q["rel"] = q.miss - q.groupby("race_id").miss.transform("mean")   # remove the race's common miss
    mse = q.groupby("population").rel.apply(lambda x: float(np.mean(x ** 2)))
    n = q.groupby("population").size()
    # lean of RV / adult polls relative to LV polls in the same race
    lv_mean = q[q.population == "lv"].groupby("race_id").miss.mean()
    lean = {}
    for pop in ["rv", "a"]:
        s = q[q.population == pop].join(lv_mean.rename("lv"), on="race_id").dropna(subset=["lv"])
        if len(s):
            d = s.miss - s.lv
            lean[pop] = {"dem_lean_vs_lv": float(d.mean()), "se": float(d.groupby(s.race_id).mean().std() / np.sqrt(s.race_id.nunique())), "n": int(len(s))}
    w = {pop: float(mse["lv"] / mse[pop]) if pop in mse else None for pop in ["lv", "rv", "a"]}
    return {"mse_rel": mse.to_dict(), "n": n.to_dict(), "weight": w, "lean_vs_lv": lean}


def half_life():
    res = {}
    orig = BT.wavg
    for hl in [7, 14, 21, 30, 45, 60, 1000]:
        def wavg_h(df, asof, half_life, _hl=hl):
            return orig(df, asof, _hl)
        BT.wavg = wavg_h
        s = BT.senate()
        res[str(hl)] = {"rmse": float(np.sqrt((s.err ** 2).mean())), "rmse_within": float(np.sqrt(((s.err - s.groupby("cycle").err.transform("mean")) ** 2).mean())),
                        "brier": float(s.brier.mean())}
        g = BT.generic()
        res[str(hl)]["generic_abs_err"] = float(g.error.abs().mean())
    BT.wavg = orig
    return res


def tails():
    cal_r = BA.load()
    races = BA.race_level(cal_r, ["Sen-G", "Gov-G"])
    races["resid"] = races.err - races.groupby("cycle").err.transform("mean")
    x = races.resid.values
    df_, loc, scale = stats.t.fit(x, floc=0)
    ks_t = stats.kstest(x / scale, "t", args=(df_,)).statistic
    ks_n = stats.kstest(x / x.std(), "norm").statistic
    kurt = float(stats.kurtosis(x))
    return {"df": float(df_), "scale": float(scale), "n": int(len(x)), "excess_kurtosis": kurt, "ks_t": float(ks_t), "ks_normal": float(ks_n),
            "tail_share_gt_2sd": float((np.abs(x) > 2 * x.std()).mean())}


def main():
    r = BA.load()
    out = {"sponsor": sponsor_shift(r), "population": population_weights(r), "half_life": half_life(), "tails": tails()}
    sp, pw, hl, tl = out["sponsor"], out["population"], out["half_life"], out["tails"]
    print("SPONSOR SHIFT (pts toward sponsor):", {k: f"{v['shift']:+.2f} ± {v['se']:.2f} ({v['n_polls']} polls, {v['n_races']} races) by party {v['by_party']}" for k, v in sp.items()})
    print("POPULATION: relative MSE", {k: round(v, 1) for k, v in pw["mse_rel"].items()}, "n", pw["n"], "-> weights", {k: (round(v, 2) if v else v) for k, v in pw["weight"].items()},
          "lean vs LV", {k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()} for k, v in pw["lean_vs_lv"].items()})
    print("HALF-LIFE:", {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in hl.items()})
    print("TAILS:", {k: round(v, 3) if isinstance(v, float) else v for k, v in tl.items()})
    # chosen values
    best_hl = min(hl, key=lambda k: hl[k]["rmse_within"])
    out["chosen"] = {
        "partisan_shift_statewide": round(max(sp["statewide"]["shift"], 0.0), 1),
        "partisan_shift_house": round(max(sp["house_district"]["shift"], 0.0), 1),
        "pop_weight": {k: round(min(max(v, 0.2), 1.0), 2) for k, v in pw["weight"].items() if v is not None},
        # backtest favours no decay within the ~140-day window; 60 days is within 0.12 pts of that and still reacts to late shifts
        "half_life_races": 60,
        "half_life_best_tested": best_hl,
        "pop_dem_lean": {k: round(v["dem_lean_vs_lv"], 1) for k, v in pw["lean_vs_lv"].items()},
        "df_t": round(min(max(tl["df"], 3.0), 30.0), 1),
    }
    out["chosen"]["pop_weight"]["lv"] = 1.0
    print("CHOSEN:", out["chosen"])
    (ROOT / "data/processed/poll_settings.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    main()
