"""Estimate the fundamentals model of the national House vote (replaces the assumed coefficients).

Outcome: two-party House vote margin of the PRESIDENT'S party (Wikipedia infoboxes, 1946-2022).
Candidate predictors (measured as of September of the election year, i.e. before the election):
  approval   Gallup job approval, mean of polls ending Jul 15-Oct 31 (American Presidency Project sheet;
             2022 from Gallup rows in 538's archive; 2026 = aggregator mean adjusted to Gallup's house effect)
  prev       president's-party House margin at the previous election (regression to the mean)
  infl       CPI-U inflation, Sept/Sept (CPIAUCNS: never revised, so no vintage issue)
  gas        real gasoline price change, Sept/Sept (gasoline CPI CUUR0000SETB01 / CPI-U)
  rdi        real disposable income per capita growth, Sept/Sept (A229RX0, 1959+; current vintage = revised data)
  unemp      change in the unemployment rate over the prior 12 months
  midterm    1 in midterm years (only in the all-elections model)

Model selection: every subset of up to 4 predictors, OLS, scored by leave-one-election-out RMSE on a
common sample (1962-2022, because RDI starts in 1959). The 2026 prediction averages the top
specifications weighted by 1/LOO-MSE; its error SD is the LOO RMSE of that average.
Writes data/processed/fundamentals.json and data/interim/fundamentals_dataset.csv
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT, fetch, latest  # noqa: E402

PRES_PARTY = {1946: "D", 1948: "D", 1950: "D", 1952: "D", 1954: "R", 1956: "R", 1958: "R", 1960: "R", 1962: "D",
              1964: "D", 1966: "D", 1968: "D", 1970: "R", 1972: "R", 1974: "R", 1976: "R", 1978: "D", 1980: "D",
              1982: "R", 1984: "R", 1986: "R", 1988: "R", 1990: "R", 1992: "R", 1994: "D", 1996: "D", 1998: "D",
              2000: "D", 2002: "R", 2004: "R", 2006: "R", 2008: "R", 2010: "D", 2012: "D", 2014: "D", 2016: "D",
              2018: "R", 2020: "R", 2022: "D", 2026: "R"}
PREDICTORS = ["approval", "prev", "infl", "gas", "rdi", "unemp"]


def fred(sid):
    fetch("fred", f"{sid}.csv", "https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid})
    d = pd.read_csv(latest("fred", f"{sid}.csv"))
    d.columns = ["date", "v"]
    d["date"] = pd.to_datetime(d.date)
    d["v"] = pd.to_numeric(d.v, errors="coerce")
    return d.dropna().set_index("date").v


def yoy(series, year, month=9, pct=True):
    a = series.get(pd.Timestamp(year=year, month=month, day=1))
    b = series.get(pd.Timestamp(year=year - 1, month=month, day=1))
    if a is None or b is None:
        return np.nan
    return 100 * (a / b - 1) if pct else a - b


def gallup_house_effect():
    """Gallup minus the all-pollster average (adults/RV), by month, Trump 1 + Biden (538 archive)."""
    g = pd.read_csv(latest("538_wayback", "president_approval_polls_historical.csv"), low_memory=False)
    g["end"] = pd.to_datetime(g.end_date, format="%m/%d/%y", errors="coerce")
    g["ym"] = g.end.dt.to_period("M")
    allm = g.groupby(["politician", "ym"]).yes.mean()
    gal = g[g.pollster.str.contains("Gallup", na=False)].groupby(["politician", "ym"]).yes.mean()
    diff = (gal - allm.reindex(gal.index)).dropna()
    return float(diff.mean()), int(len(diff)), g


def build():
    vote = pd.read_csv(ROOT / "data/interim/house_national_vote.csv").set_index("year").two_party_margin_D
    gal = pd.read_csv(ROOT / "data/interim/gallup_approval.csv", parse_dates=["end"])
    offset, n_off, g538 = gallup_house_effect()
    cpi, gas, rdi, ur = fred("CPIAUCNS"), fred("CUUR0000SETB01"), fred("A229RX0"), fred("UNRATE")
    rows = []
    for y, party in PRES_PARTY.items():
        sign = 1 if party == "D" else -1
        win = gal[(gal.end >= f"{y}-07-15") & (gal.end <= f"{y}-10-31")]
        prior = gal[(gal.end >= f"{y}-04-01") & (gal.end <= f"{y}-10-31")]
        if len(win):
            appr, src = float(win.Approving.mean()), "Gallup (APP sheet)"
        elif len(prior):  # Gallup gap in late summer (1948, 1964, 1972, 1976): use the latest polls before November
            appr, src = float(prior.sort_values("end").Approving.tail(2).mean()), "Gallup (latest Apr-Oct polls; window gap)"
        elif y == 2022:
            w = g538[(g538.politician == "Joe Biden") & g538.pollster.str.contains("Gallup", na=False)
                     & (g538.end >= "2022-07-15") & (g538.end <= "2022-10-31")]
            appr, src = float(w.yes.mean()), "Gallup (538 archive)"
        elif y == 2026:
            nat = json.loads((ROOT / "data/processed/national_inputs.json").read_text())
            appr, src = nat["approval"] + offset, f"aggregator mean {nat['approval']:.1f} + Gallup house effect {offset:+.1f}"
        else:
            appr, src = np.nan, "missing"
        real_gas = (gas / cpi).dropna()
        rows.append(dict(
            year=y, pres_party=party, midterm=int(y % 4 == 2),
            outcome=sign * vote.get(y, np.nan) if y in vote.index else np.nan,
            prev=sign * vote.get(y - 2, np.nan) if (y - 2) in vote.index else np.nan,
            approval=appr, approval_source=src,
            infl=yoy(cpi, y), gas=yoy(real_gas, y), rdi=yoy(rdi, y),
            unemp=yoy(ur, y, pct=False),
            gas_nominal_level=float(fred("APU000074714").get(pd.Timestamp(year=y, month=9, day=1), np.nan)) if y >= 1977 else np.nan,
        ))
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "data/interim/fundamentals_dataset.csv", index=False)
    return df, offset, n_off


def loo(df, xs):
    X = sm.add_constant(df[xs].values, has_constant="add")
    y = df.outcome.values
    errs = []
    for i in range(len(df)):
        m = np.ones(len(df), bool); m[i] = False
        b = np.linalg.lstsq(X[m], y[m], rcond=None)[0]
        errs.append(y[i] - X[i] @ b)
    return np.array(errs)


def select(df, extra=(), max_k=4, top=5):
    specs = []
    for k in range(0, max_k + 1):
        for xs in itertools.combinations(PREDICTORS, k):
            xs = list(xs) + list(extra)
            e = loo(df, xs) if xs else df.outcome.values - np.array([np.delete(df.outcome.values, i).mean() for i in range(len(df))])
            specs.append({"vars": xs, "loo_rmse": float(np.sqrt(np.mean(e ** 2))), "loo_errs": e})
    specs.sort(key=lambda r: r["loo_rmse"])
    return specs


def fit(df, xs):
    m = sm.OLS(df.outcome, sm.add_constant(df[xs], has_constant="add")).fit()
    return m


def main():
    df, offset, n_off = build()
    hist = df[df.year <= 2022].dropna(subset=["outcome"])
    target = df[df.year == 2026].iloc[0]
    print(hist[["year", "pres_party", "midterm", "outcome", "prev", "approval", "infl", "gas", "rdi", "unemp"]].round(1).to_string(index=False))
    print(f"\n2026 inputs: approval {target.approval:.1f} ({target.approval_source}); infl {target.infl:.1f}; real gas {target.gas:+.1f}%; "
          f"rdi {target.rdi:+.1f}; unemp {target.unemp:+.1f}; prev {target.prev:+.1f}; gas $ {target.gas_nominal_level}")
    common = hist[hist.year >= 1962].dropna(subset=PREDICTORS)
    mid = common[common.midterm == 1]
    print(f"\ncorr(infl, real gas) all years {common.infl.corr(common.gas):.2f}; corr(infl, approval) {common.infl.corr(common.approval):.2f}")
    out = {"gallup_offset": offset, "gallup_offset_months": n_off, "inputs_2026": {k: (float(target[k]) if k != "approval_source" else target[k]) for k in PREDICTORS + ["approval_source"]}}
    for label, data, extra in [("midterms_1962_2022", mid, ()), ("all_1962_2022", common, ("midterm",))]:
        specs = select(data, extra=extra)
        top = specs[:5]
        w = np.array([1 / s["loo_rmse"] ** 2 for s in top]); w /= w.sum()
        preds, fits = [], []
        for s, wi in zip(top, w):
            if s["vars"]:
                m = fit(data, s["vars"])
                x = np.r_[1.0, [float(target[v]) for v in s["vars"]]]
                preds.append(float(x @ m.params.values))
                fits.append({"vars": s["vars"], "weight": float(wi), "loo_rmse": s["loo_rmse"], "pred_2026": preds[-1],
                             "coef": {k: float(v) for k, v in m.params.items()}, "se": {k: float(v) for k, v in m.bse.items()},
                             "r2": float(m.rsquared)})
            else:
                preds.append(float(data.outcome.mean()))
                fits.append({"vars": [], "weight": float(wi), "loo_rmse": s["loo_rmse"], "pred_2026": preds[-1]})
        avg = float(np.dot(w, preds))
        avg_errs = sum(wi * s["loo_errs"] for s, wi in zip(top, w))
        avg_rmse = float(np.sqrt(np.mean(avg_errs ** 2)))
        # requested predictors, shown even if they don't win
        shown = {}
        for xs in (["approval"], ["approval", "prev"], ["approval", "infl"], ["approval", "gas"], ["approval", "prev", "infl"],
                   ["approval", "prev", "gas"], ["approval", "prev", "rdi"], ["infl"], ["gas"], ["approval", "prev", "infl", "gas"]):
            xs2 = xs + list(extra)
            m = fit(data, xs2)
            e = loo(data, xs2)
            x = np.r_[1.0, [float(target[v]) for v in xs2]]
            shown[" + ".join(xs)] = {"loo_rmse": float(np.sqrt(np.mean(e ** 2))), "pred_2026": float(x @ m.params.values),
                                     "coef": {k: float(v) for k, v in m.params.items()}, "se": {k: float(v) for k, v in m.bse.items()}}
        # stability: drop inflation outliers
        best = top[0]["vars"] or ["approval"]
        stab = {}
        for drop in (1974, 2022, 1980):
            if drop in data.year.values:
                m = fit(data[data.year != drop], best)
                stab[f"without_{drop}"] = {k: float(v) for k, v in m.params.items()}
        no_mean = float(data.outcome.mean())
        null_rmse = next(s["loo_rmse"] for s in specs if not s["vars"] or s["vars"] == list(extra))
        out[label] = {"n": int(len(data)), "years": data.year.tolist(), "top": fits, "pred_2026_pres_party": avg, "loo_rmse_avg": avg_rmse,
                      "null_loo_rmse": null_rmse, "requested_specs": shown, "stability": stab,
                      "range_check": {v: {"min": float(data[v].min()), "max": float(data[v].max()), "2026": float(target[v])} for v in PREDICTORS}}
        print(f"\n=== {label} (n={len(data)}) — top specs by LOO RMSE (null model {null_rmse:.2f}) ===")
        for f in fits:
            print(f"  {' + '.join(f['vars']) or '(mean)':38} w={f['weight']:.2f} LOO {f['loo_rmse']:.2f}  2026 pred {f['pred_2026']:+.1f}  "
                  + ("coef " + ", ".join(f"{k}={v:+.2f}±{f['se'][k]:.2f}" for k, v in f["coef"].items()) if f["vars"] else ""))
        print(f"  -> averaged 2026 president's-party margin {avg:+.2f} (LOO RMSE of average {avg_rmse:.2f})  => D margin {-avg:+.2f}")
        print("  requested specs:")
        for k, v in shown.items():
            print(f"    {k:32} LOO {v['loo_rmse']:.2f}  2026 {v['pred_2026']:+.1f}  " + ", ".join(f"{kk}={vv:+.2f}±{v['se'][kk]:.2f}" for kk, vv in v["coef"].items() if kk != "const"))
        print("  stability of best spec:", {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in stab.items()})
        print("  2026 vs historical range:", {v: (round(r["min"], 1), round(r["max"], 1), round(r["2026"], 1)) for v, r in out[label]["range_check"].items()})
    (ROOT / "data/processed/fundamentals.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    main()
