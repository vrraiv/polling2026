"""Estimate the House district model (replaces the assumed district SD, incumbency bonus and district-poll error).

Data: Wikipedia 2018/2022/2024 House election pages (cached in data/raw/wikipedia_hist): every district's Cook PVI
at the time, incumbent, status and candidate vote shares. National two-party House margin from
data/interim/house_national_vote.csv. District polls (final 21 days) with results: 538 raw_polls.csv, 2018 & 2022.

Model (contested D-vs-R races; two-party D-R margin):
    margin = a + b*(2*PVI) + c*national_margin + inc*(+1 Dem incumbent running / -1 Rep incumbent running / 0 open) + e
Also with cycle fixed effects instead of the national margin. Residual SD reported overall and in the competitive
band (|expected margin| <= 15), which is what drives seat probabilities.
District polls: result - prior = w * (poll - prior), prior = fitted structural model using the final generic-ballot
poll average (known before the election). Implied district-poll SD given the estimated district SD.
Writes data/processed/house_structure.json and data/interim/house_history.csv
"""
import json
import re
import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT, latest  # noqa: E402
from wiki import STATE_ABBR, flat, pvi as parse_pvi, clean  # noqa: E402
import bias_analysis as BA  # noqa: E402

CAND = re.compile(r"▌\s*([^▌(]+?)\s*\(([^)]+)\)\s*([\d.]+)%")


def parse_year(y):
    html = latest("wikipedia_hist", f"{y}_United_States_House_of_Representatives_elections.html").read_text(encoding="utf-8")
    rows = []
    for t in pd.read_html(StringIO(html)):
        t = flat(t)
        pcol = [c for c in t.columns if "PVI" in c]
        if not pcol:
            continue
        status_col = next((c for c in t.columns if "Result" in c or "Status" in c), None)
        cand_col = next((c for c in t.columns if "Candidates" in c), None)
        party_col = next((c for c in t.columns if "Party" in c), None)
        loc_col = t.columns[0]
        if not status_col or not cand_col or not party_col:
            continue
        for _, r in t.iterrows():
            loc = str(r[loc_col]).replace(" ", " ").strip()
            m = re.match(r"(.+?)\s+(\d+|at-large|At-large)$", loc)
            if not m or m.group(1) not in STATE_ABBR:
                continue
            text = str(r[cand_col])
            if "First round" in text or "round" in text.lower():   # ranked-choice (AK, ME): skip
                continue
            shares = {"D": 0.0, "R": 0.0, "O": 0.0}
            top = {"D": 0.0, "R": 0.0}
            for name, party, pct in CAND.findall(text):
                pct = float(pct)
                k = "D" if party.startswith("Democratic") or party in ("DFL",) else "R" if party.startswith("Republican") else "O"
                shares[k] += pct
                if k in top:
                    top[k] = max(top[k], pct)
            status = clean(r[status_col])
            party = clean(r[party_col])
            inc_ran = bool(re.search(r"re-elected|lost re-election|Incumbent lost\.|defeated", status, re.I)) and not re.search(r"renomination|primary", status, re.I)
            rows.append(dict(year=y, state=STATE_ABBR[m.group(1)], district=0 if m.group(2).lower() == "at-large" else int(m.group(2)),
                             pvi=parse_pvi(r[pcol[0]]), inc_party="D" if party.startswith("Democratic") else "R" if party.startswith("Republican") else "",
                             inc_ran=inc_ran, status=status, d_top=top["D"], r_top=top["R"], other=shares["O"],
                             n_d=text.count("(Democratic"), n_r=text.count("(Republican")))
    return pd.DataFrame(rows)


