"""Historical data exploration + 2026 post-mortem: a state-level shared error for House districts.

The frozen model's correlated layers are national, Census region (SD 0.48) and a slope on lean. NC 2026 (four
upsets at ~5% each, one state) suggested districts in the same state miss together.

  estimate     House history 2006-2024 (data/interim/house_history.csv, contested races): residuals after region x
               cycle effects (absorbs the national environment and the model's region layer), lean x cycle (the
               slope layer) and incumbency x cycle; the share of residual variance common to a state and cycle
               (REML random effect and method of moments), by subset and year, a placebo (states shuffled within
               region-cycle), and the largest state-cycle shocks.
  sim_2026     the frozen P+F House forecast re-simulated with a state shock carved out of each district's
               race-level variance (total variance unchanged): seat range, Brier, and the chance of NC/OH/TX's
               results, unconditionally and with the environment fixed at D+15.
  test_redraw  is the shock larger in the first cycle under a new map? Redraws: 2012 and 2022 everywhere, plus the
               mid-decade redraws in MID_DECADE.
  test_band    gerrymandering signature: is the shock larger where many districts sit in a lean-but-not-safe band,
               and do districts leaning modestly against a wave move more than a linear swing (wave years only)?
  test_offices is the House state shock shared with the same state's Senate and governor results, and do those
               races' polls see it?
  test_persist does a state's shock carry into its next cycle, and does that predict out of sample?

    python src/postmortem/state_error.py            everything (~5 min)
    python src/postmortem/state_error.py --no-sim   history only

Writes data/postmortem/state_error.json.
"""
import sys
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import frozen as F

warnings.filterwarnings("ignore")          # MixedLM convergence chatter on single-year subsets

# Mid-decade congressional redraws in the history. Found as breaks in a state's district-by-district Cook PVI between
# consecutive cycles (correlation < 0.95 or mean absolute change, net of the state's median change, > 2.5 points;
# states with 5+ districts), each checked against a known court-ordered or legislative redraw. Breaks dropped as
# artifacts: district-count glitches (LA 2008, TX 2008, ME 2020/2024), PVI-formula updates (IL 2018, MN 2018, TN 2010)
# and two- or three-district noise (UT 2008, WV 2014).
MID_DECADE = {("FL", 2016), ("VA", 2016), ("NC", 2016), ("PA", 2018), ("NC", 2020),
              ("AL", 2024), ("GA", 2024), ("LA", 2024), ("NC", 2024)}
CENSUS_REDRAW_YEARS = {2012, 2022}
STATE_SDS = [3.3, 5.0]
N_SIM, SEED = 40000, 20261108


# ---------------- history ----------------
def history():
    h = pd.read_csv(F.INTERIM / "house_history.csv")
    h = h[h.contested & h.margin.notna()].copy()
    h["region"] = h.state.map(F.STATE_REGION).fillna("South")
    h["ry"], h["sy"], h["yr"] = h.region + h.year.astype(str), h.state + h.year.astype(str), h.year.astype(str)
    fit = smf.ols("margin ~ C(ry) + lean2:C(yr) + inc:C(yr)", h).fit()
    h["resid"], h["fitted"] = fit.resid, fit.fittedvalues
    h["redraw"] = h.year.isin(CENSUS_REDRAW_YEARS) | pd.Series(list(zip(h.state, h.year)), index=h.index).isin(MID_DECADE)
    return h


def components(d):
    """State-cycle variance component: REML random intercept, and method of moments on state-cycles with 2+ districts."""
    m = smf.mixedlm("resid ~ 1", d, groups=d["sy"]).fit(reml=True)
    s2_state, s2_e = float(m.cov_re.iloc[0, 0]), float(m.scale)
    g = d.groupby("sy").resid.agg(["mean", "var", "size"])
    g = g[g["size"] >= 2]
    within = np.average(g["var"], weights=g["size"] - 1)
    nbar = (g["size"].sum() - (g["size"] ** 2).sum() / g["size"].sum()) / (len(g) - 1)
    between = (g["size"] * (g["mean"] - np.average(g["mean"], weights=g["size"])) ** 2).sum() / (len(g) - 1)
    return {"n": len(d), "state_cycles": int(d.sy.nunique()), "sd_state_reml": np.sqrt(s2_state), "sd_idio_reml": np.sqrt(s2_e),
            "share_of_variance": s2_state / (s2_state + s2_e), "sd_state_mom": np.sqrt(max((between - within) / nbar, 0))}


