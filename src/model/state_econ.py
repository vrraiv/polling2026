"""Estimate the state-economy effect used in the Senate prior (replaces the assumed 0.5 coefficient).

Question: when a state's unemployment rose more than the nation's over the prior 12 months, does the
president's party do worse there than the state's partisanship and the national environment imply?

Data: 1998-2022 Senate + governor races with final polls (data/processed/bias_race_level.csv), state and national
unemployment from FRED (<ST>UR, UNRATE; monthly, from 1976).
  x = sign * (state 12-month change in unemployment - national change), measured in September,
      with sign = +1 under a Republican president, -1 under a Democrat (positive x = bad local trend for the
      president's party, i.e. good for Democrats when the president is a Republican). Same orientation as the forecast.
Two targets (two-party D-R margins):
  structural residual = result - prior-presidential state lean - national House margin   (what the Senate prior uses)
  poll miss           = result - final poll average                                       (whether polls already capture it)
Both are demeaned by cycle (absorbs national swings). OLS with cycle-clustered SEs; leave-one-cycle-out test of
whether adding b*x reduces out-of-sample error. Writes data/processed/state_econ.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT  # noqa: E402

PRES = {1998: "D", 2000: "D", 2002: "R", 2004: "R", 2006: "R", 2008: "R", 2010: "D", 2012: "D", 2014: "D",
        2016: "D", 2018: "R", 2020: "R", 2022: "D"}


def series(path):
    d = pd.read_csv(path)
    d.columns = ["date", "v"]
    d["date"] = pd.to_datetime(d.date)
    d["v"] = pd.to_numeric(d.v, errors="coerce")
    return d.dropna().set_index("date").v


def chg(s, y):
    a, b = s.get(pd.Timestamp(year=y, month=9, day=1)), s.get(pd.Timestamp(year=y - 1, month=9, day=1))
    return np.nan if a is None or b is None else float(a - b)


def main():
    races = pd.read_csv(ROOT / "data/processed/bias_race_level.csv")
    vote = pd.read_csv(ROOT / "data/interim/house_national_vote.csv").set_index("year").two_party_margin_D
    nat = series(sorted((ROOT / "data/raw/fred").glob("*/UNRATE.csv"))[-1])
    st_series = {}
    for f in sorted((ROOT / "data/raw/fred_state").glob("*/??UR.csv")):
        st_series[f.stem[:2]] = series(f)
    rows = []
    for _, r in races.iterrows():
        s = st_series.get(r.location)
        if s is None:
            continue
        sign = 1 if PRES[r.cycle] == "R" else -1
        diff = chg(s, r.cycle) - chg(nat, r.cycle)
        rows.append(dict(cycle=r.cycle, state=r.location, type=r.type_simple, x=sign * diff, raw_diff=diff,
                         struct=r.act - r.lean - vote.get(r.cycle, np.nan), miss=r.act - r.poll))
    df = pd.DataFrame(rows).dropna()
    for c in ["struct", "miss", "x"]:
        df[c + "_d"] = df[c] - df.groupby("cycle")[c].transform("mean")
    out = {"n_races": int(len(df)), "cycles": sorted(df.cycle.unique().tolist()), "x_sd": float(df.x.std())}
    for target in ["struct", "miss"]:
        m = smf.ols(f"{target}_d ~ x_d - 1", df).fit(cov_type="cluster", cov_kwds={"groups": df.cycle})
        # leave-one-cycle-out: predict held-out cycle's demeaned target with and without b*x
        e0, e1 = [], []
        for c in df.cycle.unique():
            tr, te = df[df.cycle != c], df[df.cycle == c]
            b = smf.ols(f"{target}_d ~ x_d - 1", tr).fit().params["x_d"]
            e0 += list(te[f"{target}_d"]); e1 += list(te[f"{target}_d"] - b * te.x_d)
        r0, r1 = float(np.sqrt(np.mean(np.square(e0)))), float(np.sqrt(np.mean(np.square(e1))))
        by_type = {}
        for t, g in df.groupby("type"):
            mt = smf.ols(f"{target}_d ~ x_d - 1", g).fit(cov_type="cluster", cov_kwds={"groups": g.cycle})
            by_type[t] = {"coef": float(mt.params["x_d"]), "se": float(mt.bse["x_d"]), "n": int(len(g))}
        out[target] = {"coef": float(m.params["x_d"]), "se_cluster": float(m.bse["x_d"]), "p": float(m.pvalues["x_d"]),
                       "loco_rmse_without": r0, "loco_rmse_with": r1, "by_type": by_type}
        print(f"[{target}] coef {m.params['x_d']:+.2f} (cluster SE {m.bse['x_d']:.2f}, p={m.pvalues['x_d']:.2f}); "
              f"LOCO RMSE {r0:.3f} -> {r1:.3f}; by type " + ", ".join(f"{k} {v['coef']:+.2f}±{v['se']:.2f} (n={v['n']})" for k, v in by_type.items()))
    s = out["struct"]
    use = s["loco_rmse_with"] < s["loco_rmse_without"] and s["p"] < 0.2
    out["coef_used"] = s["coef"] if use else 0.0
    out["decision"] = ("estimated coefficient used: improves held-out error" if use else
                       "set to 0: the estimate does not improve held-out error / is not distinguishable from zero")
    print(f"n={len(df)} races, sd(x)={df.x.std():.2f} pts. Decision: {out['decision']} -> coefficient {out['coef_used']:+.2f}")
    (ROOT / "data/processed/state_econ.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
