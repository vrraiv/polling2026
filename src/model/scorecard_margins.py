"""Stage 2 of the scorecard: everything that needs vote margins (data/scorecard/margins_*.csv).

Called from scorecard.py with the race tables it built from data/final/. Each block reports how many races it used, so a
partial count is visible rather than silently scored.

  errors      actual margin minus each version's expected margin (mu): mean (the realized shared miss), RMSE, MAE.
  national    House popular vote (sum of district boxes) vs. the generic-ballot average the forecast used (G_polls),
              i.e. this year's polling miss vs. the shift the bias-adjusted model assumed; each version's G vs. actual.
  ordering    path-to-51: Kendall tau-b between forecast mu and the actual margin (all Senate races, and the contested
              set), share of pairs in the right order, PVI-only and Cook-rating baselines, rank displacement, and which race
              actually delivered the 51st Democratic seat with the forecast's tipping-point probability for it.
  layers      the simulation's error layers, peeled off in the model's order: national miss per chamber (as a z-score
              against the national SD used), Census-region shocks (vs. sigma_region), the polarization slope on lean
              (vs. its SD, and vs. the bias-adjusted model's lean correction), then race-level coverage of the central
              50/80/95% intervals with the realized national miss removed, under t(df used), t(6) and normal.
Ratings/PVI baselines and all intervals come from data/final/ only.
"""
import json

import numpy as np
import pandas as pd
from scipy import stats

from scorecard import FINAL, PUBLISHED, SC, SENATE_NOT_UP, VERSIONS, summary

PS = json.loads((FINAL / "poll_settings.json").read_text())["chosen"]
DF_T = float(PS["df_t"])
ES = json.loads((FINAL / "error_structure.json").read_text())
STATE_REGION = {st: r for r, sts in ES["regions"].items() for st in sts}
SIGMA_REGION = float(ES["sigma_region"])
SIGMA_SLOPE = float(ES["lean_slope"]["all"]["sd_true"])
H_G_NAT = float(json.loads((FINAL / "house_structure.json").read_text())["chosen"]["g_nat"])
LEAN_CORRECTION = float(json.loads((FINAL / "bias_analysis.json").read_text())["state"]["post2010_symmetric"]["slope"])
COOK = {"Solid D": 3, "Safe D": 3, "Likely D": 2, "Lean D": 1, "Tilt D": 0.5, "Toss-up": 0, "Tossup": 0, "Tilt R": -0.5,
        "Lean R": -1, "Likely R": -2, "Solid R": -3, "Safe R": -3}
REF = "polls_fundamentals"   # the version whose residuals are used for the layer diagnostics (layers are shared)


def add_margins(df, chamber):
    m = pd.read_csv(SC / f"margins_{chamber}.csv").drop_duplicates("race_key").set_index("race_key")
    df = df.copy()
    # scores use settled counts only (total moved <1% since the previous day's snapshot); counts still moving are shown
    # on the page as "counting" but not scored
    df["counted"] = df.race_key.map(m.margin)
    df["settled"] = df.race_key.map(m.settled).fillna(False).astype(bool) if "settled" in m else False
    df["actual"] = df.counted.where(df.settled)
    df["source"] = df.race_key.map(m.source) if "source" in m else "wikipedia"
    df["margin_issues"] = df.race_key.map(m.issues).fillna("")
    df["region"] = df.state.map(STATE_REGION)
    df["lean"] = 2.0 * df.pvi
    has = df.actual.notna() & df.called
    df["sign_mismatch"] = has & ((df.actual > 0) != (df.y == 1))
    return df, m


def errors(df):
    out = {}
    for v in VERSIONS:
        out[v] = {}
        for k, sel in (("contested", df.contested), ("all", df.actual.notna())):
            d = df[sel & df.actual.notna()]
            e = d.actual - d[f"mu_{v}"]
            out[v][k] = {"n": int(len(d)), "mean": float(e.mean()) if len(d) else None,
                         "rmse": float(np.sqrt((e ** 2).mean())) if len(d) else None, "mae": float(e.abs().mean()) if len(d) else None}
    return out


