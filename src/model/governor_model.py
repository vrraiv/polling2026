"""Governors model (PLAN.md, "After the scorecard", item 4): estimation and backtest. Not part of the frozen forecast.

Data: data/interim/governor_dataset.csv (src/collect/governors.py): every governor race 1998-2025 with its result,
incumbency, prior presidential lean, national House vote, previous governor margin and final-three-week poll average.
Scored and fitted on two-way races (both a Democrat, or D-side, and a Republican; no third candidate at 15%+; no recalls).

Model, per race (two-party D-R margin):
  prior     = a + b*lean + g*environment + c*incumbent (+ p*previous governor margin, if it earns its place)
            environment: the national House vote when estimating; the final generic-ballot average when forecasting.
  polls     = final poll average; its race-level SD falls with the number of polls (calibration.json pollavg_sd_by_n,
              shared with the Senate model): sd_p(n) = sqrt(a^2 + b^2/n)
  mu        = w*polls + (1-w)*prior, w = sd_prior^2 / (sd_prior^2 + sd_p^2), with sd_prior implied by the estimated
              optimal weight on polls (as prior_weight.py does for the Senate); unpolled races: mu = prior, SD = the
              prior's robust error.
  national  two factors, t-distributed with a shared scale, correlation rho: S = the statewide-poll miss (governor
              races' cycle-mean result minus polls) and H = the generic-ballot miss. A race moves by
              w*S + (1-w)*g*H: polls carry the polls' miss, the prior carries the environment's.
  race      t-distributed race-level error with the race's SD. Degrees of freedom as the frozen forecast (3.9).

Backtest: each cycle 1998-2022 (even) and 2025, every parameter re-estimated without that cycle; the environment is
the final generic-ballot poll average (538 raw polls; VoteHub for 2025). Compared with polls only, prior only, and a
single-factor version (the frozen Senate structure: one national error at the statewide-poll SD for every race).
2024 enters the prior's comparison only: no 2024 governor polls are collected (538's archive ends in 2022).

Run:  python src/model/governor_model.py           estimate on all data, compare priors, backtest
Writes data/processed/governor_model.json, data/processed/governor_backtest.json and governor_backtest_races.csv
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT, latest  # noqa: E402

OUT = ROOT / "data" / "processed"
CAL = json.loads((OUT / "calibration.json").read_text())
SDN = CAL["pollavg_sd_by_n"]                                     # poll-average SD by number of polls
DF_T = float(json.loads((OUT / "poll_settings.json").read_text())["chosen"]["df_t"])
T_SCALE = np.sqrt((DF_T - 2) / DF_T)
N_SIM, SEED = 40000, 20261108
PRIOR_SPECS = {
    "lean": "margin_2p ~ lean_prev + env + inc",
    "lean_avg2": "margin_2p ~ lean_avg2 + env + inc",
    "lean_prevgov": "margin_2p ~ lean_prev + prev_gov_margin + env + inc",
    "lean_avg2_prevgov": "margin_2p ~ lean_avg2 + prev_gov_margin + env + inc",
}
ELECTION_2025 = pd.Timestamp("2025-11-04")
# error SD of the off-cycle environment estimate: its leave-one-election-out error on even years (environment.py)
_EO = OUT / "environment_offcycle.json"
ENV_SD = float(json.loads(_EO.read_text())["sd_env_offcycle"]) if _EO.exists() else 4.6


# ---------------- data ----------------
def load():
    d = pd.read_csv(ROOT / "data/interim/governor_dataset.csv")
    d = d[d.contested.astype(bool) & ~d.multi_candidate.astype(bool) & ~d.recall.astype(bool)].copy()
    d["env"] = d.nat_house                                   # estimation: realized national House vote
    d["polled"] = d.n_polls > 0
    d["miss"] = d.margin_2p - d.poll_avg                     # result minus polls (polled races)
    return d


def generic_final():
    """Final-three-week generic-ballot average (two-party, D-R) by cycle: 538 raw polls 1998-2022, VoteHub for 2025.
    Also the realized national House vote, so the generic miss per cycle is known."""
    import bias_analysis as BA
    g = BA.race_level(BA.load(), ["House-G-US"]).groupby("cycle").agg(generic=("poll", "mean"), generic_actual=("act", "first"))
    vh = json.loads(latest("votehub", "polls.json").read_text(encoding="utf-8"))
    vals = []
    for x in vh:
        if x.get("poll_type") != "generic-ballot":
            continue
        end = pd.Timestamp(x["end_date"])
        a = {y["choice"]: y["pct"] for y in x["answers"]}
        if ELECTION_2025 - pd.Timedelta(days=21) <= end <= ELECTION_2025 and "Dem" in a and "Rep" in a:
            vals.append(100 * (a["Dem"] - a["Rep"]) / (a["Dem"] + a["Rep"]))
    g.loc[2025, "generic"] = float(np.mean(vals)) if vals else np.nan
    g["generic_miss"] = g.generic_actual - g.generic
    return g


def sd_poll(n):
    return np.sqrt(SDN["a"] ** 2 + SDN["b"] ** 2 / np.maximum(n, 1))


# ---------------- estimation ----------------
def fit_prior(train, spec):
    tr = train[train.env.notna()]
    if "prev_gov" in spec:
        tr = tr[tr.prev_gov_margin.notna()]
    return smf.ols(PRIOR_SPECS[spec], tr).fit()


def prior_pred(model, df, fallback=None):
    """Prior for each race; races missing the previous governor margin fall back to the lean-only fit."""
    p = model.predict(df)
    if fallback is not None:
        p = p.fillna(fallback.predict(df))
    return p


def compare_priors(d):
    """Leave-one-cycle-out error of each prior specification, on even-year races 1998-2024 with every input available."""
    base = d[d.env.notna() & d.prev_gov_margin.notna() & d.lean_avg2.notna()]
    out = {}
    for spec in PRIOR_SPECS:
        err = []
        for y in sorted(base.year.unique()):
            m = fit_prior(base[base.year != y], spec)
            err.append(base[base.year == y].margin_2p - m.predict(base[base.year == y]))
        e = pd.concat(err)
        full = fit_prior(base, spec)
        out[spec] = {"n": int(len(e)), "loyo_rmse": float(np.sqrt((e ** 2).mean())), "loyo_mae": float(e.abs().mean()),
                     "coef": {k: float(v) for k, v in full.params.items()}, "se": {k: float(v) for k, v in full.bse.items()},
                     "r2": float(full.rsquared)}
    return out


def estimate(train, spec):
    """Every parameter of the model from the training races (and the training cycles' generic-ballot misses)."""
    prior = fit_prior(train, spec)
    fallback = fit_prior(train, "lean") if "prev_gov" in spec else None
    tr = train[train.env.notna()].copy()
    tr["prior"] = prior_pred(prior, tr, fallback)
    resid = tr.margin_2p - tr.prior
    # weight on polls: result - prior = w*(poll - prior) + cycle effect (national misses excluded, as prior_weight.py)
    pol = tr[tr.polled].copy()
    pol["y"], pol["x"], pol["yr"] = pol.margin_2p - pol.prior, pol.poll_avg - pol.prior, pol.year.astype(str)
    wfit = smf.ols("y ~ x + C(yr)", pol).fit()
    w = float(np.clip(wfit.params["x"], 0.01, 0.99))
    sd_p_typ = float(np.sqrt(np.mean(sd_poll(pol.n_polls) ** 2)))
    sd_prior_implied = sd_p_typ * np.sqrt(w / (1 - w))
    mad = np.median(np.abs(resid - np.median(resid)))
    # national factors from the training cycles: statewide-poll miss (governor races) and generic-ballot miss
    cyc = train[train.polled].groupby("year").miss.mean().rename("S").to_frame()
    cyc = cyc.join(GEN.generic_miss.rename("H"), how="inner").dropna()
    return {"prior": prior, "fallback": fallback, "spec": spec, "w": w, "w_se": float(wfit.bse["x"]),
            "sd_prior_implied": float(sd_prior_implied), "sd_prior_robust": float(1.4826 * mad), "sd_prior_raw": float(resid.std()),
            "g_env": float(prior.params["env"]),
            "sd_S": float(np.sqrt((cyc.S ** 2).mean())), "sd_H": float(np.sqrt((cyc.H ** 2).mean())),
            "rho": float(np.corrcoef(cyc.S, cyc.H)[0, 1]), "n_cycles_factors": int(len(cyc))}


# ---------------- forecast ----------------
def forecast(races, P, G, structure="two_factor", rng=None):
    """races: rows with lean_prev/lean_avg2, inc, prev_gov_margin, poll_avg, n_polls. G: environment (generic ballot).
    structure: two_factor | one_factor (every race moves with the statewide-poll factor) | polls_only | prior_only.
    Returns mu, sd, w, p_dem per race and the simulated D-wins count."""
    rng = rng or np.random.default_rng(SEED)
    df = races.copy()
    df["env"] = G
    df["prior"] = prior_pred(P["prior"], df, P["fallback"])
    sdp = sd_poll(df.n_polls)
    polled = df.n_polls > 0
    if structure == "polls_only":
        w = np.where(polled, 1.0, 0.0)
        sd = np.where(polled, sdp, P["sd_prior_robust"])
    elif structure == "prior_only":
        w = np.zeros(len(df))
        sd = np.full(len(df), P["sd_prior_robust"])
    else:
        sp = P["sd_prior_implied"]
        w = np.where(polled, sp ** 2 / (sp ** 2 + sdp ** 2), 0.0)
        sd = np.where(polled, 1 / np.sqrt(1 / sdp ** 2 + 1 / sp ** 2), P["sd_prior_robust"])
    df["w"], df["sd"] = w, sd
    df["mu"] = np.where(polled, w * df.poll_avg.fillna(0) + (1 - w) * df.prior, df.prior)
    # national factors: bivariate t (shared chi-square scale), unit variance after T_SCALE
    chi = np.sqrt(rng.chisquare(DF_T, N_SIM) / DF_T)
    z1 = rng.standard_normal(N_SIM)
    z2 = P["rho"] * z1 + np.sqrt(1 - P["rho"] ** 2) * rng.standard_normal(N_SIM)
    S, H = T_SCALE * z1 / chi * P["sd_S"], T_SCALE * z2 / chi * P["sd_H"]
    if structure == "one_factor":
        nat = S[:, None] * np.ones(len(df))[None, :]
    else:
        nat = S[:, None] * w[None, :] + (P["g_env"] * H)[:, None] * (1 - w)[None, :]
    eps = rng.standard_t(DF_T, (N_SIM, len(df))) * T_SCALE * sd[None, :]
    win = (df.mu.values[None, :] + nat + eps) > 0
    df["p_dem"] = win.mean(0)
    return df, win.sum(1)


# ---------------- environment for a cycle ----------------
def term_year(y):
    """Year of the presidential term an odd-year election falls in: 1 (NJ, VA) or 3 (KY, LA, MS)."""
    return 1 if y % 4 == 1 else 3 if y % 4 == 3 else None


_ENV_CACHE = {}


def env_parts(y):
    """(environment with m=0, change per unit of m) from src/model/environment.py's estimator, on Nov 5 of year y."""
    if y not in _ENV_CACHE:
        import environment as E
        model = E.fit(E.training())
        e0 = E.env_on(f"{y}-11-05", "fund", 0.0, model)[0]
        e1 = E.env_on(f"{y}-11-05", "fund", 1.0, model)[0]
        _ENV_CACHE[y] = (e0, e1 - e0)
    return _ENV_CACHE[y]


def fit_offcycle_m(train, P):
    """How midterm-like each term year's off-year electorate is (m), by least squares on the training off-year races'
    margins given the prior: margin - prior(env = e0) = g * slope * m."""
    out = {}
    tr = train[train.off_year].copy()
    if tr.empty:
        return {1: 1.0, 3: 1.0}
    tr["base"] = prior_pred(P["prior"], tr.assign(env=0.0), P["fallback"])
    g = P["g_env"]
    for ty in (1, 3):
        x = tr[tr.year.map(term_year) == ty]
        if x.empty:
            out[ty] = 1.0
            continue
        e0 = x.year.map(lambda y: env_parts(y)[0]); sl = x.year.map(lambda y: env_parts(y)[1])
        yv, xv = x.margin_2p - x.base - g * e0, g * sl
        out[ty] = float((xv * yv).sum() / (xv ** 2).sum())
    return out


def env_for(y, train, P):
    """(environment, its error SD, source) for a test cycle: the final generic-ballot average in even years that have
    one; otherwise the off-cycle estimator (presidential-year m=0 for 2024; odd years with their term year's m,
    fitted on the other off-year cycles)."""
    if y % 2 == 0 and pd.notna(GEN.generic.get(y)):
        return float(GEN.generic[y]), P["sd_H"], "generic ballot"
    e0, sl = env_parts(y)
    if y % 2 == 0:
        return e0, ENV_SD, "estimator (presidential year)"
    m = fit_offcycle_m(train, P)[term_year(y)]
    return e0 + sl * m, ENV_SD, f"estimator (term year {term_year(y)}, m={m:.2f})"


# ---------------- backtest ----------------
def backtest(d, spec):
    cycles = sorted(set(d.year))
    rows, counts = [], []
    for y in cycles:
        train, test = d[d.year != y], d[d.year == y]
        if test.empty:
            continue
        P = estimate(train, spec)
        G, sdH, src = env_for(y, train, P)
        P = dict(P, sd_H=sdH)
        for structure in ("two_factor", "one_factor", "polls_only", "prior_only"):
            f, dwins = forecast(test, P, G, structure, np.random.default_rng(SEED + y))
            f["structure"], f["y"] = structure, (f.margin_2p > 0).astype(int)
            rows.append(f[["year", "state", "structure", "y", "p_dem", "mu", "sd", "w", "prior", "poll_avg", "n_polls", "margin_2p"]])
            actual = int(f.y.sum())
            counts.append({"year": int(y), "structure": structure, "n": len(f), "n_polled": int((f.n_polls > 0).sum()),
                           "env": float(G), "env_source": src, "d_wins": actual, "expected": float(f.p_dem.sum()),
                           "pit": float((dwins < actual).mean() + 0.5 * (dwins == actual).mean()),
                           "in_80": bool(np.percentile(dwins, 10) <= actual <= np.percentile(dwins, 90))})
        print(f"  {y}: {len(test)} races, env {G:+.1f} ({src}), w {P['w']:.2f}, rho {P['rho']:.2f}", file=sys.stderr)
    return pd.concat(rows, ignore_index=True), pd.DataFrame(counts)


def scores(r, c):
    out = {}
    for s, g in r.groupby("structure"):
        p = g.p_dem.clip(1e-4, 1 - 1e-4)
        cc = c[c.structure == s]
        bins = pd.cut(g.p_dem, [0, .1, .3, .5, .7, .9, 1], include_lowest=True)
        out[s] = {"n": int(len(g)), "brier": float(((g.p_dem - g.y) ** 2).mean()),
                  "log_loss": float(-(g.y * np.log(p) + (1 - g.y) * np.log(1 - p)).mean()),
                  "accuracy": float(((g.p_dem > 0.5) == (g.y == 1)).mean()),
                  "mae_margin": float((g.margin_2p - g.mu).abs().mean()),
                  "calibration": [{"bin": str(b), "n": int(len(x)), "forecast": float(x.p_dem.mean()), "d_won": float(x.y.mean())}
                                  for b, x in g.groupby(bins, observed=True)],
                  "count_in_80pct": float(cc.in_80.mean()), "count_pit": [round(v, 3) for v in cc.pit],
                  "competitive_brier": float(((g[g.p_dem.between(.1, .9)].p_dem - g[g.p_dem.between(.1, .9)].y) ** 2).mean())}
    return out


def main():
    global GEN
    GEN = generic_final()
    d = load()
    priors = compare_priors(d)
    best = min(priors, key=lambda k: priors[k]["loyo_rmse"])
    P = estimate(d, best)
    r, c = backtest(d, best)
    src = c.drop_duplicates("year").set_index("year").env_source
    r["env_source"] = r.year.map(src)
    groups = {"all": r, "generic-ballot cycles (1998-2022)": r[r.env_source == "generic ballot"],
              "off-year cycles (estimator)": r[r.year % 2 == 1], "2024 (environment estimator; Wikipedia polls)": r[r.year == 2024],
              "unpolled races": r[r.n_polls == 0]}
    sc = {k: scores(v, c[c.year.isin(v.year.unique())]) for k, v in groups.items() if len(v)}
    model = {"note": "governors model, estimated on all two-way races 1998-2025 (see module docstring)",
             "prior_comparison": priors, "prior_chosen": best,
             "params": {k: v for k, v in P.items() if k not in ("prior", "fallback")},
             "prior_coef": {k: float(v) for k, v in P["prior"].params.items()},
             "offcycle_m": fit_offcycle_m(d, P), "env_sd_offcycle": ENV_SD,
             "generic_by_cycle": GEN.round(3).reset_index().rename(columns={"cycle": "year", "index": "year"}).to_dict("records"),
             "n_races": int(len(d)), "n_polled": int(d.polled.sum())}
    (OUT / "governor_model.json").write_text(json.dumps(model, indent=1, default=float))
    (OUT / "governor_backtest.json").write_text(json.dumps({"scores": sc, "counts": c.to_dict("records")}, indent=1, default=float))
    r.round(4).to_csv(OUT / "governor_backtest_races.csv", index=False)
    show(priors, best, P, sc, c)
    print("off-cycle m by term year (all data):", {k: round(v, 2) for k, v in model["offcycle_m"].items()},
          f"| 2025 generic ballot was {GEN.generic.get(2025, float('nan')):+.1f}")


def show(priors, best, P, sc, c):
    pd.set_option("display.width", 200)
    print("prior specs (leave-one-cycle-out):")
    for k, v in priors.items():
        print(f"  {k:20s} n={v['n']} rmse {v['loyo_rmse']:.2f} mae {v['loyo_mae']:.2f} r2 {v['r2']:.2f} {({a: round(b, 2) for a, b in v['coef'].items()})}")
    print("chosen:", best, {k: round(v, 3) for k, v in P.items() if isinstance(v, float)})
    for grp, x in sc.items():
        t = pd.DataFrame({st: {k: v for k, v in y.items() if not isinstance(v, list)} for st, y in x.items()}).T
        print(f"--- {grp}"); print(t[["n", "brier", "log_loss", "accuracy", "mae_margin", "count_in_80pct"]].round(4).to_string())
    print("calibration (two_factor, all):", [(b["bin"], b["n"], round(b["forecast"], 2), round(b["d_won"], 2)) for b in sc["all"]["two_factor"]["calibration"]])
    print(c[c.structure == "two_factor"][["year", "n", "n_polled", "env", "env_source", "d_wins", "expected", "pit", "in_80"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
