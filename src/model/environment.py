"""National environment on an off-cycle date (PLAN.md items 4 and 5): what the national House vote would be, for a race
held when there is no House election to poll (odd-year governors, special elections).

Estimators, using only what is known on the date:
  prev_vote   the last national House vote, carried forward.
  fund_m*     president's-party House margin = a + b*approval + c*previous House margin + d*m, fitted on every
              election 1946-2022 (data/interim/fundamentals_dataset.csv, midterm flag as d); m is how midterm-like an
              off-cycle date is (0 = like a presidential year, 1 = like a midterm). Approval: Gallup, mean of polls in
              the ~15 weeks before the date (as fundamentals.py uses Jul 15 - Oct 31 for November elections); the 538
              archive's Gallup polls for 2021-2024; VoteHub's average plus the Gallup house effect from 2025.

Test: odd-year governor races 1999-2025 (two-way, no recalls), scored with the governor prior (src/model/governor_model.py)
fitted on even years only, so every odd-year race is held out. Also the environment each odd year's results imply
(inverting the prior), against each estimator. Error SD for the backtest's environment factor: the estimator's
leave-one-election-out error on even years.

Run:  python src/model/environment.py
Writes data/processed/environment_offcycle.json
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
INTERIM = ROOT / "data" / "interim"
M_VALUES = (0.0, 0.5, 1.0)
WINDOW_DAYS = 108          # Jul 15 - Oct 31 before a November election, generalized to any date
LAG_DAYS = 4


# ---------------- inputs on a date ----------------
def _gallup_sheet():
    return pd.read_csv(INTERIM / "gallup_approval.csv", parse_dates=["end"])


def _gallup_538():
    g = pd.read_csv(latest("538_wayback", "president_approval_polls_historical.csv"), low_memory=False)
    g["end"] = pd.to_datetime(g.end_date, format="%m/%d/%y", errors="coerce")
    return g[g.pollster.str.contains("Gallup", na=False)]


def _votehub_trump():
    vh = json.loads(latest("votehub", "polls.json").read_text(encoding="utf-8"))
    rows = [(pd.Timestamp(x["end_date"]), next(a["pct"] for a in x["answers"] if a["choice"] == "Approve"))
            for x in vh if x.get("poll_type") == "approval" and x.get("subject") == "Donald Trump"
            and any(a["choice"] == "Approve" for a in x["answers"])]
    return pd.DataFrame(rows, columns=["end", "approve"])


def approval_on(date):
    """(approval, source): Gallup-scale presidential approval over the window before the date."""
    date = pd.Timestamp(date)
    lo, hi = date - pd.Timedelta(days=WINDOW_DAYS), date - pd.Timedelta(days=LAG_DAYS)
    s = _gallup_sheet()
    w = s[(s.end >= lo) & (s.end <= hi)]
    if len(w) and date <= pd.Timestamp("2021-01-15"):
        return float(w.Approving.mean()), "Gallup (APP sheet)"
    g = _gallup_538()
    w = g[(g.end >= lo) & (g.end <= hi)]
    if len(w):
        return float(w.yes.mean()), "Gallup (538 archive)"
    if date >= pd.Timestamp("2025-01-20"):
        import fundamentals as FM
        offset = FM.gallup_house_effect()[0]
        v = _votehub_trump()
        w = v[(v.end >= lo) & (v.end <= hi)]
        if len(w):
            return float(w.approve.mean() + offset), f"VoteHub mean of {len(w)} polls + Gallup house effect {offset:+.1f}"
    return np.nan, "missing"


def president_party(date):
    """Party in the White House on the date (inaugurations on Jan 20)."""
    terms = [(1945, "D"), (1953, "R"), (1961, "D"), (1969, "R"), (1977, "D"), (1981, "R"), (1993, "D"), (2001, "R"),
             (2009, "D"), (2017, "R"), (2021, "D"), (2025, "R")]
    date = pd.Timestamp(date)
    return [p for y, p in terms if date >= pd.Timestamp(f"{y}-01-20")][-1]


def last_house_vote(date):
    v = pd.read_csv(INTERIM / "house_national_vote.csv").set_index("year").two_party_margin_D
    y = max(yr for yr in v.index if pd.Timestamp(f"{yr}-11-01") < pd.Timestamp(date))
    return float(v[y]), int(y)


# ---------------- the estimator ----------------
def training():
    f = pd.read_csv(INTERIM / "fundamentals_dataset.csv")
    return f[f.outcome.notna() & f.approval.notna() & f.prev.notna()].copy()


def fit(train):
    return smf.ols("outcome ~ approval + prev + midterm", train).fit()


def loyo_rmse(train):
    e = [r.outcome - fit(train[train.year != r.year]).predict(train[train.year == r.year]).iloc[0] for _, r in train.iterrows()]
    return float(np.sqrt(np.mean(np.square(e)))), int(len(e))


def env_on(date, kind="fund", m=1.0, model=None):
    """National environment (D-R House margin) on a date. kind: prev_vote | fund."""
    prev_d, prev_year = last_house_vote(date)
    if kind == "prev_vote":
        return prev_d, {"prev_year": prev_year}
    party = president_party(date)
    sign = 1 if party == "D" else -1
    appr, src = approval_on(date)
    model = model or fit(training())
    pred = float(model.predict(pd.DataFrame({"approval": [appr], "prev": [sign * prev_d], "midterm": [m]})).iloc[0])
    return sign * pred, {"prev_year": prev_year, "approval": appr, "approval_source": src, "president": party}


# ---------------- test on odd-year governor races ----------------
def main():
    import governor_model as GV
    tr = training()
    model = fit(tr)
    rmse, n = loyo_rmse(tr)
    check = {int(r.year): round(float(r.approval) - approval_on(f"{int(r.year)}-11-05")[0], 2)
             for _, r in tr[tr.year >= 1962].iterrows()}
    d = GV.load()
    even = d[d.env.notna()]
    prior = GV.fit_prior(even, "lean_avg2")
    odd = d[d.off_year].copy()
    # the prior without its environment term; the environment each odd year's results imply
    odd["base"] = prior.predict(odd.assign(env=0.0))
    g = float(prior.params["env"])
    rows, per_year = [], []
    for y, grp in odd.groupby("year"):
        date = f"{y}-11-05"
        cands = {"prev_vote": env_on(date, "prev_vote")[0]}
        info = env_on(date, "fund", 1.0, model)[1]
        for m in M_VALUES:
            cands[f"fund_m{m:g}"] = env_on(date, "fund", m, model)[0]
        implied = float(((grp.margin_2p - grp.base) / g).mean())
        per_year.append({"year": int(y), "n": len(grp), "states": ",".join(grp.state), "implied_env": implied, **cands, **info})
        for k, e in cands.items():
            pr = grp.base + g * e
            rows += [{"year": int(y), "state": s, "estimator": k, "env": e, "err": float(a - p)} for s, a, p in zip(grp.state, grp.margin_2p, pr)]
    r = pd.DataFrame(rows)
    py = pd.DataFrame(per_year)
    summ = r.groupby("estimator").err.agg(n="size", mean="mean", rmse=lambda x: float(np.sqrt((x ** 2).mean())), mae=lambda x: float(x.abs().mean()))
    env_err = {k: {"rmse_vs_implied": float(np.sqrt(np.average((py[k] - py.implied_env) ** 2, weights=py.n))),
                   "mean_vs_implied": float(np.average(py[k] - py.implied_env, weights=py.n))} for k in summ.index}
    best = summ.rmse.idxmin()
    out = {"question": "What national environment should an off-cycle race use?",
           "fund_model": {k: float(v) for k, v in model.params.items()}, "fund_model_se": {k: float(v) for k, v in model.bse.items()},
           "fund_loyo_rmse_even_years": rmse, "fund_n_elections": n,
           "approval_check_vs_fundamentals_dataset": check,
           "prior_env_coef": g, "race_errors": summ.reset_index().to_dict("records"), "env_errors_vs_implied": env_err,
           "by_year": py.round(2).to_dict("records"), "chosen": best,
           "sd_env_offcycle": rmse,
           "note": "implied_env inverts the even-year governor prior on each odd year's results; it is noisy with 2-4 races per year"}
    (OUT / "environment_offcycle.json").write_text(json.dumps(out, indent=1, default=float))
    pd.set_option("display.width", 220)
    print("fundamentals-style model:", {k: round(v, 3) for k, v in model.params.items()}, "| LOYO RMSE on", n, "elections:", round(rmse, 2))
    print("approval vs fundamentals_dataset (should be ~0):", {k: v for k, v in check.items() if abs(v) > 0.5} or "all within 0.5")
    print(summ.round(2).to_string())
    print({k: {a: round(b, 2) for a, b in v.items()} for k, v in env_err.items()})
    print(py[["year", "n", "states", "president", "approval", "implied_env", "prev_vote", "fund_m0", "fund_m0.5", "fund_m1"]].round(1).to_string(index=False))
    print("chosen:", best)


if __name__ == "__main__":
    main()
