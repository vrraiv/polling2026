"""2026 House + Senate forecast: polls-only and polls+fundamentals.

Conventions
- All margins are two-party D-R margins in points (positive = Democratic).
- PVI is Cook-style (two-party share vs. national), from Wikipedia's 2026 tables, on 2026 district lines.
- Expected race margin prior: 2*PVI + national House environment G + incumbency.
- Uncertainty: one shared national error (fat-tailed, t5) for every race + race-specific error (t5).
  Scales come from 538 raw_polls.csv calibration (src/model/calibrate.py).

Run:  python src/model/forecast.py
"""
import json
import re
import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "collect"))
from common import ROOT, latest  # noqa: E402
import pollavg as P  # noqa: E402
from wiki import STATE_ABBR  # noqa: E402

OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)
ABBR_STATE = {v: k for k, v in STATE_ABBR.items()}
RNG = np.random.default_rng(2026)
NSIM = 40000
DF_T = 5  # t-distribution degrees of freedom (fat tails)

# ---------------- parameters ----------------
CAL = json.loads((OUT / "calibration.json").read_text())
GEN_CYC = [c["mean"] for c in CAL["House-G-US"]["cycles"]]
SEN_CYC = [c["mean"] for c in CAL["Sen-G"]["cycles"] if c["cycle"] % 2 == 0]
SD_NAT_GENERIC = float(np.sqrt(np.mean(np.square(GEN_CYC))))   # RMSE of final generic-ballot avg vs result (incl. bias)
GENERIC_BIAS = float(np.mean(GEN_CYC))  # raw-margin mean 1998-2022 (fallback only)
# Two-party, decay-weighted estimate of the final generic-ballot miss (src/model/bias_decay.py): about -3.0 pts
# (negative = polls overstated Democrats). Predictive SD about 2.6.
_BD = OUT / "bias_decay.json"
if _BD.exists():
    GENERIC_BIAS = float(json.loads(_BD.read_text())["top10_avg_pred_2026"])
LV_DISCOUNT = 1.0   # the 2026 aggregators adjust to likely voters; LV polls ran ~1-1.5 pts less Democratic than RV in 2020/2022
BIAS_ADJ = GENERIC_BIAS + LV_DISCOUNT   # about -2.0: the shift used by the "bias-adjusted" model
SD_NAT_SENATE = float(np.sqrt(np.mean(np.square(SEN_CYC))))     # shared Senate polling miss per cycle
SD_RACE_POLLAVG = CAL["Sen-G"]["race_resid_sd_midterms"]        # race-level error of a final poll average
SD_SENATE_PRIOR = 10.0    # race error of 2*PVI + G + incumbency prior (assumed; candidate effects are large, e.g. ME 2020 missed by ~20)
MULTI_CANDIDATE = {"MT"}   # genuine 3-way races: use raw (best non-R minus R) poll margin, no PVI prior
SD_HOUSE_DISTRICT = 6.0   # district error around 2*PVI + G + incumbency (assumed, typical of district models)
SD_HOUSE_POLL = 7.5       # district polls: mostly sparse/internal, so noisy (assumed)
INC_HOUSE = 2.5           # incumbency bonus, margin points (assumed)
INC_SENATE = 2.0
T_SCALE = np.sqrt((DF_T - 2) / DF_T)  # so scaled t has the stated SD

# Fundamentals (ASSUMED coefficients, not estimated here: two midterms can't identify them and keyless
# historical approval data wasn't available). President's-party House margin in a midterm:
#   F = A + B*(approval - 45) + C*(real disposable income per capita growth yoy - 1.5)
FUND = {"A": -4.0, "B": 0.6, "C": 0.5, "SD": 5.5}
# State-lean poll correction (src/model/bias_analysis.py): since 2010, final poll averages have understated
# state partisanship -- results land further toward the state's lean. Slope per point of lean margin (2*PVI),
# pooled over 2010-2022 Senate+Gov races; improved held-out accuracy in a real-time backtest.
_BIAS = ROOT / "data/processed/bias_analysis.json"
LEAN_SLOPE = json.loads(_BIAS.read_text())["state"]["post2010_symmetric"]["slope"] if _BIAS.exists() else 0.0
APPLY_LEAN_CORRECTION = False  # off for the first published build; see bias_analysis.py
STATE_ECON_COEF = 0.5     # Senate: D gain per point that state unemployment rose more than national (12m)


