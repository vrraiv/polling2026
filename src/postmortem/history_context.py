"""Historical data exploration: how unusual was 2026, and how are the chambers' errors linked?

  1. Midterms ranked by the president's party's two-party House margin (1946-2022, data/interim/fundamentals_dataset.csv),
     with approval and the change from the previous election; 2026's inputs against the fundamentals training range.
  2. Chamber coupling: the cycle-level Senate polling miss against the generic-ballot miss (data/final/calibration.json,
     1998-2022), with the ratio the frozen model assumed.
  3. Approval and the president's party: the Senate polling miss toward the president's party by cycle
     (data/final/bias_race_level.csv, 2002-2022), and House incumbency premiums for president's-party vs out-party
     incumbents by cycle (data/interim/house_history.csv, 2006-2024).

    python src/postmortem/history_context.py

Writes data/postmortem/history_context.json.
"""
import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

import frozen as F

PRES_EXTRA = {2024: "D"}       # fundamentals_dataset.csv ends at 2022


def midterms():
    d = pd.read_csv(F.INTERIM / "fundamentals_dataset.csv")
    m = d[d.midterm.astype(bool)].copy()
    m["change_vs_prev"] = m.outcome - m.prev
    fund = json.loads((F.FINAL / "fundamentals.json").read_text())["midterms_1962_2022"]
    nat = F.scorecard()["margins"]["national"]
    return {"midterms": m[["year", "pres_party", "approval", "prev", "outcome", "change_vs_prev"]].sort_values("outcome").round(2).to_dict("records"),
            "training_years": fund["years"], "range_check_2026": fund["range_check"],
            "pred_2026_pres_party": fund["pred_2026_pres_party"],
            "realized_2026_partial": {k: nat.get(k) for k in ("house_vote_margin", "ready", "districts_with_counts", "of")}}


def coupling():
    cal = json.loads((F.FINAL / "calibration.json").read_text())
    h = {c["cycle"]: c["mean"] for c in cal["House-G-US"]["cycles"]}
    s = {c["cycle"]: c["mean"] for c in cal["Sen-G"]["cycles"]}
    yrs = sorted(set(h) & set(s))
    H, S = np.array([h[y] for y in yrs]), np.array([s[y] for y in yrs])
    out = {"cycles": [{"cycle": y, "generic_miss": h[y], "senate_miss": s[y]} for y in yrs]}
    for lab, k in (("all", np.ones(len(yrs), bool)), ("midterms", np.array([y % 4 == 2 for y in yrs]))):
        r = float(np.corrcoef(H[k], S[k])[0, 1])
        n = int(k.sum())
        zr, se = np.arctanh(r), 1 / np.sqrt(n - 3)
        out[lab] = {"n": n, "corr": r, "corr_95ci": [float(np.tanh(zr - 1.96 * se)), float(np.tanh(zr + 1.96 * se))],
                    "slope_senate_on_generic": float(np.polyfit(H[k], S[k], 1)[0])}
    out["model_assumed"] = {v: {"corr": 1.0, "senate_per_point_of_house_env": F.national(v)["sd_nat_senate_used"] / F.national(v)["sd_nat_house_used"]}
                            for v in F.VERSIONS}
    return out


def approval_effects():
    f = pd.read_csv(F.INTERIM / "fundamentals_dataset.csv").set_index("year")
    pres = {**f.pres_party.to_dict(), **PRES_EXTRA}
    cal = json.loads((F.FINAL / "calibration.json").read_text())
    gen = {c["cycle"]: c["mean"] for c in cal["House-G-US"]["cycles"]}
    b = pd.read_csv(F.FINAL / "bias_race_level.csv")
    b = b[b.type_simple == "Sen-G"]
    cyc = b.groupby("cycle").agg(n=("err_pres", "size"), senate_miss_toward_pres=("err_pres", "mean"), midterm=("midterm", "first")).reset_index()
    cyc["approval"] = cyc.cycle.map(f.approval)
    cyc["generic_miss_toward_pres"] = cyc.cycle.map(gen) * cyc.cycle.map(pres).map({"D": 1, "R": -1})
    sen = {"cycles": cyc.round(2).to_dict("records")}
    for lab, k in (("all", cyc.index == cyc.index), ("midterms", cyc.midterm == 1)):
        d = cyc[k]
        sen[lab] = {"n": len(d), "corr_approval_vs_senate_miss": float(np.corrcoef(d.approval, d.senate_miss_toward_pres)[0, 1]),
                    "corr_approval_vs_senate_minus_generic": float(np.corrcoef(d.approval, d.senate_miss_toward_pres - d.generic_miss_toward_pres)[0, 1])}
    hh = pd.read_csv(F.INTERIM / "house_history.csv")
    hh = hh[hh.contested].copy()
    hh["pres"] = hh.year.map(pres)
    hh["inc_pres"] = ((hh.inc_party == hh.pres) & hh.inc_ran).astype(int)
    hh["inc_out"] = ((hh.inc_party != hh.pres) & hh.inc_party.isin(["D", "R"]) & hh.inc_ran).astype(int)
    sgn = hh.pres.map({"D": 1, "R": -1})
    hh["m_pres"], hh["lean_pres"] = hh.margin * sgn, hh.lean2 * sgn
    rows = []
    for y, d in hh.groupby("year"):
        fit = smf.ols("m_pres ~ lean_pres + inc_pres + inc_out", d).fit()
        rows.append({"year": int(y), "midterm": bool(y % 4 == 2), "approval": f.approval.get(y, np.nan), "n": len(d),
                     "inc_premium_pres_party": fit.params.inc_pres, "inc_premium_out_party": -fit.params.inc_out,
                     "gap": fit.params.inc_pres + fit.params.inc_out, "gap_se": float(np.hypot(fit.bse.inc_pres, fit.bse.inc_out))})
    t = pd.DataFrame(rows)
    mid = t[t.midterm]
    return {"senate": sen, "house_incumbency": {"cycles": t.round(2).to_dict("records"),
            "midterms_corr_approval_vs_gap": float(np.corrcoef(mid.approval, mid.gap)[0, 1]), "n_midterms": len(mid),
            "note": "every 2006-2022 midterm had approval 38.9-44.9: no popular-president midterm in this data"}}


def main():
    out = {"question": "How unusual was 2026, and how are Senate and House errors linked historically?",
           "extreme_environment": midterms(), "chamber_coupling": coupling(), "approval_effects": approval_effects()}
    F.write("history_context.json", out)
    print(pd.DataFrame(out["extreme_environment"]["midterms"]).head(10).to_string(index=False))
    print({k: out["chamber_coupling"][k] for k in ("all", "midterms", "model_assumed")})
    print({k: out["approval_effects"]["senate"][k] for k in ("all", "midterms")})
    print(pd.DataFrame(out["approval_effects"]["house_incumbency"]["cycles"]).to_string(index=False))


if __name__ == "__main__":
    main()
