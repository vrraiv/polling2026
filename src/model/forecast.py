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
_PSF = Path(__file__).resolve().parents[2] / "data/processed/poll_settings.json"
if _PSF.exists():  # estimated: Student-t fitted to race-level poll-average misses (src/model/poll_settings.py)
    DF_T = float(json.loads(_PSF.read_text())["chosen"]["df_t"])

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
BIAS_SD = 2.6
if _BD.exists():
    _specs = json.loads(_BD.read_text())["specs"]
    _top = sorted(_specs, key=lambda r: r["loo_rmse_weighted"])[:10]
    BIAS_SD = float(np.mean([r["pred_sd"] for r in _top]))  # predictive SD of the bias estimate (~2.6)
# Likely-voter discount: the historical miss is measured on all polls; today's averages approximate likely voters.
# Estimated in src/model/bias_confidence.py as (LV-poll miss - all-poll miss) over 2018-2024 (~0.4). Was an assumed 1.0.
_BC = OUT / "bias_confidence.json"
_bc = json.loads(_BC.read_text()) if _BC.exists() else {}
LV_DISCOUNT = float(_bc.get("lv_discount_est", 1.0))
BIAS_ADJ = GENERIC_BIAS + LV_DISCOUNT            # national (generic-ballot / House) shift for the adjusted model
# Candidate Senate-wide shift: the historical miss of the pollsters polling the 2026 battleground Senate races
# (2014-2022, result - poll) plus the LV discount. NOT used by the published Bias-adjusted model: a real-time test
# (src/model/bias_realtime.py) finds no out-of-sample gain from a Senate-wide level shift, while the generic-ballot
# shift and the state-lean term both improve real-time error. Kept for the off-site pocket scenario.
SENATE_BIAS_ADJ_CANDIDATE = float(_bc["senate_mix_bias"]) + LV_DISCOUNT if "senate_mix_bias" in _bc else BIAS_ADJ
SENATE_BIAS_ADJ = 0.0
# Senate state-lean differential (adjusted model only): results since 2010 landed further toward state lean than polls.
ADJ_USE_LEAN = True
SD_NAT_SENATE = float(np.sqrt(np.mean(np.square(SEN_CYC))))     # shared Senate polling miss per cycle
SD_RACE_POLLAVG = CAL["Sen-G"]["race_resid_sd_midterms"]        # race-level error of a final poll average (flat; kept for reference)
_SDN = CAL.get("pollavg_sd_by_n")


def pollavg_sd(pa):
    """Error of a race's poll average as a function of how many polls it has (calibrate.py: SD(n) = sqrt(a^2 + b^2/n),
    fitted on final-3-week averages 1998-2022). n = polls in the last 21 days; older polls count half (staler)."""
    if not _SDN:
        return np.sqrt(SD_RACE_POLLAVG ** 2 + (max(pa["spread_sd"], 4.0) ** 2) / pa["neff"])
    n = max(pa.get("n_recent", 0) + 0.5 * (pa["n_polls"] - pa.get("n_recent", 0)), 1.0)
    return float(np.sqrt(_SDN["a"] ** 2 + _SDN["b"] ** 2 / n))
# Senate prior error: estimated in src/model/prior_weight.py from 1998-2022 races (optimal weight on late polls
# ~0.87 => prior SD ~18.7 given the poll-average SD). Previously an assumed 10, which over-weighted partisanship.
_PW = OUT / "prior_weight.json"
_pw = json.loads(_PW.read_text()) if _PW.exists() else {}
SD_SENATE_PRIOR = float(_pw.get("implied_prior_sd", 10.0))          # sets the weight on polls in polled races (~0.86)
SD_SENATE_PRIOR_UNPOLLED = float(_pw.get("prior_sd_robust", 10.0))   # error of the prior alone (robust; tails come from t5)
MULTI_CANDIDATE = {"MT"}   # genuine 3-way races: use raw (best non-R minus R) poll margin, no PVI prior
# House district model, estimated in src/model/house_structure.py from 2006-2024 Wikipedia district results:
#   margin = const + B_LEAN*(2*PVI) + G_NAT*national + INC_HOUSE*(+1 D inc / -1 R inc)
_HS = OUT / "house_structure.json"
_hs = json.loads(_HS.read_text())["chosen"] if _HS.exists() else {}
_hsp = json.loads(_HS.read_text())["district_polls"] if _HS.exists() else {}
H_CONST = float(_hs.get("const", 0.0))
H_B_LEAN = float(_hs.get("b_lean2", 1.0))
H_G_NAT = float(_hs.get("g_nat", 1.0))          # districts move ~0.78 pts per pt of national margin (and national error)
INC_HOUSE = float(_hs.get("inc", 2.5))
SD_HOUSE_DISTRICT = float(_hs.get("sd_district", 6.0))
SD_HOUSE_POLL = float(_hsp.get("implied_poll_sd", 7.5))
INC_SENATE = 2.0
T_SCALE = np.sqrt((DF_T - 2) / DF_T)

