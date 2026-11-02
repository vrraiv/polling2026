"""Backtest the poll-averaging + uncertainty method on 2018 and 2022 (Senate races and generic ballot).

Uses archived 538 poll files (Wayback) and actual results from 538 raw_polls.csv (joined on race_id).
Same weighting as the 2026 model (recency half-life, population, sample size, partisan-sponsor shift,
per-pollster down-weighting). Polls only: no PVI prior (historical PVIs not collected), so this is a
test of the poll-average component and its stated uncertainty.

Caveat: the error scales were calibrated on 1998-2022 data that include these cycles (in-sample).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT, latest  # noqa: E402

CAL = json.loads((ROOT / "data/processed/calibration.json").read_text())
SD_RACE = CAL["Sen-G"]["race_resid_sd_midterms"]
SEN_CYC = [c["mean"] for c in CAL["Sen-G"]["cycles"] if c["cycle"] % 2 == 0]
SD_NAT = float(np.sqrt(np.mean(np.square(SEN_CYC))))
DF_T = 5
ELECTION = {2018: pd.Timestamp("2018-11-06"), 2022: pd.Timestamp("2022-11-08")}
POP_W = {"lv": 1.0, "rv": 0.8, "a": 0.5, "v": 0.9}


def wavg(df, asof, half_life):
    age = (asof - df.end).dt.days
    w = 0.5 ** (age / half_life) * np.sqrt(df.n.clip(upper=3000).fillna(600) / 600) * df.population.str.lower().map(POP_W).fillna(0.7)
    k = df.groupby("pollster").pollster.transform("size")
    w = w / np.sqrt(k)
    m = df.m + np.where(df.partisan == "DEM", -2, np.where(df.partisan == "REP", 2, 0))
    avg = np.average(m, weights=w)
    neff = w.sum() ** 2 / (w ** 2).sum()
    spread = np.sqrt(np.average((m - avg) ** 2, weights=w))
    return avg, neff, spread, len(df)


def senate():
    p = pd.read_csv(latest("538_wayback", "senate_polls_historical.csv"), low_memory=False)
    p = p[p.cycle.isin([2018, 2022]) & (p.stage == "general") & (p.hypothetical != True)]  # noqa: E712
    p["end"] = pd.to_datetime(p.end_date, format="%m/%d/%y")
    act = pd.read_csv(latest("538_github", "raw_polls.csv"), low_memory=False)
    act = act[act.type_simple == "Sen-G"].drop_duplicates("race_id")

    def actual(r):
        if r.cand1_party == "DEM" and r.cand2_party == "REP":
            return r.cand1_actual - r.cand2_actual
        if r.cand1_party == "REP" and r.cand2_party == "DEM":
            return r.cand2_actual - r.cand1_actual
        return np.nan
    act["act"] = act.apply(actual, axis=1)
    act = act.dropna(subset=["act"]).set_index("race_id")

    # one row per question: top DEM vs top REP
    q = p[p.party.isin(["DEM", "REP"])].groupby(["question_id", "party"]).pct.max().unstack()
    q = q.dropna()
    q["m"] = 100 * (q.DEM - q.REP) / (q.DEM + q.REP)
    meta = p.drop_duplicates("question_id").set_index("question_id")[["race_id", "cycle", "state", "pollster", "end", "sample_size", "population", "partisan"]]
    q = q.join(meta).rename(columns={"sample_size": "n"})
    q["population"] = q.population.fillna("lv").astype(str)
    rows = []
    for (cyc, rid), g in q.groupby(["cycle", "race_id"]):
        cutoff = ELECTION[cyc] - pd.Timedelta(days=5)
        g = g[(g.end <= cutoff) & (g.end >= cutoff - pd.Timedelta(days=140))]
        if g.empty or rid not in act.index:
            continue
        avg, neff, spread, n = wavg(g, cutoff, 21)
        sd_race = np.sqrt(SD_RACE ** 2 + max(spread, 4.0) ** 2 / neff)
        sd = np.sqrt(SD_NAT ** 2 + sd_race ** 2)
        pd_ = stats.t.cdf(avg / (sd * np.sqrt((DF_T - 2) / DF_T)), DF_T)
        rows.append(dict(cycle=cyc, race_id=rid, state=g.state.iloc[0], n_polls=n, poll_avg=avg,
                         actual=act.loc[rid, "act"], p_dem=pd_))
    df = pd.DataFrame(rows)
    df["err"] = df.actual - df.poll_avg
    df["dem_won"] = df.actual > 0
    df["correct"] = (df.p_dem > 0.5) == df.dem_won
    df["brier"] = (df.p_dem - df.dem_won) ** 2
    return df


def generic():
    g = pd.read_csv(latest("538_wayback", "generic_ballot_polls_historical.csv"), low_memory=False)
    g = g[g.cycle.isin([2018, 2022])].copy()
    g["end"] = pd.to_datetime(g.end_date, format="%m/%d/%y")
    g["m"] = 100 * (g.dem - g.rep) / (g.dem + g.rep)
    g = g.rename(columns={"sample_size": "n"})
    g["population"] = g.population.fillna("lv").astype(str)
    act = pd.read_csv(latest("538_github", "raw_polls.csv"), low_memory=False)
    act = act[act.type_simple == "House-G-US"]
    out = []
    for cyc in [2018, 2022]:
        cutoff = ELECTION[cyc] - pd.Timedelta(days=5)
        x = g[(g.cycle == cyc) & (g.end <= cutoff) & (g.end >= cutoff - pd.Timedelta(days=90))]
        avg, neff, spread, n = wavg(x, cutoff, 14)
        a = act[act.cycle == cyc].iloc[0]
        actual = (a.cand1_actual - a.cand2_actual) if a.cand1_party == "DEM" else (a.cand2_actual - a.cand1_actual)
        out.append(dict(cycle=cyc, n_polls=n, generic_avg_two_party=avg, actual_house_margin=actual, error=actual - avg))
    return pd.DataFrame(out)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    s = senate()
    s.to_csv(ROOT / "data/processed/backtest_senate_2018_2022.csv", index=False)
    gen = generic()
    gen.to_csv(ROOT / "data/processed/backtest_generic_2018_2022.csv", index=False)
    summ = {}
    for cyc, g in s.groupby("cycle"):
        summ[int(cyc)] = dict(races=len(g), winner_accuracy=float(g.correct.mean()), brier=float(g.brier.mean()),
                              mean_error=float(g.err.mean()), mae=float(g.err.abs().mean()),
                              misses=g.loc[~g.correct, ["state", "poll_avg", "actual", "p_dem"]].round(2).to_dict("records"))
        print(cyc, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in summ[int(cyc)].items()})
    # calibration bins
    s["bin"] = pd.cut(s.p_dem, [0, .1, .3, .5, .7, .9, 1])
    print(s.groupby("bin", observed=True).agg(n=("dem_won", "size"), p_mean=("p_dem", "mean"), dem_win_rate=("dem_won", "mean")).round(2))
    print(gen.round(2).to_string())
    summ["generic"] = gen.round(2).to_dict("records")
    (ROOT / "data/processed/backtest_summary.json").write_text(json.dumps(summ, indent=1, default=str))
