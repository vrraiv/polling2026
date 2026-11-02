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
    out = {"sponsor": sponsor_shift(r), "population": population_weights(r), "half_life": half_life(), "tails": tails(),
           "lv_paired": lv_estimate()}
    lp = out["lv_paired"]
    print(f"LV ADJUSTMENT (paired): prior {lp['prior_mean']:+.2f} (SD {lp['prior_sd']:.2f}); 2026 {lp['mean_2026']:+.2f} (SE {lp['se_2026']:.2f}, "
          f"n={lp['n_pairs_2026']}); posterior LV-minus-RV {lp['posterior_lv_minus_rv']:+.2f} +/- {lp['posterior_sd']:.2f}")
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
        # likely-voter adjustment from paired surveys (historical prior + 2026 pairs); RV and adult polls are shifted by
        # -(LV minus RV). Replaces the cross-poll estimate (RV polls vs other LV polls of the same race, 2018-2024).
        "pop_dem_lean": {"rv": round(-out["lv_paired"]["posterior_lv_minus_rv"], 2), "a": round(-out["lv_paired"]["posterior_lv_minus_rv"], 2)},
        "pop_dem_lean_crosspoll_old": {k: round(v["dem_lean_vs_lv"], 1) for k, v in pw["lean_vs_lv"].items()},
        "df_t": round(min(max(tl["df"], 3.0), 30.0), 1),
    }
    out["chosen"]["pop_weight"]["lv"] = 1.0
    print("CHOSEN:", out["chosen"])
    (ROOT / "data/processed/poll_settings.json").write_text(json.dumps(out, indent=1, default=float))


def lv_adjustment():
    """Likely-voter adjustment from PAIRED comparisons (the same survey published among likely and registered/all voters).
    Prior: historical 538 pairs, mean of per-cycle means (2018-2024) with between-cycle SD.
    Data: 2026 VoteHub pairs (same pollster, dates, race; LV and RV/adult versions), generic ballot + Senate + House.
    Posterior (normal-normal) = the shift to apply to RV/adult polls, as LV-minus-RV (+ = Democrats better among LV).
    Returned as pop_dem_lean = -(posterior): the amount RV/adult polls are more Democratic than LV (subtracted)."""
    import glob as _g
    def tp(d, r):
        return 100 * (d - r) / (d + r)
    rows = []
    g = pd.read_csv(latest("538_wayback", "generic_ballot_polls_historical.csv"), low_memory=False)
    g["m"] = tp(g.dem, g.rep); g["pop"] = g.population.str.lower().replace({"v": "lv"})
    for pid, x in g.groupby("poll_id"):
        if {"lv", "rv"} <= set(x["pop"]):
            rows.append({"cycle": x.cycle.iloc[0], "d": x[x["pop"] == "lv"].m.mean() - x[x["pop"] == "rv"].m.mean()})
    for f in ["senate_polls_historical.csv", "house_polls_historical.csv"]:
        p = pd.read_csv(latest("538_wayback", f), low_memory=False)
        p = p[p.party.isin(["DEM", "REP"]) & (p.stage == "general")]
        q = p.groupby(["poll_id", "question_id", "party"]).pct.max().unstack().dropna()
        q["m"] = tp(q.DEM, q.REP)
        meta = p.drop_duplicates("question_id").set_index("question_id")[["population", "cycle"]]
        q = q.reset_index().join(meta, on="question_id"); q["pop"] = q.population.str.lower().replace({"v": "lv"})
        for pid, x in q.groupby("poll_id"):
            if {"lv", "rv"} <= set(x["pop"]):
                rows.append({"cycle": x.cycle.iloc[0], "d": x[x["pop"] == "lv"].m.mean() - x[x["pop"] == "rv"].m.mean()})
    h = pd.DataFrame(rows)
    cyc = h.groupby("cycle").d.mean()
    prior_m, prior_sd = float(cyc.mean()), float(cyc.std(ddof=1))
    # 2026 pairs
    d = json.loads(sorted((ROOT / "data/raw/votehub").glob("*/polls.json"))[-1].read_text(encoding="utf-8"))
    recs = {}
    for x in d:
        if x["poll_type"] not in ("generic-ballot", "us-senator", "us-representative") or x["end_date"] < "2025-06-01":
            continue
        if x["poll_type"] == "us-senator" and any(w in (x.get("subject") or "") for w in ("Democratic", "Republican")):
            continue  # primaries
        k = (x["pollster"], x["start_date"], x["end_date"], x["poll_type"], x.get("subject"), x.get("seat_name"))
        recs.setdefault(k, {})[(x.get("population") or "").lower()] = {y["choice"]: y["pct"] for y in x["answers"]}
    pairs = []
    for k, v in recs.items():
        lv = v.get("lv"); other = v.get("rv") or v.get("a")
        if not lv or not other:
            continue
        if k[3] == "generic-ballot":
            if {"Dem", "Rep"} <= set(lv) & set(other):
                pairs.append({"type": "generic", "pollster": k[0], "d": tp(lv["Dem"], lv["Rep"]) - tp(other["Dem"], other["Rep"])})
        else:
            common = [c for c in lv if c in other]
            if len(common) >= 2:
                # orient D-R using the race's nominees if known; otherwise by VoteHub answer order is unsafe -> use party lookup
                pairs.append({"type": k[3], "pollster": k[0], "subject": k[4], "c": common[:2], "lv": [lv[c] for c in common[:2]], "o": [other[c] for c in common[:2]]})
    return h, cyc, prior_m, prior_sd, pairs


