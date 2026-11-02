"""Pollster house effects (538-style) instead of a flat penalty for sponsored polls.

Data: 538 raw_polls.csv, general-election polls 2010-2022 (final 21 days), two-party margins.
  rel = poll margin - average of all polls of the same race       (+ = more Democratic than other polls)
  s   = +1 Democratic-sponsored, -1 Republican-sponsored, 0 otherwise
Model: rel = alpha_pollster + beta * s + e      (pollster fixed effects; beta = sponsor effect WITHIN a pollster)
  alpha shrunk toward 0 by empirical Bayes: alpha_shrunk = alpha_hat * tau^2 / (tau^2 + sigma^2 / n_pollster)
  Pollsters with no usable history: their sponsored polls get the average lean of sponsored polls from pollsters with
  thin history (< 10 polls), i.e. the old flat penalty, re-estimated on exactly the polls it applies to.
Adjustment applied to a 2026 poll (subtracted from its margin):  alpha_shrunk(pollster) + beta * s   (matched pollsters)
                                                               or  thin_sponsor_shift * s            (unmatched)
Validation: leave-one-cycle-out on the 2018/2022 Senate backtest (effects re-estimated without the test cycle).
Writes data/processed/pollster_effects.json
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT  # noqa: E402
import bias_analysis as BA  # noqa: E402

TYPES = ["Sen-G", "Gov-G", "House-G", "House-G-US", "Pres-G"]


def norm(name):
    s = str(name).lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(the|inc|llc|polling|poll|research|associates|and|group|strategies|university|college|survey|center)\b", " ", s)
    return " ".join(s.split())


def load_polls(r, exclude_cycle=None):
    s = r[r.type_simple.isin(TYPES) & (r.cycle >= 2010)].copy()
    if exclude_cycle is not None:
        s = s[s.cycle != exclude_cycle]
    s["miss"] = s.poll2 - s.act2
    s["rel"] = s.miss - s.groupby("race_id").miss.transform("mean")
    sp = s.partisan.fillna("").str.upper()
    s["s"] = np.where(sp == "DEM", 1, np.where(sp == "REP", -1, 0))
    s["pkey"] = s.pollster.map(norm)
    return s


def estimate(r, exclude_cycle=None):
    s = load_polls(r, exclude_cycle)
    n_p = s.groupby("pkey").size()
    s["thin"] = s.pkey.map(n_p) < 10
    fit = s[~s.thin]
    m = smf.ols("rel ~ C(pkey) + s", fit).fit()
    beta, beta_se = float(m.params["s"]), float(m.bse["s"])
    # raw pollster means net of the sponsor effect -> empirical-Bayes shrinkage
    fit = fit.assign(adj=fit.rel - beta * fit.s)
    g = fit.groupby("pkey").adj.agg(["mean", "size"])
    sigma2 = float(fit.groupby("pkey").adj.var().mean())
    tau2 = max(float(g["mean"].var() - (sigma2 / g["size"]).mean()), 0.05)
    g["alpha"] = g["mean"] * tau2 / (tau2 + sigma2 / g["size"])
    thin_sp = s[s.thin & (s.s != 0)]
    thin_shift = float((thin_sp.rel * thin_sp.s).mean()) if len(thin_sp) else 4.0
    tsw = thin_sp[thin_sp.type_simple.isin(["Sen-G", "Gov-G", "Pres-G"])]
    tsh = thin_sp[thin_sp.type_simple.isin(["House-G", "House-G-US"])]
    thin_by_level = {"statewide": float((tsw.rel * tsw.s).mean()) if len(tsw) else thin_shift,
                     "house": float((tsh.rel * tsh.s).mean()) if len(tsh) else thin_shift,
                     "n_statewide": int(len(tsw)), "n_house": int(len(tsh))}
    names = s.drop_duplicates("pkey").set_index("pkey").pollster
    return {"beta": beta, "beta_se": beta_se, "tau": float(np.sqrt(tau2)), "sigma": float(np.sqrt(sigma2)),
            "thin_sponsor_shift": thin_shift, "n_thin_sponsored": int(len(thin_sp)), "thin_by_level": thin_by_level,
            "alpha": {k: float(v) for k, v in g.alpha.items()}, "n": {k: int(v) for k, v in g["size"].items()},
            "display": {k: names[k] for k in g.index}}


def adjustment(est, pollster, sponsor_sign, mode="house"):
    """mode 'house': house effect + within-pollster sponsor effect; 'tiered': sponsor effect only (beta for pollsters with a
    record, thin-history shift otherwise), no general house effects."""
    k = norm(pollster)
    a = est["alpha"].get(k)
    if a is None:  # fuzzy: token-set Jaccard >= 0.6 with a unique best candidate
        kt = set(k.split())
        best, bj = None, 0.0
        for p in est["alpha"]:
            pt = set(p.split())
            if not pt or not kt:
                continue
            j = len(kt & pt) / len(kt | pt)
            if j > bj:
                best, bj = p, j
        if best is not None and bj >= 0.6:
            a, k = est["alpha"][best], best
    if a is not None:
        return (a if mode == "house" else 0.0) + est["beta"] * sponsor_sign, k
    return est["thin_sponsor_shift"] * sponsor_sign, None


def backtest_loco(r):
    """2018/2022 Senate backtest: flat sponsor shift vs pollster house effects (estimated without the test cycle)."""
    import backtest as BT
    import pollavg as PA
    p = pd.read_csv(sorted((ROOT / "data/raw/538_wayback").glob("*/senate_polls_historical.csv"))[-1], low_memory=False)
    p = p[p.cycle.isin([2018, 2022]) & (p.stage == "general") & (p.hypothetical != True)]  # noqa: E712
    p["end"] = pd.to_datetime(p.end_date, format="%m/%d/%y")
    act = r[r.type_simple == "Sen-G"].drop_duplicates("race_id").set_index("race_id").act2
    q = p[p.party.isin(["DEM", "REP"])].groupby(["question_id", "party"]).pct.max().unstack().dropna()
    q["m"] = 100 * (q.DEM - q.REP) / (q.DEM + q.REP)
    meta = p.drop_duplicates("question_id").set_index("question_id")[["race_id", "cycle", "pollster", "end", "sample_size", "population", "partisan"]]
    q = q.join(meta).rename(columns={"sample_size": "n"})
    q["population"] = q.population.fillna("lv").astype(str)
    q["s"] = np.where(q.partisan == "DEM", 1, np.where(q.partisan == "REP", -1, 0))
    out = {"sponsored_polls": {str(c): {"dem": int(((q.cycle == c) & (q.s == 1)).sum()), "rep": int(((q.cycle == c) & (q.s == -1)).sum()),
                                         "total": int((q.cycle == c).sum())} for c in (2018, 2022)}}
    keep_pe = PA.PE_EST
    PA.PE_EST = None        # BT.wavg must apply only the adjustment under test (flat = old 538-style flag penalty)
    for mode in ["flat", "house", "tiered"]:
        errs, briers, cycs = [], [], []
        for cyc in [2018, 2022]:
            est = estimate(r, exclude_cycle=cyc) if mode != "flat" else None
            cutoff = BT.ELECTION[cyc] - pd.Timedelta(days=5)
            for rid, g in q[q.cycle == cyc].groupby("race_id"):
                g = g[(g.end <= cutoff) & (g.end >= cutoff - pd.Timedelta(days=140))].copy()
                if g.empty or rid not in act.index:
                    continue
                if mode != "flat":
                    g["m"] = g.m - np.array([adjustment(est, pn, sg, mode)[0] for pn, sg in zip(g.pollster, g.s)])
                    g["partisan"] = None   # sponsor handled inside the adjustment
                avg, neff, spread, n = BT.wavg(g, cutoff, PA.HALF_LIFE)
                e = act[rid] - avg
                sd = np.sqrt(BT.SD_NAT ** 2 + BT.SD_RACE ** 2 + max(spread, 4.0) ** 2 / neff)
                from scipy import stats
                pdem = stats.t.cdf(avg / (sd * np.sqrt((BT.DF_T - 2) / BT.DF_T)), BT.DF_T)
                errs.append(e); briers.append((pdem - (act[rid] > 0)) ** 2); cycs.append(cyc)
        errs = np.array(errs)
        cyc_arr = np.array(cycs)
        within = np.concatenate([errs[cyc_arr == c] - errs[cyc_arr == c].mean() for c in (2018, 2022)])
        out[mode] = {"n": int(len(errs)), "rmse": float(np.sqrt(np.mean(errs ** 2))), "mae": float(np.mean(np.abs(errs))), "brier": float(np.mean(briers)),
                     "mean_err": float(errs.mean()), "mean_err_2018": float(errs[cyc_arr == 2018].mean()), "mean_err_2022": float(errs[cyc_arr == 2022].mean()),
                     "rmse_within_cycle": float(np.sqrt(np.mean(within ** 2)))}
    PA.PE_EST = keep_pe
    return out


def main():
    r = BA.load()
    est = estimate(r)
    print(f"within-pollster sponsor effect beta = {est['beta']:+.2f} (SE {est['beta_se']:.2f}) pts toward the sponsor")
    print(f"house-effect spread tau = {est['tau']:.2f}; poll noise sigma = {est['sigma']:.2f}; "
          f"thin-history sponsored polls lean {est['thin_sponsor_shift']:+.2f} toward sponsor (n={est['n_thin_sponsored']})")
    # 2026 pollsters
    d = json.loads(sorted((ROOT / "data/raw/votehub").glob("*/polls.json"))[-1].read_text(encoding="utf-8"))
    recent = [x for x in d if x["poll_type"] in ("us-senator", "us-representative") and x["end_date"] >= "2026-06-15"]
    cnt = pd.Series([(x["pollster"], (x.get("partisan") or "")) for x in recent]).value_counts()
    rows = []
    for (pn, sp), c in cnt.items():
        sg = 1 if sp.upper() == "DEM" else -1 if sp.upper() == "REP" else 0
        adj, k = adjustment(est, pn, sg, "house")
        adj_t, _ = adjustment(est, pn, sg, "tiered")
        flat = 4.3 * sg
        rows.append({"pollster": pn, "sponsor": sp, "polls_2026": int(c), "matched_538": est["display"].get(k) if k else None,
                     "n_hist": est["n"].get(k, 0) if k else 0, "house_effect": est["alpha"].get(k) if k else None,
                     "adj_house": adj, "adj_tiered": adj_t, "adj_flat_old": flat})
    tab = pd.DataFrame(rows).sort_values("polls_2026", ascending=False)
    print(tab.head(30).round(2).to_string(index=False))
    bt = backtest_loco(r)
    print("sponsored polls in backtest:", bt["sponsored_polls"])
    for k, v in bt.items():
        if k != "sponsored_polls":
            print("LOCO", k, {kk: round(vv, 3) for kk, vv in v.items()})
    est["backtest"] = bt
    pr = pd.read_csv(sorted((ROOT / "data/raw/538_github").glob("*/pollster-ratings-combined.csv"))[-1])
    est["partisan_work"] = {norm(n): float(v) for n, v in zip(pr.pollster, pr.percent_partisan_work) if pd.notna(v)}
    bl = ROOT / "data/processed/pollster_effects_bigloco.json"
    if not bl.exists():
        json.dump(big_loco(r), open(bl, "w"), indent=1)
    est["big_loco"] = json.loads(bl.read_text())
    print(f"thin-history sponsored shift: statewide {est['thin_by_level']['statewide']:+.2f} (n={est['thin_by_level']['n_statewide']}), "
          f"House districts {est['thin_by_level']['house']:+.2f} (n={est['thin_by_level']['n_house']})")
    est["table_2026"] = tab.round(3).to_dict("records")
    (ROOT / "data/processed/pollster_effects.json").write_text(json.dumps(est, indent=1, default=float))


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    main()


def big_loco(r):
    """Leave-one-cycle-out on 538 raw_polls itself: Senate + governor races 2010-2022, final-21-day polls.
    Per held-out cycle: estimate beta / thin shift / flat shift on the other cycles, adjust that cycle's polls,
    average each race's polls, score against the result. Paired comparison flat vs tiered per race."""
    base = r[r.type_simple.isin(["Sen-G", "Gov-G"]) & (r.cycle >= 2010)].copy()
    sp = base.partisan.fillna("").str.upper()
    base["s"] = np.where(sp == "DEM", 1, np.where(sp == "REP", -1, 0))
    rows = []
    for c in sorted(base.cycle.unique()):
        est = estimate(r, exclude_cycle=c)
        oth = load_polls(r, exclude_cycle=c)
        oth = oth[oth.type_simple.isin(["Sen-G", "Gov-G"])]
        flat = float((oth.rel * oth.s)[oth.s != 0].mean())
        te = base[base.cycle == c].copy()
        te["adj_flat"] = te.poll2 - flat * te.s
        te["adj_tier"] = te.poll2 - np.array([adjustment(est, pn, sg, "tiered")[0] for pn, sg in zip(te.pollster, te.s)])
        te["adj_house"] = te.poll2 - np.array([adjustment(est, pn, sg, "house")[0] for pn, sg in zip(te.pollster, te.s)])
        g = te.groupby("race_id").agg(act=("act2", "first"), flat=("adj_flat", "mean"), tier=("adj_tier", "mean"),
                                       house=("adj_house", "mean"), any_sp=("s", lambda x: (x != 0).any()))
        g["cycle"] = c
        rows.append(g)
    g = pd.concat(rows)
    res = {"n_races": int(len(g)), "n_races_with_sponsored": int(g.any_sp.sum())}
    for k in ["flat", "tier", "house"]:
        e = g.act - g[k]
        ew = e - e.groupby(g.cycle).transform("mean")
        res[k] = {"rmse": float(np.sqrt((e ** 2).mean())), "rmse_within": float(np.sqrt((ew ** 2).mean())),
                  "winners": float(((g[k] > 0) == (g.act > 0)).mean())}
    for k in ["tier", "house"]:
        for lab, sub in [("all", g), ("races_with_sponsored", g[g.any_sp])]:
            d = (sub.act - sub["flat"]) ** 2 - (sub.act - sub[k]) ** 2      # + = k better than flat
            dw = d.groupby(sub.race_id.map(lambda x: x) if False else sub.index).mean()
            res[f"paired_{k}_vs_flat_{lab}"] = {"mean_sq_err_gain": float(d.mean()), "se": float(d.std(ddof=1) / np.sqrt(len(d))), "n": int(len(d))}
    return res