def tdraw(size):
    return RNG.standard_t(DF_T, size=size) * T_SCALE


def pct(s):
    return float(str(s).replace("%", "").replace("−", "-").strip())


# ---------------- national inputs ----------------
def national_inputs():
    polls = P.load_votehub()
    hhtml = latest("wikipedia", "2026_United_States_House_of_Representatives_elections.html").read_text(encoding="utf-8")
    agg = next(t for t in pd.read_html(StringIO(hhtml)) if "Source of poll aggregation" in [str(c) for c in t.columns])
    agg = agg[agg["Source of poll aggregation"].astype(str).str.contains(r"\[", regex=True)]  # the named aggregators
    agg = agg.assign(D=agg.Democrats.map(pct), R=agg.Republicans.map(pct))
    agg["two_party"] = 100 * (agg.D - agg.R) / (agg.D + agg.R)
    g_agg = float(agg.two_party.mean())
    g_vh = P.generic_ballot(P.load_votehub())

    ahtml = latest("wikipedia", "Opinion_polling_on_the_second_Trump_presidency.html").read_text(encoding="utf-8")
    at = next(t for t in pd.read_html(StringIO(ahtml)) if "Aggregator" in t.columns and "Approve" in t.columns)
    at = at[~at.Aggregator.astype(str).str.contains("average", case=False)]  # drop Wikipedia's own "Average" row
    approval = float(at.Approve.map(pct).mean())

    def series(name, src="fred"):
        f = sorted((ROOT / "data" / "raw" / src).glob(f"*/{name}.csv"))[-1]
        d = pd.read_csv(f)
        d.columns = ["date", "v"]
        d["v"] = pd.to_numeric(d.v, errors="coerce")
        d["date"] = pd.to_datetime(d.date)
        return d.dropna().set_index("date").v

    rdi = series("A229RX0")
    rdi_g = 100 * (rdi.iloc[-1] / rdi.iloc[-13] - 1)
    u = series("UNRATE")
    cpi = series("CPIAUCSL")
    econ = {"rdi_pc_growth_yoy": rdi_g, "unemployment": float(u.iloc[-1]), "unemp_chg_12m": float(u.iloc[-1] - u.iloc[-13]),
            "cpi_yoy": float(100 * (cpi.iloc[-1] / cpi.iloc[-13] - 1)), "econ_asof": str(u.index[-1].date())}
    # President is a Republican -> president's-party margin F is R-D; convert to D-R
    F_pres = FUND["A"] + FUND["B"] * (approval - 45) + FUND["C"] * (rdi_g - 1.5)
    F = -F_pres
    w = (1 / SD_NAT_GENERIC ** 2) / (1 / SD_NAT_GENERIC ** 2 + 1 / FUND["SD"] ** 2)
    G_fund = w * g_agg + (1 - w) * F
    sd_fund = 1 / np.sqrt(1 / SD_NAT_GENERIC ** 2 + 1 / FUND["SD"] ** 2)
    nat = {"generic_aggregators": agg[["Source of poll aggregation", "D", "R", "two_party"]].round(2).to_dict("records"),
           "G_polls": g_agg, "G_votehub_own_avg": g_vh, "approval": approval,
           "approval_aggregators": at[["Aggregator", "Approve"]].to_dict("records"),
           "econ": econ, "fundamentals_margin_D": F, "fund_weight_on_polls": w, "G_fund": G_fund,
           "sd_nat_polls": SD_NAT_GENERIC, "sd_nat_fund": sd_fund, "generic_hist_bias": GENERIC_BIAS,
           "sd_nat_senate": SD_NAT_SENATE, "sd_race_pollavg": SD_RACE_POLLAVG}
    return nat, polls