def lv_posterior(pairs_oriented, prior_m, prior_sd):
    x = np.array(pairs_oriented)
    n = len(x)
    m = float(x.mean()); sd = float(x.std(ddof=1)) if n > 1 else 3.0
    se = sd / np.sqrt(n)
    w = (1 / se ** 2) / (1 / se ** 2 + 1 / prior_sd ** 2)
    post = w * m + (1 - w) * prior_m
    post_sd = float(np.sqrt(1 / (1 / se ** 2 + 1 / prior_sd ** 2)))
    return {"n_pairs_2026": n, "mean_2026": m, "se_2026": float(se), "weight_on_2026": float(w), "posterior_lv_minus_rv": float(post), "posterior_sd": post_sd}



def lv_estimate():
    """Orient the 2026 pairs to D-R and combine with the historical prior. Returns the posterior and details."""
    import pollavg as P
    from wiki import STATE_ABBR
    h, cyc, pm, psd, pairs = lv_adjustment()
    sen = pd.read_csv(ROOT / "data/interim/senate_2026_races.csv")
    known = {"vindman": "D", "nixon": "D", "moody": "R", "brown": "D", "husted": "R"}

    def party_of(name, subject):
        ln = P.lastname(name)
        st = STATE_ABBR.get(str(subject).replace("2026 ", ""))
        r = sen[sen.state == st]
        if not r.empty:
            r = r.iloc[0]
            for col, pty in [("cands_D", "D"), ("cands_I", "D"), ("cands_R", "R")]:
                if any(P.lastname(c) == ln for c in str(r[col]).split("; ")):
                    return pty
        return known.get(ln, "?")
    oriented, detail = [], []
    for p in pairs:
        if p["type"] == "generic":
            oriented.append(p["d"]); detail.append({"type": "generic", "pollster": p["pollster"], "lv_minus_rv": round(p["d"], 2)})
            continue
        if p["type"] != "us-senator":
            continue
        pa = [party_of(c, p["subject"]) for c in p["c"]]
        if sorted(pa) != ["D", "R"]:
            continue
        iD, iR = pa.index("D"), pa.index("R")
        dd = 100 * (p["lv"][iD] - p["lv"][iR]) / (p["lv"][iD] + p["lv"][iR]) - 100 * (p["o"][iD] - p["o"][iR]) / (p["o"][iD] + p["o"][iR])
        oriented.append(dd); detail.append({"type": "senate", "pollster": p["pollster"], "race": str(p["subject"]).replace("2026 ", ""), "lv_minus_rv": round(dd, 2)})
    post = lv_posterior(oriented, pm, psd)
    post.update({"prior_mean": pm, "prior_sd": psd, "prior_by_cycle": {int(k): float(v) for k, v in cyc.items()},
                 "n_hist_pairs": int(len(h)), "pairs_2026": detail,
                 "mean_generic_2026": float(np.mean([x["lv_minus_rv"] for x in detail if x["type"] == "generic"])),
                 "mean_senate_2026": float(np.mean([x["lv_minus_rv"] for x in detail if x["type"] == "senate"])) if any(x["type"] == "senate" for x in detail) else None})
    return post


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    main()