# Correlated-error structure beyond the national factor (src/model/error_structure.py):
# a shared shock per Census region and a per-simulation random slope on state lean.
_ES = OUT / "error_structure.json"
if _ES.exists():
    _es = json.loads(_ES.read_text())
    SIGMA_REGION = float(_es["sigma_region"])
    SIGMA_LEAN_SLOPE = float(_es["lean_slope"]["all"]["sd_true"])
    STATE_REGION = {st: r for r, sts in _es["regions"].items() for st in sts}
else:
    SIGMA_REGION, SIGMA_LEAN_SLOPE, STATE_REGION = 0.0, 0.0, {}
REGIONS = ["Northeast", "Midwest", "South", "West"]  # so scaled t has the stated SD

# Fundamentals (ASSUMED coefficients, not estimated here: two midterms can't identify them and keyless
# historical approval data wasn't available). President's-party House margin in a midterm:
#   F = A + B*(approval - 45) + C*(real disposable income per capita growth yoy - 1.5)
# Estimated fundamentals (src/model/fundamentals.py): president's-party House margin regressed on Gallup approval,
# previous House margin, real gas-price change, inflation, income and unemployment; top specifications by
# leave-one-out RMSE, averaged. SD = LOO RMSE of the averaged model (3.9) inflated ~15% for specification
# search and for 2026 inputs outside the historical range (approval, gas) -> 4.5.
_FJ = OUT / "fundamentals.json"
FUND_EST = json.loads(_FJ.read_text()) if _FJ.exists() else None
FUND = {"SD": 4.5, "set": "all_1962_2022", "spec": None}  # spec=None -> weighted average of top specs


def fundamentals_margin_pres(approval_agg, set_=None, spec=None):
    """Predicted president's-party House margin for 2026, using today's approval (aggregator mean + Gallup house effect)."""
    est = FUND_EST[set_ or FUND["set"]]
    x = dict(FUND_EST["inputs_2026"])
    x["approval"] = approval_agg + FUND_EST["gallup_offset"]
    x["midterm"] = 1.0
    tops = est["top"] if spec is None else [t for t in est["top"] if t["vars"] == spec] or [est["top"][0]]
    preds, ws = [], []
    for t in tops:
        c = t["coef"]
        preds.append(c.get("const", 0.0) + sum(c[v] * float(x[v]) for v in t["vars"]))
        ws.append(t["weight"])
    return float(np.average(preds, weights=ws))
# State-lean poll correction (src/model/bias_analysis.py): since 2010, final poll averages have understated
# state partisanship -- results land further toward the state's lean. Slope per point of lean margin (2*PVI),
# pooled over 2010-2022 Senate+Gov races; improved held-out accuracy in a real-time backtest.
_BIAS = ROOT / "data/processed/bias_analysis.json"
LEAN_SLOPE = json.loads(_BIAS.read_text())["state"]["post2010_symmetric"]["slope"] if _BIAS.exists() else 0.0
APPLY_LEAN_CORRECTION = False  # off for the first published build; see bias_analysis.py
# State-economy term in the Senate prior, estimated in src/model/state_econ.py (D gain per point that state
# unemployment rose more than national over 12 months, R president). Set to 0 there unless it improves held-out error.
_SE = OUT / "state_econ.json"
STATE_ECON_COEF = float(json.loads(_SE.read_text())["coef_used"]) if _SE.exists() else 0.0


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
    F_pres = fundamentals_margin_pres(approval, FUND["set"], FUND["spec"])
    econ["real_gas_change_yoy"] = FUND_EST["inputs_2026"]["gas"]
    econ["cpi_infl_sept_yoy"] = FUND_EST["inputs_2026"]["infl"]
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