# ---------------- state economics ----------------
def state_unemp_change():
    out = {}
    nat = None
    for st in STATE_ABBR.values():
        fs = sorted((ROOT / "data/raw/fred_state").glob(f"*/{st}UR.csv"))
        if not fs:
            continue
        d = pd.read_csv(fs[-1])
        d.columns = ["date", "v"]
        d["v"] = pd.to_numeric(d.v, errors="coerce")
        d = d.dropna()
        out[st] = float(d.v.iloc[-1] - d.v.iloc[-13])
    u = pd.read_csv(sorted((ROOT / "data/raw/fred").glob("*/UNRATE.csv"))[-1])
    u.columns = ["date", "v"]
    nat = float(u.v.iloc[-1] - u.v.iloc[-13])
    return {k: v - nat for k, v in out.items()}


# ---------------- Senate ----------------
def senate_races(polls):
    s = pd.read_csv(ROOT / "data/interim/senate_2026_races.csv")
    s["state_name"] = s.state.map(ABBR_STATE)
    # Nominees: Wikipedia candidate list; specials (FL, OH) and multi-R Alaska resolved from the latest polls
    def nominee(row, party):
        c = row[f"cands_{party}"]
        names = [n for n in str(c).split("; ") if n and n != "nan"]
        return names
    dem, rep, dside_party = [], [], []
    for _, r in s.iterrows():
        ds, rs, is_ = nominee(r, "D"), nominee(r, "R"), nominee(r, "I")
        # names appearing in recent polls for this state (most frequent two)
        recent = [x for x in polls if x["poll_type"] == "us-senator" and x["subject"] == f"2026 {r.state_name}"
                  and x["end"] >= pd.Timestamp("2026-09-01")]
        cnt = pd.Series([a["choice"] for x in recent for a in x["answers"]]).value_counts()
        top = list(cnt.index[:2]) if len(cnt) else []
        polled = lambda names: [n for n in names if P.lastname(n) in {P.lastname(t) for t in top}]  # noqa: E731
        d = polled(ds) or ds
        rr = polled(rs) or rs
        side = "D"
        if not d and is_:  # independent as the anti-R candidate (NE: Osborn)
            d = polled(is_) or is_[:1]
            side = "I"
        if r.special and top:  # FL / OH specials: Wikipedia summary lacks candidates
            known = {"FL": ("Angie Nixon", "Ashley Moody"), "OH": ("Sherrod Brown", "Jon Husted")}
            d, rr = [known[r.state][0]], [known[r.state][1]]
            assert all(any(P.lastname(n) == P.lastname(t) for t in top) for n in d + rr), (r.state, top)
        inc_clean = re.sub(r"\s*\(.*\)", "", str(r.incumbent)).strip()
        if rr and P.lastname(rr[0]) == P.lastname(inc_clean) and inc_clean in rs:
            rr = [inc_clean]
        dem.append(d[0] if d else None)
        rep.append(rr[0] if rr else None)
        dside_party.append(side)
    s["dem_nominee"], s["rep_nominee"], s["dside_party"] = dem, rep, dside_party
    s["inc_running"] = ~s.status.fillna("").str.contains("retir|lost", case=False) & ~s.incumbent.str.contains("retiring|lost", case=False)
    s.loc[s.special, "inc_party"] = "R"  # both specials are appointed Republicans running
    s.loc[s.special, "inc_running"] = True
    return s


