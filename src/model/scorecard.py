"""Score the frozen final forecast (data/final/) against 2026 results (data/scorecard/results_*.csv).

Reads only data/final/ and data/scorecard/; writes data/scorecard/scorecard.json. Never touches data/processed/.

Stage 1 (now): winner-based scores, provisional while races are pending.
  - Senate and House: Brier score and log loss per race, for the three published models and the two off-site pocket
    scenarios, on called races; which races each version got wrong; actual vs. expected Brier and upset counts.
  - Seat totals and control: the range the final total can still land in, and where that range sits in each version's
    simulated seat distribution. Not graded as a point until every race is called.
Stage 2 (once vote counts exist): national polling miss, path-to-51 ordering grade, per-layer error diagnostics and
interval coverage. Not written yet.

Contested set: fixed from the frozen forecast alone, before any result is read: races where any of the three published
models gave the Democratic side between 2% and 98%. The same set is used for every version.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "data" / "final"
SC = ROOT / "data" / "scorecard"
PUBLISHED = ["polls_only", "polls_fundamentals", "polls_fundamentals_biasadj"]
POCKET = ["pocket_senate_wide_shift", "pocket_full_historical_bias"]
VERSIONS = PUBLISHED + POCKET
LO, HI = 0.02, 0.98
NSIM = 40000
EPS = 0.5 / NSIM            # probabilities are shares of 40,000 simulations: clip at half a simulation for log loss
MULTI_CANDIDATE = {"MT"}    # as in forecast.py: the D side is the best non-Republican
SENATE_NOT_UP = {"R": 31, "D": 34}


def frozen(chamber, v):
    d = FINAL / "pocket" if v in POCKET else FINAL
    return pd.read_csv(d / f"{chamber}_{v}.csv")


def summary(v):
    d = FINAL / "pocket" if v in POCKET else FINAL
    return json.loads((d / f"summary_{v}.json").read_text())


def outcomes(chamber):
    """Frozen race list with each version's P(D side) and, where called, y = 1 if the D side won."""
    pcol = "p_dside" if chamber == "senate" else "p_dem"
    base = frozen(chamber, "polls_fundamentals")
    keep = ["race_key", "state"] + (["special", "dem", "rep", "dside"] if chamber == "senate"
                                    else ["district", "inc_party", "fixed", "dem_cand", "rep_cand"])
    df = base[keep].copy()
    for v in VERSIONS:
        f = frozen(chamber, v).set_index("race_key")
        df[v] = df.race_key.map(f[pcol])
        df[f"mu_{v}"] = df.race_key.map(f["mu"])
    res = pd.read_csv(SC / f"results_{chamber}.csv").set_index("race_key")
    df["called"] = df.race_key.map(res.called).astype(bool)
    df["winner"] = df.race_key.map(res.winner_name).fillna("")
    df["winner_party"] = df.race_key.map(res.winner_party).fillna("")
    if chamber == "senate":
        y = np.where(df.state.isin(MULTI_CANDIDATE), df.winner_party != "R", df.winner_party == df.dside)
    else:
        y = df.winner_party == "D"
    df["y"] = np.where(df.called, y.astype(float), np.nan)
    pub = df[PUBLISHED]
    df["contested"] = ((pub > LO) & (pub < HI)).any(axis=1)
    if chamber == "house":
        df["contested"] &= df.fixed.isna()
    return df, {k: res[k].iloc[0] for k in ("revision", "page_modified", "snapshot")}


def scores(df, v):
    d = df[df.called]
    p, y = d[v].clip(EPS, 1 - EPS), d.y
    fav_lost = d[(d[v] > 0.5) != (d.y == 1)]
    return {"n": int(len(d)),
            "brier": float(((d[v] - y) ** 2).mean()) if len(d) else None,
            "brier_expected": float((d[v] * (1 - d[v])).mean()) if len(d) else None,   # if the version were calibrated
            "log_loss": float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()) if len(d) else None,
            "upsets": int(len(fav_lost)), "upsets_expected": float(np.minimum(d[v], 1 - d[v]).sum()),
            # direction matters more than the count: a shared national miss shows up as upsets all one way
            "upsets_to_d": int((fav_lost.y == 1).sum()), "upsets_to_r": int((fav_lost.y == 0).sum()),
            "upsets_to_d_expected": float(d.loc[d[v] < 0.5, v].sum()), "upsets_to_r_expected": float((1 - d.loc[d[v] > 0.5, v]).sum()),
            "misses": [{"race": r.race_key, "p_dside": round(float(r[v]), 4), "winner": r.winner,
                        "winner_party": r.winner_party} for _, r in fav_lost.iterrows()]}


def chamber_scores(df):
    out = {}
    for v in VERSIONS:
        out[v] = {"all": scores(df[df.fixed.isna()] if "fixed" in df else df, v), "contested": scores(df[df.contested], v)}
    return out


def seat_range(hist, lo, hi):
    h = np.array(hist, float)
    cdf = np.cumsum(h) / h.sum()
    below = float(cdf[lo - 1]) if lo > 0 else 0.0
    return {"lo": int(lo), "hi": int(hi), "p_at_or_below_hi": float(cdf[hi]), "p_below_lo": below,
            "p_in_range": float(cdf[hi] - below)}