def rating(v):
    """Expert rating as the forecaster publishes it: drop Wikipedia's "(flip)" marker (rating favors the non-holding party)."""
    return re.sub(r"\s*\(flip\)", "", v).strip() if isinstance(v, str) else v


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
            sd = np.sqrt(pollavg_sd(pa) ** 2 + 3.0 ** 2)
        elif pa:
            lean_adj = LEAN_SLOPE * 2 * r.pvi if APPLY_LEAN_CORRECTION else 0.0
            pa = dict(pa, raw_avg=pa["avg"], avg=pa["avg"] + lean_adj)
            sd_p = pollavg_sd(pa)
            wp = (1 / sd_p ** 2) / (1 / sd_p ** 2 + 1 / SD_SENATE_PRIOR ** 2)
            mu = wp * pa["avg"] + (1 - wp) * prior
            sd = 1 / np.sqrt(1 / sd_p ** 2 + 1 / SD_SENATE_PRIOR ** 2)
        else:
            wp, mu, sd = 0.0, prior, SD_SENATE_PRIOR_UNPOLLED
        econ_term = STATE_ECON_COEF * econ_adj[r.state] if econ_adj is not None and r.state in econ_adj else 0.0
        rows.append(dict(race_key=r.race_key, state=r.state, special=r.special, dem=r.dem_nominee, rep=r.rep_nominee,
                         dside=r.dside_party, inc_party=r.inc_party, pvi=r.pvi, prior=prior,
                         prior_env=G, prior_inc=inc, prior_econ=econ_term,
                         poll_avg=pa["avg"] if pa else np.nan, poll_avg_raw=pa.get("raw_avg", pa["avg"]) if pa else np.nan,
                         n_polls=pa["n_polls"] if pa else 0,
                         poll_weight=wp, mu=mu, sd_race=sd, rating_cook=rating(r.get("rating_Cook")),
                         rating_silver=rating(r.get("rating_Silver"))))
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
    mus, sds, pw, pavg, priors, incs, npolls = [], [], [], [], [], [], []
    for _, r in h.iterrows():
        inc = 0.0
        if r.inc_running:
            inc = INC_HOUSE if r.inc_party == "D" else -INC_HOUSE if r.inc_party in ("R", "I") else 0.0
        prior = H_CONST + H_B_LEAN * 2 * r.pvi + H_G_NAT * G + inc
        priors.append(prior); incs.append(inc)
        pa = pav.get(r.race_key)
        if pa and APPLY_LEAN_CORRECTION and False:  # House: lean pattern was estimated on statewide races only
            pa = dict(pa, avg=pa["avg"] + LEAN_SLOPE * 2 * r.pvi)
        if pa:
            sd_p = np.sqrt(SD_HOUSE_POLL ** 2 + (max(pa["spread_sd"], 4.0) ** 2) / pa["neff"])
            wp = (1 / sd_p ** 2) / (1 / sd_p ** 2 + 1 / SD_HOUSE_DISTRICT ** 2)
            mu = wp * pa["avg"] + (1 - wp) * prior
            sd = 1 / np.sqrt(1 / sd_p ** 2 + 1 / SD_HOUSE_DISTRICT ** 2)
        else:
            wp, mu, sd = 0.0, prior, SD_HOUSE_DISTRICT
        mus.append(mu); sds.append(sd); pw.append(wp); pavg.append(pa["avg"] if pa else np.nan)
        npolls.append(pa["n_polls"] if pa else 0)
    h = h.copy()
    h["prior_G"] = G
    h["mu"], h["sd_race"], h["poll_weight"], h["poll_avg"] = mus, sds, pw, pavg
    h["prior"], h["prior_inc"], h["n_polls"] = priors, incs, npolls
    return h


# ---------------- simulation ----------------
SENATE_NOT_UP = {"R": 31, "D": 34}  # 53 R / 47 D-caucus (incl. King, Sanders) minus seats up in 2026 (22 R, 13 D)


