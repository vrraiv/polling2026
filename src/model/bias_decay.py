"""Decay-weighted estimate of the 2026 generic-ballot polling bias.

Data: two-party generic-ballot miss per cycle, 1998-2022 (538 raw_polls.csv; see bias_analysis.py).
Positive = Democrats beat their polls.

Weights: w = 0.5 ** ((2026 - cycle) / H) * (M if midterm else 1)
Covariates (all signed so that a positive coefficient = Democrats beat polls):
  pres_D        Democrat in the White House
  house_D       Democrats hold the House going into the election (House incumbency)
  second_term   president in a second term (2026: Trump, second non-consecutive term)
  president     specific occupant, as a random effect shrunk toward the fitted mean (empirical Bayes)
Model choice by weighted leave-one-cycle-out (LOO) prediction error.
Writes data/processed/bias_decay.json
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT  # noqa: E402
import bias_analysis as BA  # noqa: E402

CYCLE_INFO = {  # president, party, term, House majority going into the election
    1998: ("Clinton", "D", 2, "R"), 2000: ("Clinton", "D", 2, "R"), 2002: ("Bush", "R", 1, "R"),
    2004: ("Bush", "R", 1, "R"), 2006: ("Bush", "R", 2, "R"), 2008: ("Bush", "R", 2, "D"),
    2010: ("Obama", "D", 1, "D"), 2012: ("Obama", "D", 1, "R"), 2014: ("Obama", "D", 2, "R"),
    2016: ("Obama", "D", 2, "R"), 2018: ("Trump", "R", 1, "R"), 2020: ("Trump", "R", 1, "D"),
    2022: ("Biden", "D", 1, "D"), 2026: ("Trump", "R", 2, "R"),
}


def frame():
    r = BA.load()
    gen = BA.race_level(r, ["House-G-US"])[["cycle", "poll", "act", "err"]]
    rows = []
    for c, (pres, party, term, house) in CYCLE_INFO.items():
        e = gen.loc[gen.cycle == c, "err"]
        rows.append(dict(cycle=c, president=pres, pres_D=int(party == "D"), second_term=int(term == 2),
                         house_D=int(house == "D"), midterm=int(c % 4 == 2), err=float(e.iloc[0]) if len(e) else np.nan))
    return pd.DataFrame(rows)


def wls(X, y, w):
    W = np.diag(w)
    XtWX = X.T @ W @ X
    beta = np.linalg.solve(XtWX + 1e-9 * np.eye(X.shape[1]), X.T @ W @ y)
    resid = y - X @ beta
    dof = max(w.sum() ** 2 / (w ** 2).sum() - X.shape[1], 1.0)  # effective-n based
    s2 = float((w * resid ** 2).sum() / w.sum() * (w.sum() ** 2 / (w ** 2).sum()) / dof)
    cov = s2 * np.linalg.inv(XtWX / w.sum() * (w.sum() ** 2 / (w ** 2).sum()))
    return beta, cov, s2, resid


def fit_predict(df_tr, df_te, covs, H, M, pres_re):
    w = 0.5 ** ((2026 - df_tr.cycle) / H) * np.where(df_tr.midterm == 1, M, 1.0)
    X = np.column_stack([np.ones(len(df_tr))] + [df_tr[c] for c in covs])
    y = df_tr.err.values
    beta, cov, s2, resid = wls(X, y, w.values)
    xt = np.array([1.0] + [float(df_te[c]) for c in covs])
    pred = float(xt @ beta)
    var = float(xt @ cov @ xt) + s2
    if pres_re:
        # empirical-Bayes president effect: weighted mean residual for this president, shrunk by n_eff / (n_eff + k)
        pr = df_te["president"]
        mask = (df_tr.president == pr).values
        if mask.any():
            tau2 = max(np.var([resid[(df_tr.president == p).values].mean() for p in df_tr.president.unique()]) - s2 / 2, 0.25)
            wn = w.values[mask]
            n_eff = wn.sum() ** 2 / (wn ** 2).sum()
            shrink = tau2 / (tau2 + s2 / n_eff)
            pred += shrink * float(np.average(resid[mask], weights=wn))
    return pred, np.sqrt(var), beta


def main():
    df = frame()
    hist = df[df.cycle < 2026].reset_index(drop=True)
    target = df[df.cycle == 2026].iloc[0]
    cov_sets = [[], ["midterm"], ["pres_D"], ["house_D"], ["second_term"], ["pres_D", "midterm"], ["house_D", "pres_D"],
                ["pres_D", "second_term"], ["pres_D", "house_D", "second_term"]]
    results = []
    for H, M, covs, re in itertools.product([6, 10, 16, 1000], [1, 2, 3], cov_sets, [False, True]):
        if len(covs) + 1 + (1 if re else 0) > 4:
            continue
        # LOO: predict each held-out cycle from the others (same weighting scheme centred on 2026)
        errs, wts = [], []
        for i in range(len(hist)):
            tr, te = hist.drop(i), hist.iloc[i]
            p, _, _ = fit_predict(tr, te, covs, H, M, re)
            errs.append(te.err - p)
            wts.append(0.5 ** ((2026 - te.cycle) / H) * (M if te.midterm else 1))
        errs, wts = np.array(errs), np.array(wts)
        loo_rmse_w = float(np.sqrt(np.average(errs ** 2, weights=wts)))   # weighted toward recent midterms
        loo_rmse = float(np.sqrt(np.mean(errs ** 2)))
        loo_recent = float(np.sqrt(np.mean(errs[hist.cycle.values >= 2010] ** 2)))
        p26, sd26, beta = fit_predict(hist, target, covs, H, M, re)
        results.append(dict(half_life=H if H < 1000 else "none", midterm_mult=M, covariates="+".join(covs) or "(mean only)",
                            president_effect=re, pred_2026=p26, pred_sd=sd26, loo_rmse=loo_rmse, loo_rmse_weighted=loo_rmse_w,
                            loo_rmse_2010plus=loo_recent, coefs={k: float(b) for k, b in zip(["const"] + covs, beta)}))
    res = pd.DataFrame(results)
    pd.set_option("display.width", 220)
    print(hist[["cycle", "president", "pres_D", "second_term", "house_D", "midterm", "err"]].round(2).to_string(index=False))
    show = ["half_life", "midterm_mult", "covariates", "president_effect", "pred_2026", "pred_sd", "loo_rmse", "loo_rmse_weighted", "loo_rmse_2010plus"]
    print("\nBest 12 by weighted LOO RMSE:")
    print(res.sort_values("loo_rmse_weighted")[show].head(12).round(2).to_string(index=False))
    print("\nBaselines (mean only, no president effect):")
    print(res[(res.covariates == "(mean only)") & (~res.president_effect)][show].round(2).to_string(index=False))
    # Bayesian-model-average style summary: weight specs by exp(-0.5 * (loo_rmse_w / min)^2 * n_eff)? keep simple:
    top = res.sort_values("loo_rmse_weighted").head(10)
    wts = 1 / top.loo_rmse_weighted ** 2
    avg = float(np.average(top.pred_2026, weights=wts))
    spread = (float(top.pred_2026.min()), float(top.pred_2026.max()))
    print(f"\nTop-10 average 2026 prediction: {avg:+.2f} (range {spread[0]:+.2f} to {spread[1]:+.2f})")
    out = {"history": hist.to_dict("records"), "specs": res.to_dict("records"),
           "top10_avg_pred_2026": avg, "top10_range": spread,
           "flat_mean": float(hist.err.mean())}
    (ROOT / "data/processed/bias_decay.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
