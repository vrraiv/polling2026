"""Does fundraising predict Senate polling error? (candidate-quality test)

Question: after the corrections the model already makes (a cycle-wide level and the state-lean term), does a
candidate's fundraising record predict how far the result lands from the final poll average?  The poll average carries
~0.9 of the weight in polled races, so a money signal only matters for the forecast if it predicts *poll error*.

Money: individual contributions through the pre-general report (src/collect/fec_money.py), so nothing raised after
mid-October is used.

Features (all known before the election; residualizing uses the test cycle's own money/lean, never results):
  F1 money ratio     log(D individual $ / R individual $)
  F2 money vs race   F1 minus what the race "should" raise: within-cycle residual of F1 on state lean and incumbency
                     ("better than this race normally does")
  F3 national share  D nominee's share of all D-nominee money that cycle minus the R equivalent, residualized the same way
  INC                incumbency (+1 D incumbent, -1 R incumbent), to check money isn't just standing in for it

Target: e = (result - final poll avg) - cycle mean.  Every model includes the lean term (what the model already does).
Real-time protocol: coefficients fit on prior cycles only, applied to the test cycle (test cycles 2008-2022).
Leave-one-cycle-out reported as a robustness check.

Decision rule (fixed before running): a feature is adopted only if real-time RMSE on competitive races (|poll| < 10)
improves overall AND in a majority of test cycles AND the coefficient keeps one sign across all folds.

Writes data/processed/money_test.json
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "processed"
COMP = 10.0
FLOOR = 25_000.0         # $ floor so token campaigns don't produce infinite log ratios
FIRST_TEST = 2008


def rms(x):
    x = np.asarray(x, float)
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else float("nan")


def inc_code(d_inc, r_inc):
    return np.where(d_inc == "I", 1.0, np.where(r_inc == "I", -1.0, 0.0))


def residualize(df, col):
    """Within each cycle: residual of col on lean and incumbency (no outcome data used)."""
    out = pd.Series(np.nan, index=df.index)
    for c, g in df.groupby("cycle"):
        X = np.column_stack([np.ones(len(g)), g.lean, g.inc])
        b, *_ = np.linalg.lstsq(X, g[col].values, rcond=None)
        out[g.index] = g[col].values - X @ b
    return out


def features(m):
    m = m.copy()
    m["d_m"] = np.maximum(m.d_indiv.fillna(0), FLOOR)
    m["r_m"] = np.maximum(m.r_indiv.fillna(0), FLOOR)
    m["F1"] = np.log(m.d_m / m.r_m)
    m["inc"] = inc_code(m.d_inc, m.r_inc)
    m["F2"] = residualize(m, "F1")
    tot_d = m.groupby("cycle").d_m.transform("sum")
    tot_r = m.groupby("cycle").r_m.transform("sum")
    m["F3raw"] = 100 * (m.d_m / tot_d - m.r_m / tot_r)
    m["F3"] = residualize(m, "F3raw")
    return m


def load():
    r = pd.read_csv(OUT / "bias_race_level.csv")
    r = r[r.type_simple == "Sen-G"]
    f = pd.read_csv(ROOT / "data/interim/fec_money_hist.csv")
    m = r.merge(f[["race_id", "d_name", "r_name", "d_fec", "r_fec", "d_inc", "r_inc", "d_indiv", "r_indiv",
                   "d_has_12g", "r_has_12g"]], on="race_id", how="inner")
    m = m.dropna(subset=["d_fec", "r_fec"])
    m = m[(m.d_indiv.fillna(0) > 0) | (m.r_indiv.fillna(0) > 0)]
    # late replacement nominees (no pre-general money under their own committee): Mondale MN-2002, Lautenberg NJ-2002
    m = m[~((m.cycle == 2002) & m.location.isin(["MN", "NJ"]))]
    m["e"] = m.err - m.groupby("cycle").err.transform("mean")
    m["lean_c"] = m.lean - m.groupby("cycle").lean.transform("mean")
    return features(m)


def fit(tr, cols):
    X = np.column_stack([tr[c] for c in cols])
    b, *_ = np.linalg.lstsq(X, tr.e.values, rcond=None)
    return b


def predict(te, cols, b):
    return np.column_stack([te[c] for c in cols]) @ b


MODELS = {"lean only (current)": ["lean_c"], "+ F1 money ratio": ["lean_c", "F1"],
          "+ F2 money vs race": ["lean_c", "F2"], "+ F3 national share": ["lean_c", "F3"],
          "+ INC incumbency": ["lean_c", "inc"], "+ F1 + INC": ["lean_c", "F1", "inc"]}


def realtime(m, loco=False):
    rows = []
    cycles = sorted(m.cycle.unique())
    for c in cycles:
        if c < FIRST_TEST:
            continue
        tr = m[m.cycle != c] if loco else m[m.cycle < c]
        te = m[m.cycle == c]
        tc = te.poll.abs() < COMP
        row = {"cycle": int(c), "n": int(len(te)), "n_comp": int(tc.sum())}
        for name, cols in MODELS.items():
            b = fit(tr, cols)
            res = te.e.values - predict(te, cols, b)
            row[name] = {"rmse_comp": rms(res[tc.values]), "rmse_all": rms(res), "coef": [float(x) for x in b]}
        rows.append(row)
    summ = {}
    base = "lean only (current)"
    for name in MODELS:
        comp = rms(np.concatenate([[r[name]["rmse_comp"]] for r in rows]))
        allr = rms(np.concatenate([[r[name]["rmse_all"]] for r in rows]))
        better = sum(r[name]["rmse_comp"] < r[base]["rmse_comp"] - 1e-9 for r in rows)
        k = len(MODELS[name]) - 1  # the added feature's coefficient (last col)
        signs = {np.sign(r[name]["coef"][k]) for r in rows}
        summ[name] = {"rmse_comp": comp, "rmse_all": allr, "cycles_improved": int(better), "n_cycles": len(rows),
                      "coef_sign_stable": len(signs) == 1, "coef_by_cycle": [r[name]["coef"][k] for r in rows]}
    return rows, summ


def full_sample(m):
    """Full-sample OLS with SEs: is there any signal at all, before worrying about out-of-sample?"""
    out = {}
    for name, cols in MODELS.items():
        X = np.column_stack([m[c] for c in cols])
        b, *_ = np.linalg.lstsq(X, m.e.values, rcond=None)
        res = m.e.values - X @ b
        s2 = res @ res / (len(m) - len(cols))
        se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
        out[name] = {"coef": dict(zip(cols, map(float, b))), "se": dict(zip(cols, map(float, se)))}
    return out


def y2026(m):
    """Illustration only: what the full-sample F-models would shift each 2026 race's poll average by."""
    f = pd.read_csv(ROOT / "data/interim/fec_money_2026.csv")
    s = pd.read_csv(OUT / "senate_polls_fundamentals_biasadj.csv")
    f = f.merge(s[["race_key", "pvi", "poll_avg", "n_polls", "p_dside"]], on="race_key")
    f["lean"] = 2 * f.pvi
    f["cycle"] = 2026
    f = features(f.assign(d_indiv=f.d_indiv, r_indiv=f.r_indiv))
    fs = full_sample(m)
    rows = []
    for _, r in f.iterrows():
        row = {"state": r.state, "d": r.d_name, "r": r.r_name, "d_indiv_m": round(r.d_m / 1e6, 1),
               "r_indiv_m": round(r.r_m / 1e6, 1), "F1": round(r.F1, 2), "F2": round(r.F2, 2), "F3": round(r.F3, 2),
               "poll_avg": r.poll_avg, "n_polls": int(r.n_polls), "p_dside": r.p_dside}
        for k in ["F1", "F2", "F3"]:
            name = {"F1": "+ F1 money ratio", "F2": "+ F2 money vs race", "F3": "+ F3 national share"}[k]
            row[f"shift_{k}"] = round(fs[name]["coef"][k] * r[k], 2)
        rows.append(row)
    return rows


