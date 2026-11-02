"""How much should late Senate polls be pulled toward a partisanship prior?  (tests the assumed prior SD of 10)

Data: 1998-2022 Senate races with polls in the final 21 days (538 raw_polls via bias_analysis), two-party margins.
  poll  = average of final-21-day polls
  prior = prior-presidential state lean (margin vs nation) + national environment, where the environment is the
          final generic-ballot poll average that cycle (known before the election), as in the 2026 model.
          (No incumbency term: raw_polls doesn't record it; the 2026 prior adds +/-2.)
Estimate w in  result - prior = w * (poll - prior) + cycle effect + e   (within-cycle, so national misses are excluded,
matching how the forecast treats them separately). w = 1 means "trust the polls fully".
Also: residual SDs of each predictor, w by number of polls, leave-one-cycle-out error for several fixed weights,
and the implied prior SD given the poll-average error used in the forecast.
Writes data/processed/prior_weight.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT  # noqa: E402
import bias_analysis as BA  # noqa: E402


def main():
    r = BA.load()
    gen = BA.race_level(r, ["House-G-US"]).set_index("cycle").poll        # final generic-ballot average per cycle
    races = pd.read_csv(ROOT / "data/processed/bias_race_level.csv")
    races = races[races.type_simple == "Sen-G"].copy()
    races["env"] = races.cycle.map(gen)
    races = races.dropna(subset=["env", "lean"])
    races["prior"] = races.lean + races.env
    races["y"] = races.act - races.prior
    races["x"] = races.poll - races.prior
    for c in ["y", "x", "act", "poll", "prior"]:
        races[c + "_d"] = races[c] - races.groupby("cycle")[c].transform("mean")
    m = smf.ols("y_d ~ x_d - 1", races).fit(cov_type="cluster", cov_kwds={"groups": races.cycle})
    w = float(m.params["x_d"])
    sd_poll = float((races.act_d - races.poll_d).std())
    sd_prior = float((races.act_d - races.prior_d).std())
    rho = float(np.corrcoef(races.act_d - races.poll_d, races.act_d - races.prior_d)[0, 1])
    out = {"n_races": int(len(races)), "w": w, "w_se": float(m.bse["x_d"]), "sd_poll_resid": sd_poll, "sd_prior_resid": sd_prior,
           "error_corr": rho}
    # by number of polls
    out["w_by_npolls"] = {}
    for lab, g in [("1-2 polls", races[races.n <= 2]), ("3-5 polls", races[(races.n >= 3) & (races.n <= 5)]), ("6+ polls", races[races.n >= 6])]:
        mm = smf.ols("y_d ~ x_d - 1", g).fit(cov_type="cluster", cov_kwds={"groups": g.cycle})
        out["w_by_npolls"][lab] = {"w": float(mm.params["x_d"]), "se": float(mm.bse["x_d"]), "n": int(len(g))}
    # recent era
    rec = races[races.cycle >= 2010]
    mr = smf.ols("y_d ~ x_d - 1", rec).fit(cov_type="cluster", cov_kwds={"groups": rec.cycle})
    out["w_2010plus"] = {"w": float(mr.params["x_d"]), "se": float(mr.bse["x_d"]), "n": int(len(rec))}
    # leave-one-cycle-out: fixed weights and the estimated one
    grid = [0.5, 0.64, 0.75, 0.85, 0.9, 1.0]
    loco = {str(g): [] for g in grid}; loco["estimated"] = []
    for c in races.cycle.unique():
        tr, te = races[races.cycle != c], races[races.cycle == c]
        wc = smf.ols("y_d ~ x_d - 1", tr).fit().params["x_d"]
        for g in grid:
            loco[str(g)] += list(te.y_d - g * te.x_d)
        loco["estimated"] += list(te.y_d - wc * te.x_d)
    out["loco_rmse"] = {k: float(np.sqrt(np.mean(np.square(v)))) for k, v in loco.items()}
    # winner accuracy at each weight (within-cycle demeaned isn't meaningful for winners; use raw with national result)
    out["winner_acc"] = {str(g): float(((g * races.poll + (1 - g) * races.prior > 0) == (races.act > 0)).mean()) for g in grid}
    # implied prior SD for the forecast's precision weighting, given the forecast's poll-average SD
    cal = json.loads((ROOT / "data/processed/calibration.json").read_text())
    sd_pollavg = cal["Sen-G"]["race_resid_sd_midterms"]
    wc = min(max(w, 0.01), 0.99)
    out["forecast_poll_sd"] = sd_pollavg
    e_prior = races.act_d - races.prior_d
    out["prior_sd_robust"] = float(1.4826 * np.median(np.abs(e_prior - np.median(e_prior))))
    big = races[races.prior.abs() > 15]
    out["upsets_prior_gt15"] = {"n": int(len(big)), "upsets": int(((big.prior > 0) != (big.act > 0)).sum())}
    out["implied_prior_sd"] = float(sd_pollavg * np.sqrt(wc / (1 - wc)))
    # Alaska-like cases: polls disagree with prior by 3-8 pts
    dis = races[(races.x.abs() >= 3) & (races.x.abs() <= 8)]
    md = smf.ols("y_d ~ x_d - 1", dis).fit(cov_type="cluster", cov_kwds={"groups": dis.cycle})
    out["w_moderate_disagreement"] = {"w": float(md.params["x_d"]), "se": float(md.bse["x_d"]), "n": int(len(dis))}
    print(f"n={len(races)} Senate races 1998-2022")
    print(f"estimated weight on polls w = {w:.2f} (cluster SE {m.bse['x_d']:.2f}); 2010+: {out['w_2010plus']['w']:.2f} ± {out['w_2010plus']['se']:.2f}")
    print(f"residual SD: poll avg {sd_poll:.2f}, prior {sd_prior:.2f}, error corr {rho:.2f}")
    print("w by number of polls:", {k: (round(v['w'], 2), round(v['se'], 2), v['n']) for k, v in out["w_by_npolls"].items()})
    print("w when polls and prior disagree by 3-8 pts:", {k: round(v, 2) if isinstance(v, float) else v for k, v in out["w_moderate_disagreement"].items()})
    print("LOCO RMSE by weight:", {k: round(v, 3) for k, v in out["loco_rmse"].items()})
    print("winner accuracy by weight:", out["winner_acc"])
    print(f"robust prior SD (MAD) {out['prior_sd_robust']:.2f}; upsets where |prior|>15: {out['upsets_prior_gt15']}")
    print(f"implied prior SD for the forecast (poll SD {sd_pollavg:.1f}): {out['implied_prior_sd']:.1f}  (currently assumed 10)")
    (ROOT / "data/processed/prior_weight.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