def correlated_part(df, region_shock, slope, sigma_region):
    """Region shock + lean-slope term for each race, and the idiosyncratic SD that keeps total variance unchanged."""
    ridx = np.array([REGIONS.index(STATE_REGION.get(st, "South")) for st in df.state])
    lean = 2.0 * df.pvi.values  # lean in margin units (same units as the historical estimate)
    corr = region_shock[:, ridx] + slope[:, None] * lean[None, :]
    var_corr = sigma_region ** 2 + (SIGMA_LEAN_SLOPE * lean) ** 2
    sd = df.sd_race.values
    sd_idio = np.sqrt(np.maximum(sd ** 2 - var_corr, (0.5 * sd) ** 2))
    return corr, sd_idio


def simulate(h, s, sd_nat_house, sd_nat_senate=None, sigma_region=None):
    sd_nat_senate = SD_NAT_SENATE if sd_nat_senate is None else sd_nat_senate
    sigma_region = SIGMA_REGION if sigma_region is None else sigma_region
    z = tdraw(NSIM)  # one shared national draw (House and Senate)
    region_shock = RNG.standard_normal((NSIM, len(REGIONS))) * sigma_region   # shared by House and Senate races in a region
    slope = RNG.standard_normal(NSIM) * SIGMA_LEAN_SLOPE                      # polarisation miss, centred at 0
    # House
    fixed = h.fixed.notna().values
    hcorr, h_idio = correlated_part(h, region_shock, slope, sigma_region)
    mu = h.mu.values[None, :] + (H_G_NAT * sd_nat_house * z)[:, None] + hcorr
    margins = mu + tdraw((NSIM, len(h))) * h_idio[None, :]
    dwin = margins > 0
    dwin[:, fixed] = (h.fixed.values[fixed] == "D")[None, :]
    is_kiley = ((h.state == "CA") & (h.district == 6)).values
    d_seats = dwin.sum(1)
    kiley_win = ~dwin[:, is_kiley].any(1) if is_kiley.any() else np.zeros(NSIM, bool)
    r_seats = 435 - d_seats - kiley_win  # Kiley counted separately
    h = h.copy()
    h["p_dem"] = dwin.mean(0)
    # where the simulated margin lands (display only; fixed seats have no contest)
    hq = np.percentile(margins, [10, 25, 75, 90], axis=0)
    for qi, qn in enumerate(["q10", "q25", "q75", "q90"]):
        h[qn] = np.where(fixed, np.nan, hq[qi])
    # Senate: national Senate error shares the same z, scaled to the Senate calibration
    scorr, s_idio = correlated_part(s, region_shock, slope, sigma_region)
    smu = s.mu.values[None, :] + (sd_nat_senate * z)[:, None] + scorr
    sm = smu + tdraw((NSIM, len(s))) * s_idio[None, :]
    # implied error correlations for selected Senate pairs
    err = sm - s.mu.values[None, :]
    keys = list(s.state + np.where(s.special, "-sp", ""))
    pairs = [("MI", "OH-sp"), ("MI", "IA"), ("OH-sp", "IA"), ("TX", "KS"), ("ME", "NC"), ("TX", "ME"), ("AK", "IA")]
    corr_pairs = {f"{a}~{b}": float(np.corrcoef(err[:, keys.index(a)], err[:, keys.index(b)])[0, 1])
                  for a, b in pairs if a in keys and b in keys}
    swin = sm > 0
    s = s.copy()
    s["p_dside"] = swin.mean(0)
    sq = np.percentile(sm, [10, 25, 75, 90], axis=0)
    for qi, qn in enumerate(["q10", "q25", "q75", "q90"]):
        s[qn] = sq[qi]
    is_ind = (s.dside == "I").values
    d_up = swin[:, ~is_ind].sum(1)
    ind_win = swin[:, is_ind].sum(1)
    d_total = SENATE_NOT_UP["D"] + d_up
    r_total = 100 - d_total - ind_win
    # kept for the site's scenario explorer (written by run() for the published models only)
    global LAST_SIMS
    LAST_SIMS = {"nat_house": sd_nat_house * z, "d_seats": d_seats, "d_total": d_total, "swin": swin,
                 "race_keys": list(s.race_key), "p_dside": s.p_dside.values}
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
                   "error_corr_pairs": corr_pairs,
                   "p_house_and_senate_D": float(((d_seats >= 218) & (d_total >= 51)).mean()),
                   "p_house_D_senate_R": float(((d_seats >= 218) & (r_total >= 50)).mean()),
                   "p_independents_pivotal": float(((d_total < 51) & (d_total + ind_win >= 51)).mean()),
                   "hist": np.bincount(d_total, minlength=101).tolist()},
    }
    res["senate"]["reading"] = senate_reading(s, swin, sm, is_ind, d_total, keys)
    res["house"]["reading"] = house_reading(h, dwin, margins, d_seats, fixed)
    return h, s, res