def senate_model(s, polls, G, sd_nat, econ_adj=None):
    pav = P.senate(polls, s)
    rows = []
    for _, r in s.iterrows():
        inc = 0.0
        if r.inc_running and r.inc_party in ("D", "R"):
            inc = INC_SENATE if r.inc_party == "D" else -INC_SENATE
        prior = 2 * r.pvi + G + inc
        if econ_adj is not None and r.state in econ_adj:
            prior += STATE_ECON_COEF * econ_adj[r.state]  # R president: worse local job trend helps Dems
        if r.dside_party == "I":
            prior -= 0.0  # independents: use the same structural prior (Osborn has outrun it in polling)
        pa = pav.get(r.race_key)
        if r.state in MULTI_CANDIDATE:
            pa = P.senate_multi(polls, r)
        if pa and r.state in MULTI_CANDIDATE:
            wp, mu = 1.0, pa["avg"]
            sd = np.sqrt(SD_RACE_POLLAVG ** 2 + 3.0 ** 2 + (max(pa["spread_sd"], 4.0) ** 2) / pa["neff"])
        elif pa:
            lean_adj = LEAN_SLOPE * 2 * r.pvi if APPLY_LEAN_CORRECTION else 0.0
            pa = dict(pa, raw_avg=pa["avg"], avg=pa["avg"] + lean_adj)
            sd_p = np.sqrt(SD_RACE_POLLAVG ** 2 + (max(pa["spread_sd"], 4.0) ** 2) / pa["neff"])
            wp = (1 / sd_p ** 2) / (1 / sd_p ** 2 + 1 / SD_SENATE_PRIOR ** 2)
            mu = wp * pa["avg"] + (1 - wp) * prior
            sd = 1 / np.sqrt(1 / sd_p ** 2 + 1 / SD_SENATE_PRIOR ** 2)
        else:
            wp, mu, sd = 0.0, prior, SD_SENATE_PRIOR
        rows.append(dict(race_key=r.race_key, state=r.state, special=r.special, dem=r.dem_nominee, rep=r.rep_nominee,
                         dside=r.dside_party, inc_party=r.inc_party, pvi=r.pvi, prior=prior,
                         poll_avg=pa["avg"] if pa else np.nan, poll_avg_raw=pa.get("raw_avg", pa["avg"]) if pa else np.nan,
                         n_polls=pa["n_polls"] if pa else 0,
                         poll_weight=wp, mu=mu, sd_race=sd, rating_cook=r.get("rating_Cook"),
                         rating_silver=r.get("rating_Silver")))
    df = pd.DataFrame(rows)
    # national error is shared with the House draw (same z) -> scaled per chamber
    return df


# ---------------- House ----------------
def house_races():
    h = pd.read_csv(ROOT / "data/interim/house_2026_races.csv")
    st = h.status.fillna("")
    h["fixed"] = None
    h.loc[(h.n_rep == 0) & (h.n_dem > 0) & (h.ind_cand.isna() | (h.state != "CA")), "fixed"] = "D"
    h.loc[(h.n_dem == 0) & (h.n_rep > 0) & h.ind_cand.isna(), "fixed"] = "R"
    h.loc[st.str.contains("Democratic hold", case=False), "fixed"] = "D"
    h.loc[st.str.contains("Republican hold", case=False), "fixed"] = "R"
    h.loc[st.str.contains("re-elected", case=False) & h.inc_party.isin(["D", "R"]), "fixed"] = h.inc_party
    h["special_case"] = ""
    h.loc[(h.state == "CA") & (h.district == 6), ["fixed", "special_case"]] = [None, "Kiley (I, ex-R) vs Pan (D)"]
    h["inc_running"] = ~st.str.contains("retir|lost|resign|New representative|Vacant", case=False) & ~h.incumbent.fillna("").str.contains("None|Vacant")
    return h


def house_model(h, polls, G):
    pav = P.house(polls, h)
    mus, sds, pw, pavg = [], [], [], []
    for _, r in h.iterrows():
        inc = 0.0
        if r.inc_running:
            inc = INC_HOUSE if r.inc_party == "D" else -INC_HOUSE if r.inc_party in ("R", "I") else 0.0
        prior = 2 * r.pvi + G + inc
        pa = pav.get(r.race_key)
        if pa and APPLY_LEAN_CORRECTION:
            pa = dict(pa, avg=pa["avg"] + LEAN_SLOPE * 2 * r.pvi)
        if pa:
            sd_p = np.sqrt(SD_HOUSE_POLL ** 2 + (max(pa["spread_sd"], 4.0) ** 2) / pa["neff"])
            wp = (1 / sd_p ** 2) / (1 / sd_p ** 2 + 1 / SD_HOUSE_DISTRICT ** 2)
            mu = wp * pa["avg"] + (1 - wp) * prior
            sd = 1 / np.sqrt(1 / sd_p ** 2 + 1 / SD_HOUSE_DISTRICT ** 2)
        else:
            wp, mu, sd = 0.0, prior, SD_HOUSE_DISTRICT
        mus.append(mu); sds.append(sd); pw.append(wp); pavg.append(pa["avg"] if pa else np.nan)
    h = h.copy()
    h["prior_G"] = G
    h["mu"], h["sd_race"], h["poll_weight"], h["poll_avg"] = mus, sds, pw, pavg
    return h