def national(hm):
    """House popular vote from the district boxes with counts, vs. each version's national environment."""
    d = hm[(hm.d_votes_all + hm.r_votes_all) > 0]
    D, R = float(d.d_votes_all.sum()), float(d.r_votes_all.sum())
    actual = 100 * (D - R) / (D + R) if D + R else None
    stable = int(d.count_stable.fillna(False).astype(bool).sum()) if "count_stable" in d else 0
    out = {"districts_with_counts": int(len(d)), "districts_count_stable": stable, "of": 435,
           # shown on the page once at least 380 districts report votes and 95% of those have stable counts (uncontested
           # races left off the ballot and the slow counters keep it below 435 for a while)
           "ready": bool(len(d) >= 380 and stable >= 0.95 * len(d)),
           "dem_votes": D, "rep_votes": R, "house_vote_margin": actual,
           "note": "sum of reported district votes; uncontested races not on the ballot add nothing (as in the calibration's "
                   "national House vote)", "versions": {}}
    for v in VERSIONS:
        n = summary(v)["national"]
        out["versions"][v] = {"G_polls": n["G_polls"], "G_used": n["G_used"], "bias_shift_assumed": n.get("bias_shift", 0.0),
                              "polling_miss": None if actual is None else actual - n["G_polls"],
                              "G_error": None if actual is None else actual - n["G_used"]}
    return out


def pair_share(f, a):
    """Share of race pairs whose order the forecast got right (ties in the forecast count half)."""
    f, a = np.asarray(f, float), np.asarray(a, float)
    i, j = np.triu_indices(len(f), 1)
    da, df_ = np.sign(a[i] - a[j]), np.sign(f[i] - f[j])
    keep = da != 0
    if not keep.any():
        return None
    return float(((df_[keep] == da[keep]) + 0.5 * (df_[keep] == 0)).mean())


def ordering(sen):
    d_all = sen[sen.actual.notna()].copy()
    d_all["cook"] = d_all.rating_cook.map(COOK)
    out = {"n_with_margins": int(len(d_all)), "of": int(len(sen)), "pending": sen.loc[sen.actual.isna(), "race_key"].tolist()}
    for k, d in (("all", d_all), ("contested", d_all[d_all.contested])):
        blk = {"n": int(len(d))}
        if len(d) >= 3:
            for v in VERSIONS:
                blk[v] = {"tau_b": float(stats.kendalltau(d[f"mu_{v}"], d.actual).statistic),
                          "pairs_right": pair_share(d[f"mu_{v}"], d.actual)}
            blk["baseline_pvi"] = {"tau_b": float(stats.kendalltau(d.lean, d.actual).statistic), "pairs_right": pair_share(d.lean, d.actual)}
            c = d[d.cook.notna()]
            blk["baseline_cook"] = {"n": int(len(c)), "tau_b": float(stats.kendalltau(c.cook, c.actual).statistic),
                                    "pairs_right": pair_share(c.cook, c.actual)}
        out[k] = blk
    # rank displacement (contested set, reference version)
    d = d_all[d_all.contested].copy()
    d["rank_forecast"] = d[f"mu_{REF}"].rank(ascending=False, method="min").astype(int)
    d["rank_actual"] = d.actual.rank(ascending=False, method="min").astype(int)
    d["displacement"] = d.rank_actual - d.rank_forecast
    out["ranks"] = [{"race": r.race_key, "mu": round(float(r[f"mu_{REF}"]), 2), "actual": round(float(r.actual), 2),
                     "rank_forecast": int(r.rank_forecast), "rank_actual": int(r.rank_actual), "displacement": int(r.displacement)}
                    for _, r in d.sort_values("rank_actual").iterrows()]
    out["mean_abs_displacement"] = float(d.displacement.abs().mean()) if len(d) else None
    # the race that actually delivered the 51st Democratic seat (independents left out, as in the headline count)
    nonind = sen[sen.dside != "I"]
    need = 51 - SENATE_NOT_UP["D"]
    out["tipping_point"] = None
    if nonind.actual.notna().all():
        tp = nonind.sort_values("actual", ascending=False).iloc[need - 1]
        key = tp.state + ("-sp" if tp.special else "")
        out["tipping_point"] = {"race": tp.race_key, "actual": float(tp.actual), "versions": {}}
        for v in VERSIONS:
            ladder = {r["race"]: r for r in summary(v)["senate"]["reading"]["ladder"]}
            order = nonind.sort_values(f"mu_{v}", ascending=False).race_key.tolist()
            out["tipping_point"]["versions"][v] = {"p_tipping_point": ladder.get(key, {}).get("tp"),
                                                   "forecast_position": order.index(tp.race_key) + 1, "needed_position": need}
    else:
        out["tipping_point_pending"] = nonind.loc[nonind.actual.isna(), "race_key"].tolist()
    return out


