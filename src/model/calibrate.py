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
    r = pd.read_csv(latest("538_github", "raw_polls.csv"), low_memory=False)
    r = r[r.type_simple.isin(["Sen-G", "House-G-US", "House-G", "Gov-G"])].copy()
    # orient to D-R; keep only D-vs-R matchups
    def orient(row):
        p1, p2 = row.cand1_party, row.cand2_party
        if p1 == "DEM" and p2 == "REP":
            return row.cand1_pct - row.cand2_pct, row.cand1_actual - row.cand2_actual
        if p1 == "REP" and p2 == "DEM":
            return row.cand2_pct - row.cand1_pct, row.cand2_actual - row.cand1_actual
        return np.nan, np.nan
    o = r.apply(orient, axis=1, result_type="expand")
    r["poll_m"], r["act_m"] = o[0], o[1]
    r = r.dropna(subset=["poll_m", "act_m"])
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
