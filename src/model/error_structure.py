"""Correlated-error structure beyond the national factor, estimated from 1998-2022 Senate + governor poll misses.

Input: data/processed/bias_race_level.csv (from bias_analysis.py): one row per race, two-party miss `err`,
       within-cycle residual `resid` (cycle mean removed), prior-presidential state lean `lean` (margin units).

Components (all in two-party margin points):
  regional  : shared shock for the 4 Census regions in a given cycle. Method of moments:
              var(region-cycle cell means) - mean(within-cell variance / n_cell)
  lean slope: each cycle draws its own slope b_c on state lean (a polarisation/compression miss).
              sd(b) = sqrt(var(per-cycle slopes) - mean(sampling variance of the slopes))
  idiosyncratic: the rest. The forecast keeps each race's TOTAL variance unchanged and carves these
              components out of it, so marginal win probabilities are unaffected; only joint outcomes change.
Writes data/processed/error_structure.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT  # noqa: E402

REGION = {  # U.S. Census regions
    "Northeast": ["CT", "ME", "MA", "NH", "RI", "VT", "NJ", "NY", "PA"],
    "Midwest": ["IL", "IN", "MI", "OH", "WI", "IA", "KS", "MN", "MO", "NE", "ND", "SD"],
    "South": ["DE", "FL", "GA", "MD", "NC", "SC", "VA", "DC", "WV", "AL", "KY", "MS", "TN", "AR", "LA", "OK", "TX"],
    "West": ["AZ", "CO", "ID", "MT", "NV", "NM", "UT", "WY", "AK", "CA", "HI", "OR", "WA"],
}
STATE_REGION = {s: r for r, ss in REGION.items() for s in ss}


def estimate(df):
    df = df.copy()
    df["region"] = df.location.map(STATE_REGION)
    df = df.dropna(subset=["region"])
    # --- regional variance (method of moments on region x cycle cells, residuals already net of cycle mean)
    cells = df.groupby(["cycle", "region"]).resid.agg(["mean", "var", "size"]).reset_index()
    cells = cells[cells["size"] >= 3]
    noise = (cells["var"] / cells["size"]).mean()
    var_cell_means = np.average((cells["mean"] - 0) ** 2, weights=cells["size"])
    sigma_region = float(np.sqrt(max(var_cell_means - noise, 0)))
    # --- random lean slope across cycles (post-2010 regime and full period)
    out_slopes = {}
    for label, sub in [("all", df), ("post2010", df[df.cycle >= 2010])]:
        sl, se2 = [], []
        for c, g in sub.groupby("cycle"):
            m = smf.ols("resid ~ lean", g).fit()
            sl.append(m.params["lean"]); se2.append(m.bse["lean"] ** 2)
        sl, se2 = np.array(sl), np.array(se2)
        out_slopes[label] = {"mean": float(sl.mean()), "sd_raw": float(sl.std(ddof=1)),
                             "sd_true": float(np.sqrt(max(sl.var(ddof=1) - se2.mean(), 0))), "n_cycles": int(len(sl))}
    total = float(df.resid.std())
    return {"sigma_region": sigma_region, "region_cells": int(len(cells)), "cell_noise_var": float(noise),
            "var_cell_means": float(var_cell_means), "lean_slope": out_slopes, "resid_sd_total": total,
            "regions": REGION}


if __name__ == "__main__":
    df = pd.read_csv(ROOT / "data/processed/bias_race_level.csv")
    est = estimate(df)
    sb = est["lean_slope"]["all"]["sd_true"]
    print(f"regional SD {est['sigma_region']:.2f} (cells {est['region_cells']}, cell-mean var {est['var_cell_means']:.2f}, noise {est['cell_noise_var']:.2f})")
    print("lean slope:", {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in est["lean_slope"].items()})
    print(f"total within-cycle race SD {est['resid_sd_total']:.2f}")
    for lean in (0, 10, 20, 30):
        print(f"  lean {lean:>2}: regional var {est['sigma_region']**2:.1f} + lean-slope var {(sb*lean)**2:.1f} of total {est['resid_sd_total']**2:.1f}")
    (ROOT / "data/processed/error_structure.json").write_text(json.dumps(est, indent=1))
