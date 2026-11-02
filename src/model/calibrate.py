"""Polling-error calibration from 538 raw_polls.csv (final 21 days, poll vs. actual result).

For each race: average the polls (D-R margin), compare with the actual D-R margin.
Split error into a per-cycle shared (national) component and a race-specific residual.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT, latest

def load():
    """Final-21-day polls vs results, oriented to TWO-PARTY D-R margins (same basis as the forecast)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bias_analysis as BA
    r = BA.load()   # even-year D-vs-R polls with poll2 / act2 two-party margins
    r = r[r.type_simple.isin(["Sen-G", "House-G-US", "House-G", "Gov-G"])].copy()
    r["poll_m"], r["act_m"] = r.poll2, r.act2
    return r


def summarize(r, kind):
    s = r[r.type_simple == kind]
    races = s.groupby(["cycle", "race_id"]).agg(poll=("poll_m", "mean"), act=("act_m", "first"), n=("poll_m", "size")).reset_index()
    races["err"] = races.act - races.poll  # positive = Dems beat their polls
    cyc = races.groupby("cycle").err.agg(["mean", "std", "size"]).reset_index()
    races = races.merge(cyc[["cycle", "mean"]], on="cycle")
    races["resid"] = races.err - races["mean"]
    out = {"kind": kind, "n_races": int(len(races)), "cycles": cyc.round(2).to_dict("records"),
           "national_sd": float(cyc["mean"].std()), "race_resid_sd": float(races.resid.std()),
           "race_resid_sd_midterms": float(races[races.cycle % 4 == 2].resid.std()),
           "national_sd_midterms": float(cyc[cyc.cycle % 4 == 2]["mean"].std())}
    return out

if __name__ == "__main__":
    r = load()
    res = {k: summarize(r, k) for k in ["Sen-G", "House-G-US", "House-G", "Gov-G"]}
    for k, v in res.items():
        print(k, "races", v["n_races"], "national sd %.2f (midterms %.2f)" % (v["national_sd"], v["national_sd_midterms"]),
              "race resid sd %.2f (midterms %.2f)" % (v["race_resid_sd"], v["race_resid_sd_midterms"]))
        print("   per-cycle mean err:", [(c["cycle"], c["mean"]) for c in v["cycles"]])
    (ROOT / "data/processed/calibration.json").write_text(json.dumps(res, indent=1))