def house_reading(h, dwin, margins, d_seats, fixed):
    """House counterpart of senate_reading: all-favorites count, upsets per simulation, the path to 218 (tipping point =
    the district that supplies the 218th Democratic seat) and the seats most likely to change hands."""
    p = dwin.mean(0)
    fav = p > 0.5
    comp = (p > 0.05) & (p < 0.95) & ~fixed
    upsets = (dwin[:, comp] != fav[comp][None, :]).sum(1)
    up_d = (dwin[:, comp] & ~fav[comp][None, :]).sum(1)
    up_r = (~dwin[:, comp] & fav[comp][None, :]).sum(1)
    kmax = int(min(60, np.percentile(upsets, 99.5) + 1))
    p_up = [float((upsets == k).mean()) for k in range(kmax)] + [float((upsets >= kmax).mean())]
    # tipping point: the 218th most Democratic district in each simulation (fixed seats pinned)
    m_eff = margins.copy()
    m_eff[:, fixed] = np.where(h.fixed.values[fixed] == "D", 1e6, -1e6)[None, :]
    tp_idx = np.argpartition(-m_eff, 217, axis=1)[:, 217]
    tp = np.bincount(tp_idx, minlength=len(h)) / len(tp_idx)
    ctrl = d_seats >= 218
    labels = (h.state + "-" + h.district.astype(int).astype(str)).tolist()
    order = np.argsort(-p, kind="stable")
    ladder = []
    for rank, j in enumerate(order):
        if not (0.02 < p[j] < 0.98):
            continue
        col = dwin[:, j]
        ladder.append({"label": labels[j], "seat": rank + 1, "p": float(p[j]), "tp": float(tp[j]),
                       "p_ctrl_given_win": float(ctrl[col].mean()) if col.any() else None,
                       "p_ctrl_given_loss": float(ctrl[~col].mean()) if (~col).any() else None})
    pivot = labels[order[217]]
    inc = h.inc_party.fillna("").values
    flips = lambda party, pf: sorted(({"label": labels[j], "p_flip": float(pf[j]), "inc": str(h.incumbent.iloc[j]).split(" Redistricted")[0],
                                       "inc_running": bool(h.inc_running.iloc[j])}
                                      for j in range(len(h)) if inc[j] == party and pf[j] >= 0.05 and not fixed[j]),
                                     key=lambda z: -z["p_flip"])
    to_d, to_r = flips("R", p), flips("D", 1 - p)
    tpo = np.argsort(-tp)[:5]
    return {"n_comp": int(comp.sum()), "fav_dem": int(fav.sum()), "seats_if_favorites_win": int(fav.sum()),
            "p_favorites_map": float((upsets == 0).mean()), "upsets_mean": float(upsets.mean()), "p_upsets": p_up,
            "upsets_to_dem_mean": float(up_d.mean()), "upsets_to_rep_mean": float(up_r.mean()),
            "ladder": ladder, "pivot": pivot, "n_above_ladder": int((p >= 0.98).sum()),
            "tipping_point": [{"label": labels[j], "p": float(tp[j])} for j in tpo],
            "exp_gain_from_R": float(p[inc == "R"].sum()), "exp_loss_from_D": float((1 - p[inc == "D"]).sum()),
            "exp_open_D": float(p[(inc == "O") & ~fixed].sum() + (h.fixed.values[(inc == "O") & fixed] == "D").sum()),
            "n_open": int((inc == "O").sum()), "held_R": int((inc == "R").sum()), "held_D": int((inc == "D").sum()),
            "flip_to_d": to_d[:12], "flip_to_r": to_r[:12], "n_flip_to_d": len(to_d), "n_flip_to_r": len(to_r)}


PUBLISHED = ("polls_only", "polls_fundamentals", "polls_fundamentals_biasadj")
LAST_SIMS = None


