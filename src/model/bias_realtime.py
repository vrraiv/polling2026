"""Real-time (out-of-sample) tests of the three candidate polling-bias corrections.

Each correction is estimated using only elections *before* the test year, then applied to that year's final poll
averages. A correction earns its place in the Bias-adjusted model only if it reduces real-time error.

  1. National level shift on the generic ballot  (final generic average vs national House vote, 1998-2022)
  2. Senate-wide level shift on Senate race polls (competitive races, |final poll avg| < 10, 2002-2022)
  3. State-lean term: within a year, results land further toward state partisanship than polls (Senate, 2002-2022;
     slope estimated from prior years since 2010, the post-realignment period; pre-2010 slopes were negative)

Writes data/processed/bias_realtime.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed"
COMP = 10.0     # "competitive": final poll average within 10 pts
HL = 8.0        # half-life (years) for the decay-weighted variant


def rms(x):
    x = np.asarray(x, float)
    return float(np.sqrt(np.mean(x ** 2)))


def generic_test():
    g = json.loads((OUT / "bias_analysis.json").read_text())["national"]["generic_by_cycle"]
    c = np.array([x["cycle"] for x in g]); e = np.array([x["err"] for x in g]); mt = np.array([x["midterm"] for x in g])
    rows = []
    for i in range(3, len(c)):
        w = 0.5 ** ((c[i] - c[:i]) / HL)
        rows.append({"cycle": int(c[i]), "midterm": int(mt[i]), "err": float(e[i]),
                     "est_mean": float(e[:i].mean()), "est_decay": float(np.average(e[:i], weights=w))})
    d = pd.DataFrame(rows)
    summ = {}
    for lab, sel in [("all", d.cycle > 0), ("midterms", d.midterm == 1)]:
        x = d[sel]
        summ[lab] = {"n": int(len(x)), "none": rms(x.err), "shift_mean": rms(x.err - x.est_mean), "shift_decay": rms(x.err - x.est_decay)}
    return {"cycles": rows, "summary": summ,
            "n_overstate_dems": int((e < 0).sum()), "n_cycles": int(len(e))}


def senate_level_test(r):
    s = r[(r.type_simple == "Sen-G") & (r.poll.abs() < COMP)]
    cm = s.groupby("cycle").err.mean()
    midterm = s.groupby("cycle").midterm.first()
    rows = []
    for c in cm.index:
        prior = cm[cm.index < c]
        if len(prior) < 3:
            continue
        w = 0.5 ** ((c - prior.index) / HL)
        est_m, est_d = float(prior.mean()), float(np.average(prior, weights=w))
        t = s[s.cycle == c]
        rows.append({"cycle": int(c), "midterm": int(midterm[c]), "n_races": int(len(t)), "err": float(cm[c]),
                     "est_mean": est_m, "est_decay": est_d,
                     "race_rmse_none": rms(t.err), "race_rmse_mean": rms(t.err - est_m), "race_rmse_decay": rms(t.err - est_d)})
    d = pd.DataFrame(rows)
    summ = {}
    for lab, sel in [("all", d.cycle > 0), ("midterms", d.midterm == 1)]:
        x = d[sel]
        summ[lab] = {"n": int(len(x)),
                     "cycle_none": rms(x.err), "cycle_shift_mean": rms(x.err - x.est_mean), "cycle_shift_decay": rms(x.err - x.est_decay),
                     "race_none": rms(x.race_rmse_none), "race_shift_mean": rms(x.race_rmse_mean), "race_shift_decay": rms(x.race_rmse_decay)}
    hist = {"mean_all": float(cm.mean()), "sd_all": float(cm.std()), "n_all": int(len(cm)),
            "mean_midterms": float(cm[midterm == 1].mean()), "sd_midterms": float(cm[midterm == 1].std()), "n_midterms": int((midterm == 1).sum()),
            "by_cycle": {int(k): float(v) for k, v in cm.items()}}
    return {"cycles": rows, "summary": summ, "history": hist}


def lean_test(r):
    s = r[r.type_simple == "Sen-G"].copy()
    s["e"] = s.err - s.groupby("cycle").err.transform("mean")
    s["l"] = s.lean - s.groupby("cycle").lean.transform("mean")
    per = s.groupby("cycle").apply(lambda g: float((g.e * g.l).sum() / (g.l ** 2).sum()), include_groups=False)
    midterm = s.groupby("cycle").midterm.first()
    rows = []
    for c in per.index:
        prior = per[(per.index < c) & (per.index >= 2010)]
        if len(prior) < 1:
            continue
        b = float(prior.mean())
        t = s[s.cycle == c]; tc = t[t.poll.abs() < COMP]
        rows.append({"cycle": int(c), "midterm": int(midterm[c]), "slope_used": b,
                     "rmse_all_none": rms(t.e), "rmse_all_lean": rms(t.e - b * t.l),
                     "rmse_comp_none": rms(tc.e), "rmse_comp_lean": rms(tc.e - b * tc.l), "n_comp": int(len(tc))})
    d = pd.DataFrame(rows)
    summ = {}
    for lab, sel in [("all", d.cycle > 0), ("midterms", d.midterm == 1)]:
        x = d[sel]
        summ[lab] = {"n": int(len(x)), "comp_none": rms(x.rmse_comp_none), "comp_lean": rms(x.rmse_comp_lean),
                     "all_none": rms(x.rmse_all_none), "all_lean": rms(x.rmse_all_lean),
                     "cycles_improved": int((x.rmse_comp_lean < x.rmse_comp_none).sum())}
    return {"cycles": rows, "summary": summ, "slope_by_cycle": {int(k): float(v) for k, v in per.items()}}


def main():
    r = pd.read_csv(OUT / "bias_race_level.csv")
    out = {"generic": generic_test(), "senate_level": senate_level_test(r), "lean": lean_test(r), "comp_threshold": COMP, "half_life": HL}
    (OUT / "bias_realtime.json").write_text(json.dumps(out, indent=1))
    g, sl, ln = out["generic"]["summary"], out["senate_level"]["summary"], out["lean"]["summary"]
    print(f"generic shift   RMS all {g['all']['none']:.2f} -> {g['all']['shift_mean']:.2f} | midterms {g['midterms']['none']:.2f} -> {g['midterms']['shift_mean']:.2f}")
    print(f"senate shift    cycle RMS all {sl['all']['cycle_none']:.2f} -> {sl['all']['cycle_shift_mean']:.2f} | midterms "
          f"{sl['midterms']['cycle_none']:.2f} -> {sl['midterms']['cycle_shift_mean']:.2f}; race RMSE midterms {sl['midterms']['race_none']:.2f} -> {sl['midterms']['race_shift_mean']:.2f}")
    print(f"lean term       comp RMSE all {ln['all']['comp_none']:.2f} -> {ln['all']['comp_lean']:.2f} | midterms "
          f"{ln['midterms']['comp_none']:.2f} -> {ln['midterms']['comp_lean']:.2f} ({ln['all']['cycles_improved']}/{ln['all']['n']} cycles improved)")


if __name__ == "__main__":
    main()
