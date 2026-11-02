"""Build the static forecast site into site/ (served by a Cloudflare Worker with static assets, no container).

  python src/site/build.py

Reads data/processed/* and data/interim/*, writes:
  site/index.html          self-contained page (data inlined as JSON, charts drawn client-side in SVG)
  site/data/*.csv|json     downloadable model outputs
"""
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
SITE = ROOT / "site"
TEMPLATE = Path(__file__).with_name("template.html")


def clean(v):
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def records(df, cols):
    return [{c: clean(r[c]) for c in cols} for _, r in df[cols].iterrows()]


def main():
    models = {}
    for key in ["polls_only", "polls_fundamentals", "polls_fundamentals_biasadj", "scenario_polls_overstate_dems"]:
        s = json.loads((PROC / f"summary_{key}.json").read_text())
        sen = pd.read_csv(PROC / f"senate_{key}.csv")
        house = pd.read_csv(PROC / f"house_{key}.csv")
        house["label"] = house.state + "-" + house.district.astype(int).astype(str)
        house["inc"] = house.incumbent.fillna("").str.split(" Redistricted").str[0]
        comp = house[(house.p_dem > 0.05) & (house.p_dem < 0.95)].sort_values("p_dem", ascending=False)
        models[key] = {
            "house": {k: v for k, v in s["house"].items()},
            "senate": {k: v for k, v in s["senate"].items()},
            "G": s["national"]["G_used"], "shift": s["national"].get("bias_shift", 0.0),
            "sd_nat_house": s["national"].get("sd_nat_house_used", 0.0), "sd_nat_senate": s["national"].get("sd_nat_senate_used", 0.0),
            "w_polls": s["national"].get("w_polls_national", 1.0), "race_w": s["national"].get("race_poll_weight_mean_polled", 0.0),
            "senate_races": records(sen.sort_values("p_dside", ascending=False),
                                    ["race_key", "state", "special", "dem", "rep", "dside", "inc_party", "pvi", "prior",
                                     "poll_avg", "n_polls", "poll_weight", "mu", "sd_race", "p_dside", "rating_cook", "rating_silver"]),
            "house_comp": records(comp, ["label", "inc", "inc_party", "pvi", "inc_running", "poll_avg", "mu", "p_dem",
                                         "dem_cand", "rep_cand"]),
            "house_counts": {
                "fixed_d": int((house.fixed == "D").sum()), "fixed_r": int((house.fixed == "R").sum()),
                "safe_d": int(((house.p_dem >= 0.95) & house.fixed.isna()).sum()),
                "safe_r": int(((house.p_dem <= 0.05) & house.fixed.isna()).sum()),
                "competitive": int(len(comp)),
            },
        }
    nat = json.loads((PROC / "national_inputs.json").read_text())
    bt = json.loads((PROC / "backtest_summary.json").read_text())
    btr = pd.read_csv(PROC / "backtest_senate_2018_2022.csv")
    btr["bin"] = pd.cut(btr.p_dem, [0, .1, .3, .5, .7, .9, 1.0001], labels=["0–10%", "10–30%", "30–50%", "50–70%", "70–90%", "90–100%"])
    calib = btr.groupby("bin", observed=True).agg(n=("dem_won", "size"), p=("p_dem", "mean"), won=("dem_won", "mean")).reset_index()
    sens = json.loads((PROC / "sensitivity.json").read_text()) if (PROC / "sensitivity.json").exists() else None
    bd = json.loads((PROC / "bias_decay.json").read_text())
    bdf = pd.DataFrame(bd["specs"])
    bias = {"history": bd["history"], "flat_mean": bd["flat_mean"], "decay_estimate": bd["top10_avg_pred_2026"],
            "decay_range": bd["top10_range"],
            "specs": bdf.sort_values("loo_rmse_weighted").head(12)[["half_life", "midterm_mult", "covariates", "president_effect", "pred_2026", "pred_sd", "loo_rmse_weighted"]].to_dict("records"),
            "covariate_specs": bdf[(bdf.half_life.astype(str) == "10") & (bdf.midterm_mult == 2) & (~bdf.president_effect)][["covariates", "pred_2026", "pred_sd", "loo_rmse_weighted"]].to_dict("records")}
    bstate = json.loads((PROC / "bias_analysis.json").read_text())["state"]
    bias["state"] = {"post2010": bstate["post2010_symmetric"], "post2010_asym": bstate["post2010_asymmetric"],
                     "realtime_rmse": bstate["realtime_rmse_within"], "realtime_winner": bstate["realtime_winner"],
                     "slope_by_cycle": bstate["slope_by_cycle"]}
    cal = json.loads((PROC / "calibration.json").read_text())
    h_int = pd.read_csv(ROOT / "data/interim/house_2026_races.csv")
    sys.path.insert(0, str(ROOT / "src" / "model")); sys.path.insert(0, str(ROOT / "src" / "collect"))
    import pollavg as P
    from forecast import senate_races
    vh = P.load_votehub()
    poll_lists = P.senate_poll_list(vh, senate_races(vh))
    data = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "models": models,
        "national": nat,
        "backtest": bt,
        "calibration_bins": [{"bin": str(r.bin), "n": int(r.n), "p": float(r.p), "won": float(r.won)} for _, r in calib.iterrows()],
        "sensitivity": sens,
        "bias": bias,
        "senate_polls": poll_lists,
        "fund": json.loads((PROC / "fundamentals.json").read_text()),
        "state_econ": json.loads((PROC / "state_econ.json").read_text()),
        "prior_weight": json.loads((PROC / "prior_weight.json").read_text()),
        "house_structure": json.loads((PROC / "house_structure.json").read_text()),
        "poll_settings": json.loads((PROC / "poll_settings.json").read_text()),
        "errors": {"structure": json.loads((PROC / "error_structure.json").read_text()),
                   "sensitivity": json.loads((PROC / "error_sensitivity.json").read_text())},
        "error_model": {"sen_cycles": cal["Sen-G"]["cycles"], "gen_cycles": cal["House-G-US"]["cycles"]},
        "inputs": {
            "house_districts": int(len(h_int)), "house_open": int((~h_int.status.fillna("").str.contains("renominated|advanced|re-elected|running", case=False)).sum()),
            "votehub_polls": len(json.loads(sorted((ROOT / "data/raw/votehub").glob("*/polls.json"))[-1].read_text(encoding="utf-8"))),
        },
    }
    SITE.mkdir(exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)
    for f in list(PROC.glob("*.csv")) + list(PROC.glob("*.json")):
        if "_sens" not in f.name:
            shutil.copy(f, SITE / "data" / f.name)
    shutil.copy(ROOT / "data/interim/house_2026_races.csv", SITE / "data" / "house_2026_races.csv")
    shutil.copy(ROOT / "data/interim/senate_2026_races.csv", SITE / "data" / "senate_2026_races.csv")
    shutil.copy(ROOT / "data/interim/fundamentals_dataset.csv", SITE / "data" / "fundamentals_dataset.csv")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", json.dumps(data, default=clean).replace("</", "<\\/"))
    (SITE / "index.html").write_text(html, encoding="utf-8")
    shutil.copy(Path(__file__).with_name("favicon.svg"), SITE / "favicon.svg")
    og = Path(__file__).with_name("og.png")
    if og.exists():
        shutil.copy(og, SITE / "og.png")
    (SITE / "404.html").write_text('<!doctype html><meta charset="utf-8"><title>Not found</title>'
                                   '<p style="font-family:system-ui;padding:2rem">Not found. <a href="/">Back to the forecast</a></p>',
                                   encoding="utf-8")
    print("built", SITE / "index.html", f"{(SITE / 'index.html').stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