# ---------------- simulation ----------------
SENATE_NOT_UP = {"R": 31, "D": 34}  # 53 R / 47 D-caucus (incl. King, Sanders) minus seats up in 2026 (22 R, 13 D)


def simulate(h, s, sd_nat_house):
    z = tdraw(NSIM)  # one shared national draw
    # House
    fixed = h.fixed.notna().values
    mu = h.mu.values[None, :] + (sd_nat_house * z)[:, None]
    margins = mu + tdraw((NSIM, len(h))) * h.sd_race.values[None, :]
    dwin = margins > 0
    dwin[:, fixed] = (h.fixed.values[fixed] == "D")[None, :]
    is_kiley = ((h.state == "CA") & (h.district == 6)).values
    d_seats = dwin.sum(1)
    kiley_win = ~dwin[:, is_kiley].any(1) if is_kiley.any() else np.zeros(NSIM, bool)
    r_seats = 435 - d_seats - kiley_win  # Kiley counted separately
    h = h.copy()
    h["p_dem"] = dwin.mean(0)
    # Senate: national Senate error shares the same z, scaled to the Senate calibration
    smu = s.mu.values[None, :] + (SD_NAT_SENATE * z)[:, None]
    sm = smu + tdraw((NSIM, len(s))) * s.sd_race.values[None, :]
    swin = sm > 0
    s = s.copy()
    s["p_dside"] = swin.mean(0)
    is_ind = (s.dside == "I").values
    d_up = swin[:, ~is_ind].sum(1)
    ind_win = swin[:, is_ind].sum(1)
    d_total = SENATE_NOT_UP["D"] + d_up
    r_total = 100 - d_total - ind_win
    res = {
        "house": {"dem_seats_mean": float(d_seats.mean()), "dem_seats_median": float(np.median(d_seats)),
                  "dem_seats_p10": float(np.percentile(d_seats, 10)), "dem_seats_p90": float(np.percentile(d_seats, 90)),
                  "p_dem_majority": float((d_seats >= 218).mean()), "p_rep_majority": float((r_seats >= 218).mean()),
                  "p_no_majority": float(((d_seats < 218) & (r_seats < 218)).mean()),
                  "p_kiley_wins": float(kiley_win.mean()),
                  "hist": np.bincount(d_seats, minlength=436).tolist()},
        "senate": {"dem_seats_mean": float(d_total.mean()), "dem_seats_median": float(np.median(d_total)),
                   "dem_seats_p10": float(np.percentile(d_total, 10)), "dem_seats_p90": float(np.percentile(d_total, 90)),
                   # VP (Vance, R) breaks 50-50 ties
                   "p_dem_control_without_osborn": float((d_total >= 51).mean()),
                   "p_dem_control_if_independents_caucus_D": float((d_total + ind_win >= 51).mean()),
                   "p_rep_control": float((r_total >= 50).mean()),
                   "independent_races": s.loc[is_ind, "state"].tolist(),
                   "p_indep_wins_each": dict(zip(s.loc[is_ind, "state"], swin[:, is_ind].mean(0).tolist())),
                   "p_osborn_wins": float(swin[:, (s.state == "NE").values].mean()),
                   "p_independents_pivotal": float(((d_total < 51) & (d_total + ind_win >= 51)).mean()),
                   "hist": np.bincount(d_total, minlength=101).tolist()},
    }
    return h, s, res