def write_sims(model, od):
    """Compact per-simulation file for the site's scenario explorer: national environment error, Democratic House seats,
    Democratic Senate seats (independents excluded, as in the headline) and win bits for the Senate races in play.
    Layout (little-endian, n = simulations): uint32[n] race bits | int16[n] env error in 0.1 pts | uint16[n] House
    seats | uint8[n] Senate seats."""
    S = LAST_SIMS
    n = len(S["d_seats"])
    p = S["p_dside"]
    inplay = [j for j in np.argsort(np.abs(p - 0.5)) if 0.002 < p[j] < 0.998][:32]
    inplay = sorted(inplay)
    bits = np.zeros(n, dtype="<u4")
    for b, j in enumerate(inplay):
        bits |= (S["swin"][:, j].astype("<u4") << np.uint32(b))
    nat = np.clip(np.round(S["nat_house"] * 10), -32000, 32000).astype("<i2")
    hs = S["d_seats"].astype("<u2")
    st = S["d_total"].astype("u1")
    (od / f"sims_{model}.bin").write_bytes(bits.tobytes() + nat.tobytes() + hs.tobytes() + st.tobytes())
    meta = {"n": n, "races": [S["race_keys"][j] for j in inplay], "nat_scale": 0.1, "layout": "u4 bits|i2 nat|u2 house|u1 senate",
            "senate_not_up_d": SENATE_NOT_UP["D"], "file": f"sims_{model}.bin"}
    (od / f"sims_{model}.json").write_text(json.dumps(meta))


def senate_reading(s, swin, sm, is_ind, d_total, keys):
    """How to read race probabilities as a map: the all-favorites map and how often it happens, the most common
    exact maps, upsets per simulation, and the tipping-point race (the one that delivers the 51st Dem seat)."""
    p = swin.mean(0)
    fav = p > 0.5
    comp = (p > 0.05) & (p < 0.95)
    ck = [k for k, c in zip(keys, comp) if c]
    upsets = (swin[:, comp] != fav[comp][None, :]).sum(1)
    fav_map = (swin[:, comp] == fav[comp][None, :]).all(1)
    rows, inv, cnt = np.unique(swin[:, comp], axis=0, return_inverse=True, return_counts=True)
    inv = np.asarray(inv).ravel()
    top = list(np.argsort(-cnt)[:4])
    fav_row = np.where((rows == fav[comp][None, :]).all(1))[0]
    if len(fav_row) and fav_row[0] not in top:
        top.append(fav_row[0])
    maps = []
    win_lab = lambda j, w: ("I" if is_ind[comp][j] else "D") if w else "R"
    for t in top:
        sel = inv == t
        diff = [{"race": k, "winner": win_lab(j, rows[t][j])} for j, k in enumerate(ck) if rows[t][j] != fav[comp][j]]
        maps.append({"p": float(cnt[t] / len(inv)), "upsets": diff, "dem_seats": int(np.median(d_total[sel])),
                     "ind_wins": int(rows[t][is_ind[comp]].sum()), "is_favorites": not diff,
                     "winners": {k: win_lab(j, rows[t][j]) for j, k in enumerate(ck)}})
    need = 51 - SENATE_NOT_UP["D"]
    dm = sm[:, ~is_ind]
    dkeys = [k for k, i in zip(keys, is_ind) if not i]
    tp_idx = np.argsort(-dm, axis=1)[:, need - 1]
    tp = np.bincount(tp_idx, minlength=len(dkeys)) / len(tp_idx)
    order = np.argsort(-tp)[:5]
    ctrl = d_total >= 51
    dw = swin[:, ~is_ind]
    ladder = []
    for j, k in enumerate(dkeys):
        col = dw[:, j]
        ladder.append({"race": k, "p": float(col.mean()), "tp": float(tp[j]),
                       "p_win_given_ctrl": float(col[ctrl].mean()) if ctrl.any() else None,
                       "p_ctrl_given_win": float(ctrl[col].mean()) if col.any() else None,
                       "p_ctrl_given_loss": float(ctrl[~col].mean()) if (~col).any() else None})
    ladder.sort(key=lambda r: -r["p"])
    up_d = (swin[:, comp] & ~fav[comp][None, :]).sum(1)
    up_r = (~swin[:, comp] & fav[comp][None, :]).sum(1)
    return {"n_comp": int(comp.sum()), "comp_races": ck,
            "fav_dem": int((fav & ~is_ind).sum()), "fav_ind": int((fav & is_ind).sum()),
            "seats_if_favorites_win": int(SENATE_NOT_UP["D"] + (fav & ~is_ind).sum()),
            "p_favorites_map": float(fav_map.mean()), "upsets_mean": float(upsets.mean()),
            "p_upsets": [float((upsets == k).mean()) for k in range(9)] + [float((upsets >= 9).mean())],
            "upsets_to_dem_mean": float(up_d.mean()), "upsets_to_rep_mean": float(up_r.mean()),
            "p_upsets_cancel": float((up_d == up_r).mean()), "ladder": ladder, "not_up_dem": int(SENATE_NOT_UP["D"]),
            "expected_comp_dem_wins": float(p[comp & ~is_ind].sum()),
            "maps": maps,
            "tipping_point": [{"race": dkeys[i], "p": float(tp[i])} for i in order]}