def state_cycles(h, sigma_e):
    """One row per state-cycle (2+ districts): mean residual, n, and the excess of mean^2 over its sampling variance,
    an unbiased estimate of the shock variance for that state-cycle."""
    g = h.groupby(["state", "year"]).agg(n=("resid", "size"), shock=("resid", "mean"), redraw=("redraw", "first"),
                                         band=("pvi", lambda p: ((p.abs() >= 2) & (p.abs() <= 8)).mean())).reset_index()
    g = g[g.n >= 2].copy()
    g["excess"] = g.shock ** 2 - sigma_e ** 2 / g.n
    return g


def shock_sd(g, rng, n_boot=2000):
    """SD of the state shock in a set of state-cycles, with a bootstrap 90% interval over state-cycles."""
    est = lambda x: np.sqrt(max(x.mean(), 0))
    e = g.excess.values
    boots = [est(e[rng.integers(0, len(e), len(e))]) for _ in range(n_boot)]
    return {"n_state_cycles": len(g), "sd_state": est(e), "ci90": [float(np.percentile(boots, 5)), float(np.percentile(boots, 95))]}


def estimate(h):
    subsets = {"all contested": h, "competitive (|fitted| <= 15)": h[h.fitted.abs() <= 15], "midterms": h[h.year % 4 == 2],
               "competitive midterms": h[(h.fitted.abs() <= 15) & (h.year % 4 == 2)]}
    rows = [{"subset": k, **components(d)} for k, d in subsets.items()]
    rows += [{"subset": f"year {y}", **components(h[h.year == y])} for y in sorted(h.year.unique())]
    rng = np.random.default_rng(1)
    p = h.copy()
    p["sy"] = p.groupby("ry").sy.transform(lambda s: rng.permutation(s.values))
    g = h.groupby(["state", "year"]).agg(n=("resid", "size"), shock=("resid", "mean")).reset_index()
    top = g[g.n >= 4].reindex(g[g.n >= 4].shock.abs().sort_values(ascending=False).index).head(15)
    return {"residual_sd": float(h.resid.std()), "components": rows, "placebo_sd_state": components(p)["sd_state_reml"],
            "model_region_sd": F.SIGMA_REGION, "largest_shocks_4plus_districts": top.round(2).to_dict("records")}


def test_redraw(g, rng):
    mid_years = sorted({y for _, y in MID_DECADE})
    same_years = g[g.year.isin(mid_years)]
    return {"first_cycle_new_map": shock_sd(g[g.redraw], rng), "other_cycles": shock_sd(g[~g.redraw], rng),
            "census_redraw_years": shock_sd(g[g.year.isin(CENSUS_REDRAW_YEARS)], rng),
            "mid_decade_redraws": shock_sd(same_years[same_years.redraw], rng),
            "same_years_not_redrawn": shock_sd(same_years[~same_years.redraw], rng),
            "note": "2012/2022 redraws are confounded with their years; the mid-decade rows compare redrawn and not-redrawn states in the same cycles"}