def main():
    YEARS = (2006, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024)
    parts = []
    for y in YEARS:
        try:
            parts.append(parse_year(y))
        except Exception as ex:  # noqa: BLE001
            print("skip", y, ex)
    df = pd.concat(parts, ignore_index=True)
    df = df.drop_duplicates(["year", "state", "district"])
    vote = pd.read_csv(ROOT / "data/interim/house_national_vote.csv").set_index("year").two_party_margin_D
    df["nat"] = df.year.map(vote)
    contested = (df.d_top > 0) & (df.r_top > 0) & (df.n_d == 1) & (df.n_r == 1) & (df.other < 15) & df.pvi.notna()
    df["contested"] = contested
    df["margin"] = np.where(contested, 100 * (df.d_top - df.r_top) / (df.d_top + df.r_top), np.nan)
    df["inc"] = np.where(df.inc_ran & (df.inc_party == "D"), 1, np.where(df.inc_ran & (df.inc_party == "R"), -1, 0))
    df["lean2"] = 2 * df.pvi
    df.to_csv(ROOT / "data/interim/house_history.csv", index=False)
    d = df[df.contested].copy()
    print(f"parsed {len(df)} district-elections; contested D-vs-R used: {len(d)} "
          f"({d.groupby('year').size().to_dict()}); incumbents running {int((d.inc != 0).sum())}, open {int((d.inc == 0).sum())}")
    m1 = smf.ols("margin ~ lean2 + nat + inc", d).fit(cov_type="cluster", cov_kwds={"groups": d.year.astype(str) + d.state})
    m2 = smf.ols("margin ~ lean2 + C(year) + inc", d).fit(cov_type="cluster", cov_kwds={"groups": d.year.astype(str) + d.state})
    # constrained form used in the forecast: margin - (2PVI + nat) = inc*delta + e
    d["resid0"] = d.margin - d.lean2 - d.nat
    m3 = smf.ols("resid0 ~ inc", d).fit(cov_type="cluster", cov_kwds={"groups": d.year.astype(str) + d.state})
    d["expected"] = d.lean2 + d.nat + m3.params["inc"] * d.inc + m3.params["Intercept"]
    d["e"] = d.margin - d.expected
    comp = d[d.expected.abs() <= 15]
    robust = lambda x: float(1.4826 * np.median(np.abs(x - np.median(x))))  # noqa: E731
    out = {"n": int(len(d)), "by_year": d.groupby("year").size().to_dict(),
           "free": {k: {"coef": float(m1.params[k]), "se": float(m1.bse[k])} for k in ["Intercept", "lean2", "nat", "inc"]},
           "cycle_fe": {k: {"coef": float(m2.params[k]), "se": float(m2.bse[k])} for k in ["lean2", "inc"]},
           "constrained": {k: {"coef": float(m3.params[k]), "se": float(m3.bse[k])} for k in ["Intercept", "inc"]},
           "sd_all": float(d.e.std()), "sd_all_robust": robust(d.e),
           "sd_competitive": float(comp.e.std()), "sd_competitive_robust": robust(comp.e), "n_competitive": int(len(comp)),
           "sd_competitive_open": float(comp[comp.inc == 0].e.std()), "sd_competitive_inc": float(comp[comp.inc != 0].e.std()),
           "winner_acc_competitive": float(((comp.expected > 0) == (comp.margin > 0)).mean())}
    # by-year residual mean (does the structural model drift?)
    out["mean_resid_by_year"] = d.groupby("year").e.mean().round(2).to_dict()
    print("free fit:", {k: f"{v['coef']:+.2f}±{v['se']:.2f}" for k, v in out["free"].items()})
    print("cycle FE:", {k: f"{v['coef']:+.2f}±{v['se']:.2f}" for k, v in out["cycle_fe"].items()})
    print("constrained (slope 1 on 2PVI and national):", {k: f"{v['coef']:+.2f}±{v['se']:.2f}" for k, v in out["constrained"].items()})
    print(f"district residual SD: all {out['sd_all']:.2f} (robust {out['sd_all_robust']:.2f}); competitive |exp|<=15 n={len(comp)}: "
          f"{out['sd_competitive']:.2f} (robust {out['sd_competitive_robust']:.2f}); open {out['sd_competitive_open']:.2f}, incumbent {out['sd_competitive_inc']:.2f}")
    print("mean residual by year:", out["mean_resid_by_year"])

    # ---- leave-one-year-out: predict each held-out year's contested districts from the others
    lo = []
    for y in sorted(d.year.unique()):
        tr, te = d[d.year != y], d[d.year == y]
        mf = smf.ols("margin ~ lean2 + nat + inc", tr).fit()
        mc = smf.ols("resid0 ~ inc", tr).fit()
        pf = mf.predict(te); pc = te.lean2 + te.nat + mc.params["Intercept"] + mc.params["inc"] * te.inc
        comp_te = te[(pc.abs() <= 15)]
        lo.append({"year": int(y), "nat": float(te.nat.iloc[0]), "n": int(len(te)),
                   "bias_free": float((te.margin - pf).mean()), "bias_constrained": float((te.margin - pc).mean()),
                   "rmse_free": float(np.sqrt(((te.margin - pf) ** 2).mean())), "rmse_constrained": float(np.sqrt(((te.margin - pc) ** 2).mean())),
                   "seat_err_free": int(((pf > 0) != (te.margin > 0)).sum()), "seat_err_constrained": int(((pc > 0) != (te.margin > 0)).sum())})
    lo = pd.DataFrame(lo)
    out["loyo"] = lo.round(3).to_dict("records")
    out["loyo_summary"] = {"rmse_free": float(np.sqrt((lo.rmse_free ** 2 * lo.n).sum() / lo.n.sum())),
                           "rmse_constrained": float(np.sqrt((lo.rmse_constrained ** 2 * lo.n).sum() / lo.n.sum())),
                           "seat_err_free": int(lo.seat_err_free.sum()), "seat_err_constrained": int(lo.seat_err_constrained.sum())}
    print(lo.round(2).to_string(index=False))
    print("leave-one-year-out:", out["loyo_summary"])

    # ---- chosen parameters for the forecast
    #   PVI slope, incumbency, constant: polarized era 2018-2024 (incumbency fell from ~20 pts in 2006 to ~4 since 2018)
    #   national slope: all 10 cycles 2006-2024 (stable across eras, 0.75-0.78; needs wave years to be identified)
    #   district SD: competitive-band residual SD, 2016-2024 (5 cycles; slightly conservative for out-of-sample use)
    rec = d[d.year >= 2018]
    mr = smf.ols("margin ~ lean2 + nat + inc", rec).fit(cov_type="cluster", cov_kwds={"groups": rec.year})
    mn = smf.ols("margin ~ lean2 + nat + inc", d).fit(cov_type="cluster", cov_kwds={"groups": d.year})
    r16 = d[d.year >= 2016]
    m16 = smf.ols("margin ~ lean2 + nat + inc", r16).fit()
    e16 = r16.margin - m16.fittedvalues
    sd16 = float(e16[m16.fittedvalues.abs() <= 15].std())
    g = float(mn.params["nat"])
    # re-fit the 2018-24 constant and slopes holding the national slope at g
    rec2 = rec.assign(adj=rec.margin - g * rec.nat)
    mr2 = smf.ols("adj ~ lean2 + inc", rec2).fit(cov_type="cluster", cov_kwds={"groups": rec2.year})
    out["chosen"] = {"const": float(mr2.params["Intercept"]), "b_lean2": float(mr2.params["lean2"]), "g_nat": g,
                     "inc": float(mr2.params["inc"]), "sd_district": sd16,
                     "se": {"b_lean2": float(mr2.bse["lean2"]), "g_nat": float(mn.bse["nat"]), "inc": float(mr2.bse["inc"])},
                     "inc_by_year": {int(y): float(smf.ols("margin ~ lean2 + inc", gg).fit().params["inc"]) for y, gg in d.groupby("year")}}
    print("chosen:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out["chosen"].items() if k not in ("inc_by_year",)})
    ch = out["chosen"]

    # ---- district polls vs structural prior (2018, 2022)
    r = BA.load()
    gen = BA.race_level(r, ["House-G-US"]).set_index("cycle").poll
    hp = BA.race_level(r, ["House-G"])
    hp = hp[hp.cycle.isin([2018, 2022])].copy()
    hp["state"] = hp.location.str.split("-").str[0]
    hp["district"] = pd.to_numeric(hp.location.str.split("-").str[1], errors="coerce")
    hp = hp.merge(df[["year", "state", "district", "lean2", "inc"]].rename(columns={"year": "cycle"}), on=["cycle", "state", "district"], how="inner")
    hp["prior"] = ch["const"] + ch["b_lean2"] * hp.lean2 + ch["g_nat"] * hp.cycle.map(gen) + ch["inc"] * hp.inc
    hp["y"] = hp.act - hp.prior; hp["x"] = hp.poll - hp.prior
    for c in ["y", "x"]:
        hp[c + "_d"] = hp[c] - hp.groupby("cycle")[c].transform("mean")
    mp = smf.ols("y_d ~ x_d - 1", hp).fit(cov_type="HC1")
    w = float(mp.params["x_d"])
    sd_prior_used = ch["sd_district"]
    wc = min(max(w, 0.02), 0.98)
    out["district_polls"] = {"n_races": int(len(hp)), "w": w, "w_se": float(mp.bse["x_d"]),
                             "sd_poll_resid": float((hp.act - hp.poll - (hp.act - hp.poll).groupby(hp.cycle).transform("mean")).std()),
                             "implied_poll_sd": float(sd_prior_used * np.sqrt((1 - wc) / wc))}
    print(f"district polls: n={len(hp)} races; weight on polls w={w:.2f} (SE {mp.bse['x_d']:.2f}); "
          f"implied district-poll SD given prior SD {sd_prior_used:.1f}: {out['district_polls']['implied_poll_sd']:.1f} (assumed 7.5)")
    (ROOT / "data/processed/house_structure.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