def run(model, shift=0.0, tag=None, bias_removed=False, sigma_region=None, senate_shift=None, use_lean=False,
        senate_bias_removed=None, out_dir=None):
    """bias_removed=True: the polls' historical bias is taken out as a mean shift, so the national polling SD
    drops from the RMSE (which includes the bias) to the predictive SD of the bias estimate (BIAS_SD).
    senate_bias_removed (default = bias_removed): whether the shared Senate polling SD is narrowed the same way. The
    Bias-adjusted model removes no Senate-wide bias, so it keeps the full Senate RMSE."""
    if senate_bias_removed is None:
        senate_bias_removed = bias_removed
    nat, polls = national_inputs()
    sd_polls = BIAS_SD if bias_removed else SD_NAT_GENERIC
    if model == "polls_only":
        G, sd_nat, econ_adj = nat["G_polls"] + shift, sd_polls, None
        w_polls = 1.0
    else:
        # the polling bias applies to the polls only, not to the fundamentals; blend weight and SD use the same sd_polls
        w_polls = (1 / sd_polls ** 2) / (1 / sd_polls ** 2 + 1 / FUND["SD"] ** 2)
        G = w_polls * (nat["G_polls"] + shift) + (1 - w_polls) * nat["fundamentals_margin_D"]
        econ_adj = state_unemp_change()
        sd_nat = 1 / np.sqrt(1 / sd_polls ** 2 + 1 / FUND["SD"] ** 2)
    sd_sen = SD_NAT_SENATE * (sd_polls / SD_NAT_GENERIC) if senate_bias_removed else SD_NAT_SENATE
    s = senate_races(polls)
    global APPLY_LEAN_CORRECTION
    keep_lean = APPLY_LEAN_CORRECTION
    APPLY_LEAN_CORRECTION = bool(use_lean)
    smod = senate_model(s, polls, G, sd_nat, econ_adj)
    APPLY_LEAN_CORRECTION = keep_lean
    sshift = shift if senate_shift is None else senate_shift
    # Senate poll averages shift by the Senate-specific amount; the prior's environment (G) already carries the national shift
    smod["mu"] = smod.mu + sshift * smod.poll_weight
    hmod = house_model(house_races(), polls, G)
    hmod["mu"] = hmod.mu + shift * hmod.poll_weight
    model = tag or model
    hmod, smod, res = simulate(hmod, smod, sd_nat, sd_sen, sigma_region)
    res["national"] = {k: v for k, v in nat.items() if k not in ("generic_aggregators", "approval_aggregators")}
    res["national"]["G_used"] = G
    res["national"]["bias_shift"] = shift
    res["national"]["senate_bias_shift"] = sshift
    res["national"]["senate_lean_correction"] = bool(use_lean)
    res["national"]["w_polls_national"] = w_polls
    res["national"]["race_poll_weight_mean_polled"] = float(smod.loc[smod.n_polls > 0, "poll_weight"].mean())
    res["national"]["sd_nat_house_used"] = sd_nat
    res["national"]["sd_nat_senate_used"] = sd_sen
    res["national"]["sigma_region"] = SIGMA_REGION if sigma_region is None else sigma_region
    res["national"]["sigma_lean_slope"] = SIGMA_LEAN_SLOPE
    res["model"] = model
    od = out_dir or OUT
    od.mkdir(parents=True, exist_ok=True)
    hmod.to_csv(od / f"house_{model}.csv", index=False)
    smod.to_csv(od / f"senate_{model}.csv", index=False)
    (od / f"summary_{model}.json").write_text(json.dumps(res, indent=1, default=float))
    if od == OUT and model in PUBLISHED:
        write_sims(model, od)
    (OUT / "national_inputs.json").write_text(json.dumps(nat, indent=1, default=float))
    return hmod, smod, res