def run(model, shift=0.0, tag=None):
    nat, polls = national_inputs()
    if model == "polls_only":
        G, sd_nat, econ_adj = nat["G_polls"], SD_NAT_GENERIC, None
    else:
        G, sd_nat, econ_adj = nat["G_fund"], nat["sd_nat_fund"], state_unemp_change()
    G = G + shift
    s = senate_races(polls)
    smod = senate_model(s, polls, G, sd_nat, econ_adj)
    smod["mu"] = smod.mu + shift * smod.poll_weight  # polls part shifts too (prior part already via G)
    hmod = house_model(house_races(), polls, G)
    hmod["mu"] = hmod.mu + shift * hmod.poll_weight
    model = tag or model
    hmod, smod, res = simulate(hmod, smod, sd_nat)
    res["national"] = {k: v for k, v in nat.items() if k not in ("generic_aggregators", "approval_aggregators")}
    res["national"]["G_used"] = G
    res["national"]["bias_shift"] = shift
    res["national"]["sd_nat_house_used"] = sd_nat
    res["model"] = model
    hmod.to_csv(OUT / f"house_{model}.csv", index=False)
    smod.to_csv(OUT / f"senate_{model}.csv", index=False)
    (OUT / f"summary_{model}.json").write_text(json.dumps(res, indent=1, default=float))
    (OUT / "national_inputs.json").write_text(json.dumps(nat, indent=1, default=float))
    return hmod, smod, res


def sensitivity():
    """Vary the assumed fundamentals coefficients; record the range of outcomes."""
    global FUND
    base = dict(FUND)
    res = []
    for A in (-6.0, -2.0):
        for B in (0.4, 0.8):
            FUND = dict(base, A=A, B=B)
            _, _, r = run("polls_fundamentals", tag="_sens")
            res.append((r["national"]["fundamentals_margin_D"], r["national"]["G_used"], r["house"]["p_dem_majority"],
                        r["senate"]["p_dem_control_without_osborn"]))
    FUND = base
    for f in OUT.glob("*_sens*"):
        f.unlink()
    F, G, pH, pS = zip(*res)
    out = dict(F_min=min(F), F_max=max(F), G_min=min(G), G_max=max(G), pH_min=min(pH), pH_max=max(pH), pS_min=min(pS), pS_max=max(pS))
    (OUT / "sensitivity.json").write_text(json.dumps(out, indent=1))
    print("sensitivity", {k: round(v, 3) for k, v in out.items()})


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    for m, shift, tag in [("polls_only", 0.0, None), ("polls_fundamentals", 0.0, None),
                          ("polls_fundamentals", BIAS_ADJ, "polls_fundamentals_biasadj"),
                          ("polls_fundamentals", GENERIC_BIAS, "scenario_polls_overstate_dems")]:
        h, s, res = run(m, shift, tag)
        m = tag or m
        print(f"\n===== {m} =====  G used: D{res['national']['G_used']:+.2f}  (polls {res['national']['G_polls']:+.2f}, "
              f"fundamentals {res['national']['fundamentals_margin_D']:+.2f}, approval {res['national']['approval']:.1f})")
        hh, ss = res["house"], res["senate"]
        print(f"HOUSE  D seats mean {hh['dem_seats_mean']:.1f} (80% {hh['dem_seats_p10']:.0f}-{hh['dem_seats_p90']:.0f})  "
              f"P(D majority) {hh['p_dem_majority']:.1%}  P(R majority) {hh['p_rep_majority']:.1%}")
        print(f"SENATE D seats mean {ss['dem_seats_mean']:.1f} (80% {ss['dem_seats_p10']:.0f}-{ss['dem_seats_p90']:.0f})  "
              f"P(D control) {ss['p_dem_control_without_osborn']:.1%} / with independents {ss['p_dem_control_if_independents_caucus_D']:.1%}  "
              f"P(R control) {ss['p_rep_control']:.1%}  P(Osborn) {ss['p_osborn_wins']:.1%}")
        print(s[["race_key", "dem", "rep", "pvi", "prior", "poll_avg", "n_polls", "poll_weight", "mu", "sd_race", "p_dside", "rating_cook"]]
              .sort_values("p_dside").round(2).to_string())
    sensitivity()
    run("polls_fundamentals")  # restore national_inputs.json etc. to the base model