def main():
    m = load()
    rt_rows, rt = realtime(m)
    lo_rows, lo = realtime(m, loco=True)
    fs = full_sample(m)
    base = rt["lean only (current)"]
    verdict = {}
    for name in ["+ F1 money ratio", "+ F2 money vs race", "+ F3 national share"]:
        x = rt[name]
        verdict[name] = bool(x["rmse_comp"] < base["rmse_comp"] and x["cycles_improved"] > x["n_cycles"] / 2
                             and x["coef_sign_stable"])
    cov = m.groupby("cycle").size().to_dict()
    out = {"n_races": int(len(m)), "races_by_cycle": {int(k): int(v) for k, v in cov.items()},
           "realtime": {"cycles": rt_rows, "summary": rt}, "loco": {"cycles": lo_rows, "summary": lo},
           "full_sample": fs, "verdict": verdict, "y2026": y2026(m), "comp_threshold": COMP, "floor": FLOOR}
    (OUT / "money_test.json").write_text(json.dumps(out, indent=1, default=float))
    print(f"races {len(m)}  by cycle {cov}")
    print("\nfull-sample coefficients (SE):")
    for name, v in fs.items():
        print(f"  {name:22s} " + "  ".join(f"{k}={v['coef'][k]:+.3f} ({v['se'][k]:.3f})" for k in v["coef"]))
    print("\nreal-time (prior cycles only)          comp RMSE   all RMSE   cycles better   sign stable")
    for name, x in rt.items():
        print(f"  {name:36s} {x['rmse_comp']:.3f}     {x['rmse_all']:.3f}      {x['cycles_improved']}/{x['n_cycles']}"
              f"            {x['coef_sign_stable']}")
    print("\nleave-one-cycle-out                    comp RMSE   all RMSE   cycles better")
    for name, x in lo.items():
        print(f"  {name:36s} {x['rmse_comp']:.3f}     {x['rmse_all']:.3f}      {x['cycles_improved']}/{x['n_cycles']}")
    print("\nverdict:", verdict)


if __name__ == "__main__":
    main()