def sensitivity():
    """Spread of outcomes across the estimated fundamentals specifications (each top spec, both samples)."""
    base = dict(FUND)
    res = []
    for set_ in ("all_1962_2022", "midterms_1962_2022"):
        for t in FUND_EST[set_]["top"]:
            FUND.update(set=set_, spec=t["vars"])
            _, _, r = run("polls_fundamentals", tag="_sens")
            res.append({"set": set_, "vars": t["vars"], "F": r["national"]["fundamentals_margin_D"], "G": r["national"]["G_used"],
                        "pH": r["house"]["p_dem_majority"], "pS": r["senate"]["p_dem_control_without_osborn"]})
    FUND.clear(); FUND.update(base)
    for f in OUT.glob("*_sens*"):
        f.unlink()
    F = [x["F"] for x in res]; G = [x["G"] for x in res]; pH = [x["pH"] for x in res]; pS = [x["pS"] for x in res]
    out = dict(F_min=min(F), F_max=max(F), G_min=min(G), G_max=max(G), pH_min=min(pH), pH_max=max(pH), pS_min=min(pS), pS_max=max(pS),
               specs=res)
    (OUT / "sensitivity.json").write_text(json.dumps(out, indent=1))
    print("sensitivity", {k: round(v, 3) for k, v in out.items() if k != "specs"})


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    # off-site scenarios (not published; kept for the post-election scorecard) -> data/processed/pocket/
    POCKET = OUT / "pocket"
    for f in OUT.glob("*scenario_polls_overstate_dems*"):
        f.unlink()
    for tag, kw in [("pocket_senate_wide_shift", dict(shift=BIAS_ADJ, bias_removed=True, senate_shift=SENATE_BIAS_ADJ_CANDIDATE,
                                                      use_lean=ADJ_USE_LEAN)),
                    ("pocket_full_historical_bias", dict(shift=GENERIC_BIAS, bias_removed=True))]:
        _, _, r = run("polls_fundamentals", tag=tag, out_dir=POCKET, **kw)
        print(f"pocket {tag}: Senate P(D) {r['senate']['p_dem_control_without_osborn']:.1%}, House P(D) {r['house']['p_dem_majority']:.1%}")
    for m, shift, tag in [("polls_only", 0.0, None), ("polls_fundamentals", 0.0, None),
                          ("polls_fundamentals", BIAS_ADJ, "polls_fundamentals_biasadj")]:
        adj = tag == "polls_fundamentals_biasadj"
        h, s, res = run(m, shift, tag, bias_removed=bool(shift), senate_shift=SENATE_BIAS_ADJ if adj else None, use_lean=adj and ADJ_USE_LEAN,
                        senate_bias_removed=False)
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
    # error-structure sensitivity: national factor only vs. estimated structure vs. strong regional factor
    es = {}
    for lab, sr, sl in [("national_only", 0.0, 0.0), ("estimated", None, None), ("strong_region_2pt", 2.0, None)]:
        keep = SIGMA_LEAN_SLOPE
        if sl is not None:
            SIGMA_LEAN_SLOPE = sl
        _, _, r = run("polls_fundamentals", tag="_errsens", sigma_region=sr)
        SIGMA_LEAN_SLOPE = keep
        es[lab] = {"p_dem_senate": r["senate"]["p_dem_control_without_osborn"], "senate_p10": r["senate"]["dem_seats_p10"],
                   "senate_p90": r["senate"]["dem_seats_p90"], "p_dem_house": r["house"]["p_dem_majority"],
                   "house_p10": r["house"]["dem_seats_p10"], "house_p90": r["house"]["dem_seats_p90"],
                   "corr_pairs": r["senate"]["error_corr_pairs"]}
        print("error structure", lab, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in es[lab].items() if k != "corr_pairs"},
              {k: round(v, 2) for k, v in es[lab]["corr_pairs"].items()})
    for f in OUT.glob("*_errsens*"):
        f.unlink()
    (OUT / "error_sensitivity.json").write_text(json.dumps(es, indent=1))
    run("polls_fundamentals")  # restore national_inputs.json etc. to the base model