def test_band(h, g, rng):
    # (a) state level: is the shock larger where many districts lean but aren't safe (|PVI| 2-8)?
    k = g.n >= 3
    hi = g[k & (g.band >= g[k].band.median())]
    lo = g[k & (g.band < g[k].band.median())]
    fit = smf.wls("excess ~ band", g[k], weights=g[k].n).fit()
    # (b) district level: residual SD by |PVI| band
    h = h.copy()
    h["abs_band"] = pd.cut(h.pvi.abs(), [-0.1, 2, 5, 8, 12, 20, 60]).astype(str)
    by_abs = h.groupby("abs_band").resid.agg(["size", "std"]).reset_index().round(2)
    # (c) wave years: districts leaning against the wave, by how much; residual oriented toward the wave
    nat = h.groupby("year").nat.first()
    waves = nat[nat.abs() >= 5]
    w = h[h.year.isin(waves.index)].copy()
    sgn = np.sign(w.year.map(waves))
    w["lean_vs_wave"], w["resid_toward_wave"] = w.lean2 * sgn, w.resid * sgn
    w["band"] = pd.cut(w.lean_vs_wave, [-80, -24, -16, -10, -4, 4, 16, 80]).astype(str)
    w["inc_against_wave"] = (w.inc * sgn) < 0
    by_lean = w.groupby("band").agg(n=("resid", "size"), mean_resid_toward_wave=("resid_toward_wave", "mean"),
                                    se=("resid_toward_wave", lambda x: x.std() / np.sqrt(len(x)))).reset_index().round(2)
    by_lean_inc = w.groupby(["band", "inc_against_wave"]).agg(n=("resid", "size"), mean_resid_toward_wave=("resid_toward_wave", "mean")).reset_index().round(2)
    return {"state_level": {"high_band_share": shock_sd(hi, rng), "low_band_share": shock_sd(lo, rng),
                            "wls_excess_on_band_share": {"slope": fit.params.band, "se": fit.bse.band, "p": fit.pvalues.band}},
            "district_resid_sd_by_abs_pvi": by_abs.to_dict("records"),
            "wave_years": {str(int(y)): float(v) for y, v in waves.items()},
            "wave_by_lean_vs_wave": by_lean.to_dict("records"), "wave_by_lean_and_incumbent": by_lean_inc.to_dict("records"),
            "note": "lean x cycle is already removed, so the wave rows show departures from a linear swing; lean_vs_wave < 0 = the district leans against the wave (margin units, 2*PVI)"}


def test_offices(g):
    b = pd.read_csv(F.FINAL / "bias_race_level.csv").rename(columns={"location": "state", "cycle": "year"})
    b["region"] = b.state.map(F.STATE_REGION).fillna("South")
    out = {}
    for office in ("Sen-G", "Gov-G"):
        d = b[b.type_simple == office].copy()
        d["struct_resid"] = smf.ols("act ~ lean + C(year) + C(region)", d).fit().resid
        j = d.merge(g[["state", "year", "shock", "n"]].rename(columns={"n": "n_house"}), on=["state", "year"])
        cs = float(np.corrcoef(j.shock, j.struct_resid)[0, 1])
        cp = float(np.corrcoef(j.shock, j.err)[0, 1])
        slope = smf.wls("shock ~ struct_resid", j, weights=j.n_house).fit()
        out[office] = {"n": len(j), "corr_house_shock_vs_result_resid": cs, "corr_house_shock_vs_poll_miss": cp,
                       "house_shock_per_point_of_result_resid": slope.params.struct_resid, "se": slope.bse.struct_resid}
    out["note"] = ("result_resid: the race's result against lean + cycle + region (no polls). poll_miss: result minus the "
                   "final poll average. If the House shock tracks result_resid but not poll_miss, the statewide race's "
                   "polls already saw the state's shift, and could inform its House districts.")
    return out


def test_persist(g):
    g = g.set_index(["state", "year"])
    rows = []
    for (st, y), r in g.iterrows():
        if (st, y - 2) in g.index:
            rows.append({"state": st, "year": y, "shock": r.shock, "prev": g.loc[(st, y - 2), "shock"], "n": r.n, "redraw": r.redraw})
    p = pd.DataFrame(rows)
    out = {"corr_all": float(np.corrcoef(p.shock, p.prev)[0, 1]), "n_pairs": len(p),
           "corr_same_map": float(np.corrcoef(p[~p.redraw].shock, p[~p.redraw].prev)[0, 1]), "n_same_map": int((~p.redraw).sum()),
           "corr_across_redraw": float(np.corrcoef(p[p.redraw].shock, p[p.redraw].prev)[0, 1]), "n_across_redraw": int(p.redraw.sum())}
    # leave-one-cycle-out: carry k * last cycle's shock forward, k fitted on the other cycles
    mse0 = mse1 = 0.0
    for y in sorted(p.year.unique()):
        tr, te = p[p.year != y], p[p.year == y]
        k = np.sum(tr.n * tr.shock * tr.prev) / np.sum(tr.n * tr.prev ** 2)
        mse0 += np.sum(te.n * te.shock ** 2)
        mse1 += np.sum(te.n * (te.shock - k * te.prev) ** 2)
    out["loyo_mse_reduction"] = 1 - mse1 / mse0
    out["k_all"] = float(np.sum(p.n * p.shock * p.prev) / np.sum(p.n * p.prev ** 2))
    return out