def senate_seats(df):
    nonind = df.dside != "I"
    d_called = int(((df.y == 1) & nonind & df.called).sum())
    r_called = int(((df.y == 0) & df.called & ~(df.winner_party == "I")).sum())
    pend = df[~df.called]
    lo_d = SENATE_NOT_UP["D"] + d_called
    hi_d = lo_d + int((~pend.dside.eq("I")).sum())
    r_lo = SENATE_NOT_UP["R"] + r_called
    ctrl = "D" if lo_d >= 51 else "R" if r_lo >= 50 else None
    out = {"dem_seats_called": lo_d, "dem_seats_max": hi_d, "rep_seats_called": r_lo, "pending": pend.race_key.tolist(),
           "control_decided": ctrl, "versions": {}}
    for v in VERSIONS:
        s = summary(v)["senate"]
        p_ctrl = {"D": s["p_dem_control_without_osborn"], "R": s["p_rep_control"]}
        out["versions"][v] = {"mean": s["dem_seats_mean"], "p10": s["dem_seats_p10"], "p90": s["dem_seats_p90"],
                              "range": seat_range(s["hist"], lo_d, hi_d),
                              "p_control_outcome": p_ctrl.get(ctrl) if ctrl else None,
                              "log_loss_control": float(-np.log(max(p_ctrl[ctrl], EPS))) if ctrl else None}
    return out


def house_seats(df):
    # seats the forecast already treated as decided (one party on the ballot, or called before Nov 3) count as decided
    # even before Wikipedia ticks them
    fixed_d = ~df.called & df.fixed.eq("D")
    fixed_r = ~df.called & df.fixed.eq("R")
    d_called = int((df.called & (df.y == 1)).sum() + fixed_d.sum())
    r_called = int((df.called & (df.winner_party == "R")).sum() + fixed_r.sum())
    pend = df[~df.called & ~fixed_d & ~fixed_r]
    ctrl = "D" if d_called >= 218 else "R" if r_called >= 218 else None
    out = {"dem_seats_called": d_called, "rep_seats_called": r_called, "n_pending": int(len(pend)),
           "n_pending_contested": int(pend.contested.sum()), "control_decided": ctrl, "versions": {}}
    for v in VERSIONS:
        s = summary(v)["house"]
        p_ctrl = {"D": s["p_dem_majority"], "R": s["p_rep_majority"]}
        out["versions"][v] = {"mean": s["dem_seats_mean"], "p10": s["dem_seats_p10"], "p90": s["dem_seats_p90"],
                              "range": seat_range(s["hist"], d_called, d_called + len(pend)),
                              "p_control_outcome": p_ctrl.get(ctrl) if ctrl else None}
    return out


def races_table(df, chamber):
    cols = ["race_key", "contested", "called", "winner", "winner_party", "y"] + VERSIONS
    return json.loads(df[cols].to_json(orient="records"))


def main():
    sen, prov_s = outcomes("senate")
    hou, prov_h = outcomes("house")
    out = {"stage": "winners only (provisional: races are still being called and counted)",
           "sources": {"senate": prov_s, "house": prov_h},
           "contested_rule": f"any published model gave the D side between {LO:.0%} and {HI:.0%} (fixed from data/final/)",
           "senate": {"scores": chamber_scores(sen), "seats": senate_seats(sen), "races": races_table(sen, "senate")},
           "house": {"scores": chamber_scores(hou), "seats": house_seats(hou), "races": races_table(hou, "house")}}
    (SC / "scorecard.json").write_text(json.dumps(out, indent=1, default=float))
    report(out, sen, hou)


def report(out, sen, hou):
    for ch, df in (("senate", sen), ("house", hou)):
        c = out[ch]
        n_cont = int(df.contested.sum())
        print(f"\n===== {ch.upper()}  ({int(df.called.sum())} of {len(df)} called; contested {int((df.contested & df.called).sum())} of {n_cont} called)")
        print(f"{'version':30s} {'set':10s} {'n':>4s} {'Brier':>7s} {'(exp.)':>7s} {'logloss':>8s} {'upsets':>7s} {'(exp.)':>7s}"
              f" {'->D':>4s} {'(exp.)':>7s} {'->R':>4s} {'(exp.)':>7s}")
        for v in VERSIONS:
            for k in ("contested", "all"):
                s = c["scores"][v][k]
                if s["n"]:
                    print(f"{v:30s} {k:10s} {s['n']:4d} {s['brier']:7.4f} {s['brier_expected']:7.4f} {s['log_loss']:8.4f} "
                          f"{s['upsets']:7d} {s['upsets_expected']:7.2f} {s['upsets_to_d']:4d} {s['upsets_to_d_expected']:7.2f}"
                          f" {s['upsets_to_r']:4d} {s['upsets_to_r_expected']:7.2f}")
        for v in PUBLISHED:
            ms = c["scores"][v]["contested"]["misses"]
            print(f"  misses {v}: " + (", ".join(f"{m['race'].split('|')[1]}{'-' + m['race'].split('|')[3] if ch == 'house' else ''}"
                                                 f" (p {m['p_dside']:.2f}, {m['winner_party']} won)" for m in ms) or "none"))
        seats = c["seats"]
        print(f"  seats: {json.dumps({k: v for k, v in seats.items() if k != 'versions'})}")
        for v, s in seats["versions"].items():
            r = s["range"]
            print(f"   {v:30s} mean {s['mean']:.1f} (80% {s['p10']:.0f}-{s['p90']:.0f})  final total in [{r['lo']}, {r['hi']}]: "
                  f"P(in range) {r['p_in_range']:.3f}, P(below {r['lo']}) {r['p_below_lo']:.3f}; P(outcome control) {s['p_control_outcome']}")


if __name__ == "__main__":
    main()