def layers(sen, hou):
    out = {"reference_version": REF, "df_t_used": DF_T}
    rows = []
    for ch, df in (("senate", sen), ("house", hou)):
        d = df[df.contested & df.actual.notna()].copy()
        d["err"] = d.actual - d[f"mu_{REF}"]
        nat = summary(REF)["national"]
        sd_nat = nat["sd_nat_senate_used"] if ch == "senate" else H_G_NAT * nat["sd_nat_house_used"]
        miss = float(d.err.mean()) if len(d) else None
        out[f"national_{ch}"] = {"n": int(len(d)), "miss": miss, "sd_assumed": float(sd_nat),
                                 "z": None if miss is None else miss / sd_nat}
        d["resid"] = d.err - (miss or 0.0)
        d["chamber"] = ch
        d["sd"] = d[f"sd_{REF}"]
        rows.append(d[["race_key", "chamber", "region", "lean", "resid", "sd"]])
    r = pd.concat(rows)
    out["n_races"] = int(len(r))
    if len(r) < 10:
        return out
    # region shocks: mean residual by region (both chambers share the shock), vs. sigma_region
    reg = {}
    for g, x in r.groupby("region"):
        se = float(x.resid.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan
        reg[g] = {"n": int(len(x)), "mean": float(x.resid.mean()), "se": se,
                  "z": float(x.resid.mean() / np.sqrt(SIGMA_REGION ** 2 + se ** 2)) if np.isfinite(se) else None}
    out["region"] = {"sigma_assumed": SIGMA_REGION, "by_region": reg}
    # polarization slope on lean, pooled and per chamber
    sl = {}
    for lab, x in (("pooled", r), ("senate", r[r.chamber == "senate"]), ("house", r[r.chamber == "house"])):
        if len(x) >= 5 and x.lean.std() > 0:
            res = stats.linregress(x.lean, x.resid)
            sl[lab] = {"n": int(len(x)), "slope": float(res.slope), "se": float(res.stderr),
                       "z_vs_assumed_sd": float(res.slope / np.sqrt(SIGMA_SLOPE ** 2 + res.stderr ** 2))}
    out["slope"] = {"sd_assumed": SIGMA_SLOPE, "bias_adjusted_lean_correction": LEAN_CORRECTION, **sl}
    # race-level coverage with the realized national miss removed
    cov = {}
    for lab, dist in (("t_used", ("t", DF_T)), ("t6", ("t", 6.0)), ("normal", ("n", None))):
        c = {}
        for level in (0.5, 0.8, 0.95):
            q = 1 - (1 - level) / 2
            if dist[0] == "t":
                hw = stats.t.ppf(q, dist[1]) * r.sd * np.sqrt((dist[1] - 2) / dist[1])
            else:
                hw = stats.norm.ppf(q) * r.sd
            c[f"{int(level * 100)}"] = float((r.resid.abs() <= hw).mean())
        cov[lab] = c
    out["coverage"] = {"n": int(len(r)), "expected": {"50": 0.5, "80": 0.8, "95": 0.95}, **cov,
                       "by_chamber_t_used": {ch: float((x.resid.abs() <= stats.t.ppf(0.9, DF_T) * x.sd * np.sqrt((DF_T - 2) / DF_T)).mean())
                                             for ch, x in r.groupby("chamber")},
                       "note": "share of races whose error, after removing the chamber's realized national miss, falls inside "
                               "the central interval of the race-level error (region, slope and race-specific layers)"}
    return out


def poll_audit_scores(sen, hou):
    """Error of the poll audit's what-if expected margins (polls + fundamentals) against settled results: would a
    second poll source have helped? Over audited races with a settled count."""
    path = SC / "poll_audit.json"
    if not path.exists():
        return None
    A = json.loads(path.read_text())
    out = {}
    for ch, df in (("senate", sen), ("house", hou)):
        if ch not in A:
            continue
        act = df.set_index("race_key").actual
        rows = []
        for r in A[ch]["races"]:
            a = act.get(r["race_key"])
            if a is None or pd.isna(a):
                continue
            rows.append({k: r["what_if"][k]["polls_fundamentals"]["mu"] - a for k in r["what_if"]})
        if not rows:
            continue
        e = pd.DataFrame(rows)
        out[ch] = {"n": int(len(e)), **{k: {"rmse": float(np.sqrt((e[k] ** 2).mean())), "mean": float(-e[k].mean())} for k in e}}
    return out or None


def early_read(sen):
    """The Senate polling miss from the latest counts, settled or not: published as an early read, never scored. Miss =
    count minus the forecast's final poll average (polls-only version's average, before any adjustment), over races
    with at least two polls; the forecast's expected-margin errors alongside."""
    po = pd.read_csv(FINAL / "senate_polls_only.csv").set_index("race_key")
    off = pd.read_csv(SC / "official_senate.csv").set_index("race_key") if (SC / "official_senate.csv").exists() else None
    rows = []
    for _, r in sen.iterrows():
        if pd.isna(r.counted) or not r.contested:   # the scorecard's fixed close-race set
            continue
        k, p = r.race_key, po.loc[r.race_key]
        n = int(p.n_polls)
        o = off.loc[k] if off is not None and k in off.index and off.loc[k, "status"] == "ok" else None
        status = (("official, complete" if bool(o["complete"]) else f"official, still counting ({o['reporting']})") if o is not None
                  else "Wikipedia count")
        pa = float(p.poll_avg_raw) if n and pd.notna(p.poll_avg_raw) else None
        rows.append({"race": k, "count": round(float(r.counted), 2), "settled": bool(r.settled), "status": status,
                     "poll_avg": None if pa is None else round(pa, 2), "n_polls": n,
                     "miss_vs_polls": None if pa is None else round(float(r.counted) - pa, 2),
                     **{f"mu_{v}": round(float(r[f"mu_{v}"]), 2) for v in PUBLISHED}})
    polled = [x for x in rows if x["n_polls"] >= 2]
    miss = np.array([x["miss_vs_polls"] for x in polled], float)
    out = {"races": rows, "n_polled": len(polled),
           "note": "counts as of the latest run, most not final; shown, not scored"}
    if len(polled):
        out.update(mean_miss=float(miss.mean()), median_miss=float(np.median(miss)),
                   mean_error_vs_mu={v: float(np.mean([x["count"] - x[f"mu_{v}"] for x in polled])) for v in PUBLISHED})
    return out


def margin_row(r):
    rnd = lambda x: None if pd.isna(x) else round(float(x), 2)
    return {"race": r.race_key, "actual": rnd(r.actual), "counted": rnd(r.counted), "settled": bool(r.settled),
            "source": r.source if isinstance(r.source, str) else None, **{f"mu_{v}": rnd(r[f"mu_{v}"]) for v in PUBLISHED}}


def stage2(sen, hou):
    sen, sm = add_margins(sen, "senate")
    hou, hm = add_margins(hou, "house")
    out = {"sources": {"senate_pages": sm[["revision", "page_modified"]].dropna().astype(str).drop_duplicates().to_dict("records")[:3],
                       "n_pages_senate": int(sm.revision.nunique()), "n_pages_house": int(hm.revision.nunique())},
           "completeness": {"senate": {"counted": int(sen.counted.notna().sum()), "settled": int(sen.actual.notna().sum()),
                                       "of": int(len(sen))},
                            "house_contested": {"counted": int((hou.contested & hou.counted.notna()).sum()),
                                                "settled": int((hou.contested & hou.actual.notna()).sum()), "of": int(hou.contested.sum())},
                            "house_all": {"counted": int(hou.counted.notna().sum()), "settled": int(hou.actual.notna().sum()), "of": int(len(hou))},
                            "rule": "scores use settled counts: candidate votes moved less than 1% since the previous day's "
                                    "snapshot, the source was updated in between (page edited or report re-issued), and "
                                    "nothing moved the way a count in progress can't (votes falling, a swing with no new votes); in states that "
                                    "count mail ballots for weeks (CA, WA, OR, NV, AZ, UT, AK) the count must also have held "
                                    "still for 7 days"},
           "sign_mismatches": sen.loc[sen.sign_mismatch, "race_key"].tolist() + hou.loc[hou.sign_mismatch, "race_key"].tolist(),
           "box_issues": {r.race_key: r.issues for _, r in pd.concat([sm.reset_index(), hm.reset_index()])
                          .loc[lambda x: x.issues.fillna("") != ""].iterrows()},
           "errors": {"senate": errors(sen), "house": errors(hou[hou.fixed.isna()])},
           "national": national(hm),
           "ordering": ordering(sen),
           "layers": layers(sen, hou),
           "poll_audit_scores": poll_audit_scores(sen, hou),
           "early_read": early_read(sen),
           "senate_margins": [margin_row(r) for _, r in sen.iterrows()],
           "house_margins": [margin_row(r) for _, r in hou[hou.contested].iterrows()]}
    return out


def report(m):
    print("\n===== MARGINS (stage 2)")
    print("completeness:", json.dumps(m["completeness"]), "| sign mismatches:", m["sign_mismatches"] or "none")
    if m["box_issues"]:
        print("box issues:", m["box_issues"])
    for ch in ("senate", "house"):
        for v in VERSIONS:
            e = m["errors"][ch][v]["contested"]
            if e["n"]:
                print(f"  {ch:6s} {v:30s} contested n={e['n']:3d} mean err {e['mean']:+.2f}  RMSE {e['rmse']:.2f}  MAE {e['mae']:.2f}")
    n = m["national"]
    print(f"national: {n['districts_with_counts']}/435 districts with counts; House vote margin {n['house_vote_margin']}")
    for v, x in n["versions"].items():
        print(f"   {v:30s} G_polls {x['G_polls']:+.2f} G_used {x['G_used']:+.2f} assumed shift {x['bias_shift_assumed']:+.2f} "
              f"polling miss {x['polling_miss']} G error {x['G_error']}")
    o = m["ordering"]
    print(f"ordering: {o['n_with_margins']}/{o['of']} Senate races with margins; pending {o['pending']}")
    for k in ("all", "contested"):
        b = o[k]
        if "baseline_pvi" in b:
            print(f"   {k:9s} n={b['n']:2d} " + "  ".join(f"{v.replace('polls_', '')[:14]} tau {b[v]['tau_b']:.2f}/{b[v]['pairs_right']:.0%}" for v in PUBLISHED)
                  + f"  | PVI tau {b['baseline_pvi']['tau_b']:.2f}/{b['baseline_pvi']['pairs_right']:.0%}  Cook tau {b['baseline_cook']['tau_b']:.2f}/{b['baseline_cook']['pairs_right']:.0%}")
    print("   tipping point:", o.get("tipping_point") or ("pending " + str(o.get("tipping_point_pending"))))
    L = m["layers"]
    print("layers:", {k: L[k] for k in ("national_senate", "national_house")})
    for k in ("region", "slope", "coverage"):
        if k in L:
            print(f"   {k}: {json.dumps(L[k], default=lambda x: round(x, 3))[:600]}")
