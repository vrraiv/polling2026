"""House special elections: which national environment fits them, and does the year of the term matter? (PLAN.md,
"After the scorecard", item 5; companion to the governor off-cycle test in src/model/environment.py.)

Data: data/interim/house_specials.csv (src/collect/specials.py): 2007-2026 specials with a Democrat and a Republican,
not on a general-election day, no third candidate at 15%+, with the district's Cook PVI on the lines in force.

Prior: the frozen House district model (data/final/house_structure.json) for an open seat:
    margin = const + b * lean2 + g * environment        (lean2 = 2 x PVI)
Environment estimators on the special's date (src/model/environment.py): the last House vote carried forward; the
fundamentals-style estimate at m = 0 and m = 1; and m fitted by year of the presidential term (1-4), leave-one-
calendar-year-out. Also each special's implied environment (inverting the prior) and the overperformance of the
party out of the White House against each estimator.
The forecasting specification (prospective()): m by half of the term (years 1-2 vs 3-4) plus the shrunk mean
residual of specials in the prior 12 months, which tracks how the special electorate currently leans (Democratic
since 2017, Republican in 2009-10) without hard-coding an era.

Run:  python src/model/special_model.py
Writes data/processed/specials_environment.json
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT  # noqa: E402
import environment as E  # noqa: E402

OUT = ROOT / "data" / "processed"
HS = json.loads((ROOT / "data/final/house_structure.json").read_text())["chosen"]
INAUGURATIONS = [pd.Timestamp(f"{y}-01-20") for y in (2005, 2009, 2013, 2017, 2021, 2025)]


def term_year(date):
    """1-4: which year of the presidential term (counted from Jan 20) the date falls in."""
    start = max(i for i in INAUGURATIONS if i <= date)
    return int((date - start).days // 365.25) + 1


def load():
    d = pd.read_csv(ROOT / "data/interim/house_specials.csv", parse_dates=["date"])
    d = d[~d.multi_candidate.astype(bool) & d.pvi.notna()].copy()
    d["term_year"] = d.date.map(term_year)
    d["base"] = HS["const"] + HS["b_lean2"] * d.lean2               # the prior with environment 0
    model = E.fit(E.training())
    parts = {dt: (E.env_on(dt, "fund", 0.0, model), E.env_on(dt, "fund", 1.0, model)[0], E.env_on(dt, "prev_vote")[0])
             for dt in d.date.unique()}
    d["e0"] = d.date.map(lambda x: parts[x][0][0])
    d["slope"] = d.date.map(lambda x: parts[x][1] - parts[x][0][0])
    d["prev_vote"] = d.date.map(lambda x: parts[x][2])
    d["approval"] = d.date.map(lambda x: parts[x][0][1].get("approval"))
    d["president"] = d.date.map(lambda x: parts[x][0][1].get("president"))
    d["implied_env"] = (d.margin_2p - d.base) / HS["g_nat"]
    d["out_sign"] = np.where(d.president == "D", -1, 1)              # + = toward the party out of the White House
    return d


def best_m(x):
    """Least-squares m on margins: margin - base - g*e0 = g*slope*m."""
    g = HS["g_nat"]
    yv, xv = x.margin_2p - x.base - g * x.e0, g * x.slope
    return float((xv * yv).sum() / (xv ** 2).sum())


def prospective(d, k_values=(None, 0, 2, 4, 8)):
    """The specification for forecasting a special: m by half of the presidential term (years 1-2 vs 3-4; fitted
    without the special's calendar year), plus the mean residual of specials in the prior 12 months (strictly earlier
    races), shrunk by n / (n + k). k=None: no recent-specials term."""
    g = HS["g_nat"]
    d = d.sort_values("date").copy()
    d["half2"] = (d.term_year >= 3).astype(int)
    out = []
    for k in k_values:
        pred = []
        for _, r in d.iterrows():
            tr = d[d.date.dt.year != r.date.year]
            mh = {h: best_m(tr[tr.half2 == h]) for h in (0, 1)}
            env = r.e0 + r.slope * mh[r.half2]
            if k is not None:
                past = d[(d.date < r.date) & (d.date >= r.date - pd.Timedelta(days=365))]
                if len(past):
                    resid = (past.implied_env - (past.e0 + past.slope * past.half2.map(mh))).mean()
                    env += resid * len(past) / (len(past) + k)
            pred.append(r.base + g * env)
        e = d.margin_2p.values - np.array(pred)
        out.append({"recent_specials_k": k, "rmse": float(np.sqrt((e ** 2).mean())), "mae": float(np.abs(e).mean()),
                    "mean_err": float(e.mean()), "winner_acc": float(((np.array(pred) > 0) == (d.margin_2p.values > 0)).mean())})
    halves = {h: best_m(d[d.half2 == h]) for h in (0, 1)}
    return out, halves


def main():
    d = load()
    g = HS["g_nat"]
    pred = {"prev_vote": d.base + g * d.prev_vote, "fund_m0": d.base + g * d.e0, "fund_m1": d.base + g * (d.e0 + d.slope)}
    # m by term year, leave-one-calendar-year-out
    cv = pd.Series(index=d.index, dtype=float)
    m_cv = {}
    for y in sorted(d.date.dt.year.unique()):
        te = d.date.dt.year == y
        for ty in d[te].term_year.unique():
            tr = d[~te & (d.term_year == ty)]
            m = best_m(tr) if len(tr) else 1.0
            k = te & (d.term_year == ty)
            cv[k] = d.base[k] + g * (d.e0[k] + d.slope[k] * m)
            m_cv.setdefault(int(ty), []).append(round(m, 2))
    pred["fund_m_by_term_year (LOYO)"] = cv
    pred["fund_m_pooled (LOYO)"] = pd.Series(
        [d.base[i] + g * (d.e0[i] + d.slope[i] * best_m(d[d.date.dt.year != d.date[i].year])) for i in d.index], index=d.index)
    res = {}
    for k, p in pred.items():
        e = d.margin_2p - p
        res[k] = {"n": int(len(e)), "rmse": float(np.sqrt((e ** 2).mean())), "mae": float(e.abs().mean()),
                  "mean_err": float(e.mean()), "out_party_overperformance": float((e * d.out_sign).mean()),
                  "winner_acc": float(((p > 0) == (d.margin_2p > 0)).mean())}
    m_all = {int(ty): {"m": best_m(x), "n": int(len(x))} for ty, x in d.groupby("term_year")}
    m_all["pooled"] = {"m": best_m(d), "n": int(len(d))}
    over = d.assign(over=(d.implied_env - (d.e0 + d.slope)) * d.out_sign).groupby("term_year").over.agg(["size", "mean", "std"])
    pros, halves = prospective(d)
    gov = json.loads((OUT / "governor_model.json").read_text()).get("offcycle_m", {}) if (OUT / "governor_model.json").exists() else {}
    out = {"question": "Which national environment fits House special elections, and does the year of the term matter?",
           "n_specials": int(len(d)), "prior": {k: HS[k] for k in ("const", "b_lean2", "g_nat")}, "errors": res,
           "m_by_term_year_all_data": m_all, "m_by_term_year_loyo_values": m_cv,
           "out_party_overperformance_vs_m1_by_term_year": over.round(2).reset_index().to_dict("records"),
           "governor_offcycle_m": gov,
           "prospective": {"by_k": pros, "m_by_half_all_data": {"years_1_2": halves[0], "years_3_4": halves[1]},
                           "chosen_k": 2, "note": "k chosen among 0, 2, 4, 8; the recent-specials term uses only earlier races"},
           "specials": d[["date", "state", "district", "term_year", "president", "approval", "margin_2p", "pvi", "implied_env",
                          "prev_vote", "e0", "slope"]].assign(date=d.date.dt.date.astype(str)).round(2).to_dict("records")}
    (OUT / "specials_environment.json").write_text(json.dumps(out, indent=1, default=float))
    pd.set_option("display.width", 200)
    print(f"{len(d)} specials; prior const {HS['const']:.2f}, lean {HS['b_lean2']:.2f}, environment {HS['g_nat']:.2f}")
    print(pd.DataFrame(res).T.round(2).to_string())
    print("m by term year (all data):", {k: (round(v["m"], 2), v["n"]) for k, v in m_all.items()}, "| governors:", gov)
    print("prospective spec (m by term half + recent specials):"); print(pd.DataFrame(pros).round(2).to_string(index=False))
    print("m by term half (all data):", {k: round(v, 2) for k, v in halves.items()})
    print("out-party overperformance against m=1, by term year:"); print(over.round(2).to_string())
    print(d.groupby(d.date.dt.year).apply(lambda x: pd.Series({"n": len(x), "implied": x.implied_env.mean(), "m1": (x.e0 + x.slope).mean(), "prev": x.prev_vote.mean()}), include_groups=False).round(1).to_string())


if __name__ == "__main__":
    main()