# ---------------- 2026 ----------------
def sim_2026():
    v = "polls_fundamentals"
    sc, nat = F.scorecard(), F.national(v)
    h = F.races(v, "house")
    hf, hc = h[h.fixed.notna()], h[h.fixed.isna()].reset_index(drop=True)
    called = F.called("house", sc).set_index("race_key")
    k = hc.race_key.isin(called.index).values
    y = called.y.reindex(hc.race_key).values
    states = sorted(hc.state.unique())
    sidx = hc.state.map({s: i for i, s in enumerate(states)}).values
    fav = (hc.p_dem > 0.5).values
    actual_up = pd.Series(((fav != (y == 1)) & k), index=hc.state).groupby(level=0).sum()
    out = {"actual_states_with_3plus_upsets": int((actual_up >= 3).sum()), "actual_upsets_by_state": actual_up[actual_up >= 2].to_dict(), "runs": []}
    for env in (None, 15.0):
        rng = np.random.default_rng(SEED)
        region = rng.standard_normal((N_SIM, len(F.REGIONS))) * F.SIGMA_REGION
        slope = rng.standard_normal(N_SIM) * F.SIGMA_SLOPE
        shift = (F.G_NAT * nat["sd_nat_house_used"] * rng.standard_t(F.DF_T, N_SIM) * F.T_SCALE if env is None
                 else F.G_NAT * (env - nat["G_used"]))
        base_shock = rng.standard_normal((N_SIM, len(states)))
        for sd in [0.0] + STATE_SDS:
            w = F.draw_wins(hc, rng, N_SIM, shift, region, slope, state_shock=base_shock * sd, state_sd=sd)
            seats = int((hf.fixed == "D").sum()) + w.sum(1)
            p = w.mean(0)
            run = {"environment": "as forecast" if env is None else f"fixed at D+{env:g}", "state_sd": sd,
                   "house_d_p10": np.percentile(seats, 10), "house_d_p90": np.percentile(seats, 90),
                   "brier_called": float(((p[k] - y[k]) ** 2).mean())}
            for st in ("NC", "OH", "TX"):
                m = (hc.state == st).values & k
                actual = int(y[m].sum())
                run[f"p_{st}_d_at_least_{actual}_of_{int(m.sum())}"] = float((w[:, m].sum(1) >= actual).mean())
            ups = (w != fav[None, :]) & k[None, :]
            per_state = np.stack([ups[:, sidx == i].sum(1) for i in range(len(states))], 1)
            run["mean_states_with_3plus_upsets"] = float((per_state >= 3).sum(1).mean())
            out["runs"].append(run)
            print(f"  sim {run['environment']} sd={sd}", file=sys.stderr)
    out["note"] = ("P+F House. The state shock is carved out of each district's race-level variance, so single-race "
                   "probabilities (and Brier) barely move; what changes is how districts in one state move together.")
    return out


def main(do_sim=True):
    rng = np.random.default_rng(SEED)
    h = history()
    est = estimate(h)
    sigma_e = next(r for r in est["components"] if r["subset"] == "all contested")["sd_idio_reml"]
    g = state_cycles(h, sigma_e)
    out = {"question": "Do House districts in the same state share an error the frozen model left out?",
           "estimate": est, "test_redraw": test_redraw(g, rng), "test_band": test_band(h, g, rng),
           "test_offices": test_offices(g), "test_persist": test_persist(g)}
    if do_sim:
        out["sim_2026"] = sim_2026()
    F.write("state_error.json", out)
    show(out)


def show(o):
    pd.set_option("display.width", 200)
    print(pd.DataFrame(o["estimate"]["components"]).round(2).to_string(index=False))
    print("placebo", round(o["estimate"]["placebo_sd_state"], 2))
    for k in ("test_redraw", "test_offices", "test_persist"):
        print(k, {a: b for a, b in o[k].items() if a != "note"})
    tb = o["test_band"]
    print("test_band state level", tb["state_level"])
    print(pd.DataFrame(tb["district_resid_sd_by_abs_pvi"]).to_string(index=False))
    print("waves", tb["wave_years"]); print(pd.DataFrame(tb["wave_by_lean_vs_wave"]).to_string(index=False))
    print(pd.DataFrame(tb["wave_by_lean_and_incumbent"]).to_string(index=False))
    if "sim_2026" in o:
        print(pd.DataFrame(o["sim_2026"]["runs"]).round(4).to_string(index=False))


if __name__ == "__main__":
    main(do_sim="--no-sim" not in sys.argv)
