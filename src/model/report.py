"""Write FORECAST.md from data/processed outputs.  Run after forecast.py and backtest.py."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
from common import ROOT  # noqa: E402

OUT = ROOT / "data" / "processed"


def j(name):
    return json.loads((OUT / name).read_text())


def pct(x):
    return f"{100 * x:.0f}%" if 0.005 <= x <= 0.995 else ("<1%" if x < 0.005 else ">99%")


def m(x):
    return "—" if pd.isna(x) else (f"D+{x:.1f}" if x >= 0 else f"R+{-x:.1f}")


def main():
    po, pf, ba, sc = (j("summary_polls_only.json"), j("summary_polls_fundamentals.json"),
                      j("summary_polls_fundamentals_biasadj.json"), j("summary_scenario_polls_overstate_dems.json"))
    nat = j("national_inputs.json")
    bt = j("backtest_summary.json")
    sen = pd.read_csv(OUT / "senate_polls_fundamentals.csv")
    sen_po = pd.read_csv(OUT / "senate_polls_only.csv").set_index("race_key")
    house = pd.read_csv(OUT / "house_polls_fundamentals.csv")
    house_po = pd.read_csv(OUT / "house_polls_only.csv").set_index("race_key")
    L = []
    a = L.append
    a("# 2026 Midterm Forecast\n")
    import datetime as dt
    a(f"_Generated {dt.datetime.now():%Y-%m-%d %H:%M} from the latest data snapshot. Refresh data + rerun everything: `python src/run_all.py`._\n")
    a("## Topline\n")
    V = (po, pf, ba, sc)
    a(f"| | Polls-only | Polls + fundamentals (unadjusted) | Polls + fundamentals, bias-adjusted ({ba['national']['bias_shift']:+.1f}) | Scenario: full historical bias ({sc['national']['bias_shift']:+.1f}) |")
    a("|---|---|---|---|---|")
    a("| National House environment (two-party) | " + " | ".join(m(x['national']['G_used']) for x in V) + " |")
    for lab, key in [("**P(Democratic House majority)**", "p_dem_majority"), ("P(Republican House majority)", "p_rep_majority")]:
        a(f"| {lab} | " + " | ".join(pct(x['house'][key]) for x in V) + " |")
    a("| Dem House seats, mean (80% range) | " + " | ".join(
        f"{x['house']['dem_seats_mean']:.0f} ({x['house']['dem_seats_p10']:.0f}–{x['house']['dem_seats_p90']:.0f})" for x in V) + " |")
    a("| **P(Democratic Senate control)** | " + " | ".join(pct(x["senate"]["p_dem_control_without_osborn"]) for x in V) + " |")
    a("| P(Dem control if independents caucus D) | " + " | ".join(pct(x["senate"]["p_dem_control_if_independents_caucus_D"]) for x in V) + " |")
    a("| P(Republican Senate control) | " + " | ".join(pct(x["senate"]["p_rep_control"]) for x in V) + " |")
    a("| Dem-caucus Senate seats, mean (80% range) | " + " | ".join(
        f"{x['senate']['dem_seats_mean']:.1f} ({x['senate']['dem_seats_p10']:.0f}–{x['senate']['dem_seats_p90']:.0f})" for x in V) + " |")
    a("")
    a("Democrats need 51 Senate seats for control (VP Vance breaks 50–50 ties); 34 Dem-caucus and 31 Republican seats are not up. "
      "Independent candidates (Osborn in NE, Achilles in ID) are counted separately; neither has committed to a caucus.\n")
    if (OUT / "sensitivity.json").exists():
        sv = json.loads((OUT / "sensitivity.json").read_text())
        a(f"**Fundamentals sensitivity** (each of the ten top estimated specifications, both samples): "
          f"fundamentals-only environment ranges {m(sv['F_min'])} to {m(sv['F_max'])}; after blending with polls, "
          f"{m(sv['G_min'])} to {m(sv['G_max'])}, P(D House) {pct(sv['pH_min'])}–{pct(sv['pH_max'])}, "
          f"P(D Senate) {pct(sv['pS_min'])}–{pct(sv['pS_max'])}.\n")
    a("**Benchmark:** Silver Bulletin's FLIPR (Nov 1 free summary) gives Democrats ~95% to win the House with a ~25-seat net gain "
      "(≈238 seats); Senate numbers are paywalled (described as a meaningful Democratic edge).\n")

    a("## National inputs\n")
    e = nat["econ"]
    a(f"- **Generic ballot**: mean of 5 aggregators on Wikipedia (DDHQ, FiftyPlusOne, NBC, RCP, Silver Bulletin; updated Oct 30), "
      f"converted to two-party: **{m(nat['G_polls'])}**. Own average of VoteHub polls (through early Oct, VoteHub stopped tracking): "
      f"{m(nat['G_votehub_own_avg']['avg'])}.")
    a(f"- **Trump approval**: {nat['approval']:.1f}% (mean of 8 aggregators).")
    a(f"- **Economy** (FRED, as of {e['econ_asof']}): unemployment {e['unemployment']:.1f}% ({e['unemp_chg_12m']:+.1f} over 12 months), "
      f"CPI inflation {e['cpi_yoy']:.1f}% y/y, real disposable income per capita {e['rdi_pc_growth_yoy']:+.1f}% y/y.")
    fj = json.loads((OUT / "fundamentals.json").read_text())
    fa = fj["all_1962_2022"]
    a(f"- **Real gas prices** {fj['inputs_2026']['gas']:+.1f}% y/y (Sept; gasoline CPI ÷ CPI-U); **CPI inflation** {fj['inputs_2026']['infl']:.1f}% (Sept/Sept, unrevised CPI-U).")
    a(f"- **Fundamentals estimate** (estimated on 1962–2022; top specifications averaged, LOO RMSE {fa['loo_rmse_avg']:.1f}, SD used 4.5): "
      f"{m(nat['fundamentals_margin_D'])}. Blended with polls by inverse variance "
      f"({nat['fund_weight_on_polls']:.0%} weight on polls) → {m(nat['G_fund'])}.")
    a(f"- **Uncertainty** (from 538 poll-vs-result archive, 1998–2022): national generic-ballot miss RMSE {nat['sd_nat_polls']:.1f} pts "
      f"(historical mean {nat['generic_hist_bias']:+.1f}: polls have tended to overstate Democrats); Senate shared miss {nat['sd_nat_senate']:.1f}; "
      f"race-level poll-average error {nat['sd_race_pollavg']:.1f}. All errors are fat-tailed (t, estimated df), 40,000 simulations.\n")

    a("## Senate races\n")
    a(f"Margins are two-party D−R (Montana: best non-R minus R). The forecast blends the poll average (on average "
      f"{pf['national']['race_poll_weight_mean_polled']:.0%} weight in polled races) with a structural prior (2×PVI + environment + incumbency). "
      f"Nationally, polls get {pf['national']['w_polls_national']:.0%} of the weight vs. the fundamentals.\n")
    a("| Race | Democrat / Ind. | Republican | PVI | Poll avg (n) | Prior | Forecast margin | P(D/I win) polls-only | P(D/I win) +fund | Cook | Silver |")
    a("|---|---|---|---|---|---|---|---|---|---|---|")
    for _, r in sen.sort_values("p_dside", ascending=False).iterrows():
        po_p = sen_po.loc[r.race_key, "p_dside"]
        name = r.race_key.split("|")[1] + (" (sp.)" if r.special else "")
        dn = f"{r.dem}{' (I)' if r.dside == 'I' else ''}"
        a(f"| {name} | {dn} | {r.rep} | {m(2 * r.pvi)} | {m(r.poll_avg)} ({int(r.n_polls)}) | {m(r.prior)} | {m(r.mu)} | {pct(po_p)} | {pct(r.p_dside)} | {r.rating_cook} | {r.rating_silver} |")
    a("")

    a("## Competitive House seats\n")
    comp = house[(house.p_dem > 0.1) & (house.p_dem < 0.9)].sort_values("p_dem", ascending=False)
    a(f"{len(comp)} seats have a Democratic win probability between 10% and 90% (polls+fundamentals). "
      f"Full table: `data/processed/house_polls_fundamentals.csv`.\n")
    a("| District | Incumbent (party) | PVI | Open? | District poll avg | Forecast margin | P(D win) polls-only | P(D win) +fund |")
    a("|---|---|---|---|---|---|---|---|")
    for _, r in comp.iterrows():
        inc = str(r.incumbent).split(" Redistricted")[0]
        a(f"| {r.state}-{int(r.district)} | {inc} ({r.inc_party}) | {m(2 * r.pvi) if False else ('D+%d' % r.pvi if r.pvi > 0 else 'R+%d' % -r.pvi if r.pvi < 0 else 'EVEN')} | "
          f"{'open' if not r.inc_running else ''} | {m(r.poll_avg)} | {m(r.mu)} | {pct(house_po.loc[r.race_key, 'p_dem'])} | {pct(r.p_dem)} |")
    a("")
    a("_PVI column in the House table is Cook-style share PVI (district vs. nation); in the Senate table it is shown as the implied margin (2×PVI)._\n")

    a("## Backtest (2018 & 2022, poll-average component)\n")
    for cyc in ("2018", "2022"):
        b = bt[cyc]
        a(f"- **{cyc} Senate**: {b['races']} races, winner called correctly {b['winner_accuracy']:.0%}, Brier {b['brier']:.3f}, "
          f"mean error {b['mean_error']:+.1f} (D−R), MAE {b['mae']:.1f}. Misses: " +
          ", ".join(f"{x['state']} (polls {m(x['poll_avg'])}, actual {m(x['actual'])})" for x in b["misses"]))
    for g in bt["generic"]:
        a(f"- **{g['cycle']} generic ballot**: my average {m(g['generic_avg_two_party'])} vs. actual House vote {m(g['actual_house_margin'])} (error {g['error']:+.1f}).")
    btr = pd.read_csv(OUT / "backtest_senate_2018_2022.csv")
    btr["bin"] = pd.cut(btr.p_dem, [0, .1, .3, .5, .7, .9, 1.0001])
    cb = btr.groupby("bin", observed=True).agg(n=("dem_won", "size"), p=("p_dem", "mean"), w=("dem_won", "mean"))
    a("- Calibration by forecast bin: " + "; ".join(f"{iv.left:.0%}–{min(iv.right, 1):.0%}: forecast {r.p:.0%}, Dems won {r.w:.0%} of {int(r.n)}"
                                                     for iv, r in cb.iterrows()) +
      ". The middle bins resolve more decisively than forecast, i.e. the model is somewhat under-confident with the two-party error scales. "
      "Caveat: error scales were estimated on data that include these cycles (in-sample).\n")

    a("## Caveats and judgment calls\n")
    best = fa["top"][0]
    a("- **Fundamentals are estimated** (`src/model/fundamentals.py`): president's-party House margin on Gallup approval, the previous House margin, "
      "real gas-price change, inflation, real income growth and unemployment change; every subset of up to 4 predictors scored by leave-one-out RMSE, "
      "top five averaged. Best specification: " + ", ".join(f"{k} {v:+.2f} (±{best['se'][k]:.2f})" for k, v in best["coef"].items()) + ". "
      "Inflation adds nothing once approval is in; real gas has the expected sign but is only ~1.5 SE from zero. "
      "2026 approval and the gas-price rise are both outside the 1962–2022 range, so the estimate extrapolates. "
      "Unemployment (12-month change and level) was tested nationally: both are weak (coefficients within ~1.5 SE of zero) and enter only as minor terms in the averaged model.")
    se = json.loads((OUT / "state_econ.json").read_text())
    a(f"- **State unemployment** (`src/model/state_econ.py`, {se['n_races']} Senate/governor races 1998–2022). Relative to state lean and the national "
      f"environment, a worse local job trend is associated with {se['struct']['coef']:+.2f} pts for Democrats-under-a-Republican-president "
      f"(cluster SE {se['struct']['se_cluster']:.2f}; wrong sign, no held-out gain), so the Senate prior uses {se['coef_used']:.1f}. As a correction to poll "
      f"averages the effect is {se['miss']['coef']:+.2f} (SE {se['miss']['se_cluster']:.2f}), but it improves held-out error by only 0.1%, so it is not applied.")
    pw = json.loads((OUT / "prior_weight.json").read_text())
    a(f"- **Polls vs. partisanship (Senate).** On {pw['n_races']} races 1998–2022, the optimal weight on final-three-week polls vs. a lean + environment "
      f"prior is {pw['w']:.2f} (SE {pw['w_se']:.2f}); the prior's errors are fat-tailed (robust SD {pw['prior_sd_robust']:.1f}, SD {pw['sd_prior_resid']:.1f}). "
      f"Polled races use prior SD {pw['implied_prior_sd']:.1f} (≈{pw['w']:.2f} weight on polls); unpolled races use {pw['prior_sd_robust']:.1f}. "
      f"Previously an assumed 10 for both (0.64 weight). See `src/model/prior_weight.py`.")
    hs = json.loads((OUT / "house_structure.json").read_text())
    c = hs["chosen"]
    a(f"- **House district model (estimated)** on {hs['n']} contested races 2006–2024: margin = {c['const']:.2f} + {c['b_lean2']:.2f}×(2×PVI) + "
      f"{c['g_nat']:.2f}×national ± {c['inc']:.1f} incumbency; district SD {c['sd_district']:.1f}; district polls get ~{hs['district_polls']['w']:.2f} weight "
      f"(poll SD {hs['district_polls']['implied_poll_sd']:.1f}). Incumbency fell from ~20 pts (2006) to ~4 (2018–2024). Expected-seat RMSE over 2006–2024: 6.7 vs 11.9 "
      "for the old assumed model; recent cycles undercount Democratic contested-seat wins by ~6.")
    bc = json.loads((OUT / "bias_confidence.json").read_text())
    pr = bc["pred_all_14"]
    a(f"- **Is the bias adjustment justified?** Polls overstated Democrats in 11 of 14 elections 1998–2024 (mean {pr['mean']:.1f}, predictive SD "
      f"{pr['pred_sd']:.1f}; P(overstate again) {pr['p_overstate_dems']:.0%}); LV-only polls 2018–2024 averaged {bc['lv_only_2018_2024']['mean']:.1f}; "
      f"Senate polls missed against Democrats in all five cycles since 2014 (mean {bc['senate_vs_generic']['sen_mean_2014plus']:.1f}). Nothing observable "
      f"predicts the size. This year's generic-ballot pollsters are a typical mix (house effect {bc['pollster_mix']['generic']['mix_house_effect']:+.2f}); "
      f"the battleground Senate pollsters lean slightly Republican ({bc['pollster_mix']['senate_key']['mix_house_effect']:+.2f}; historical miss "
      f"{-bc['pollster_mix']['senate_key']['mix_raw_miss']:.1f}). The Bias-adjusted model: national shift {ba['national']['bias_shift']:+.2f} "
      f"(estimate + LV discount {bc['lv_discount_est']:.2f}), Senate shift {ba['national']['senate_bias_shift']:+.2f} (battleground pollsters' record + discount) "
      f"plus the state-lean term. The Senate moves ~10 pts of control probability per point of national shift because five races in R-leaning states sit within 3 pts of even.")
    ps = json.loads((OUT / "poll_settings.json").read_text())["chosen"]
    a(f"- **Poll-averaging settings (estimated, `src/model/poll_settings.py`)**: sponsor shift {ps['partisan_shift_statewide']} pts statewide / "
      f"{ps['partisan_shift_house']} House; population weights RV {ps['pop_weight']['rv']}, adults {ps['pop_weight']['a']}, with RV/adult polls shifted "
      f"{ps['pop_dem_lean']['rv']}/{ps['pop_dem_lean']['a']} pts toward Republicans; half-life {ps['half_life_races']} days (backtest prefers no decay); "
      f"t with {ps['df_t']} df.")
    es = json.loads((OUT / "error_structure.json").read_text())
    a(f"- **Correlated errors.** Beyond the shared national miss, each simulation draws a Census-region shock (SD {es['sigma_region']:.1f}) and a random "
      f"slope on state lean (SD {es['lean_slope']['all']['sd_true']:.3f} per point), with each race's total variance held fixed. The regional component is "
      "small in 1998–2022 data; a 2-pt regional sensitivity moves Senate control by about 1 point (see `data/processed/error_sensitivity.json`).")
    a(f"- **Polling bias.** On a two-party basis, final generic-ballot averages overstated Democrats by 3.1 pts on average over 1998–2022 "
      f"(9 of 13 elections; 2018 was the main exception at +0.5). A decay-weighted re-estimate that up-weights recent midterms gives "
      f"{nat['generic_hist_bias']:+.1f}; adding party in the White House, House incumbency, a second-term flag or a president-specific effect "
      f"makes out-of-sample prediction worse, so none is used. The bias-adjusted model shifts every race by {ba['national']['bias_shift']:+.1f} "
      f"(the estimate less 1 pt because the 2026 aggregators already adjust to likely voters, which ran 1–1.5 pts less Democratic than "
      f"registered-voter polls in 2020/2022). The scenario column applies the full {sc['national']['bias_shift']:+.1f}. "
      f"Details: `src/model/bias_decay.py`, `data/processed/bias_decay.json`.")
    a("- **State-level poll misses.** Since 2010, results have landed further toward a state's partisan lean than final poll averages "
      "(about 0.08 pts per point of lean, symmetric in red and blue states; a real-time 2014–2022 backtest improved race-level RMSE from 5.6 to 5.3). "
      "This is an outcome-based pattern, not a test of differential non-response by party: no source here records response rates. Not applied "
      "in the published models; `APPLY_LEAN_CORRECTION` in `src/model/forecast.py`.")
    a("- **Michigan**: Haley Stevens endorsed Mike Rogers on Nov 1, after most polls were taken. Not modeled; Silver Bulletin estimates ~1 pt effect.")
    a("- **Alaska** uses ranked-choice voting and has multiple 'Dan Sullivan' candidates on the ballot; modeled as a head-to-head.")
    a("- **Montana** is a genuine three-way race (Alme R, Bankhead D, Bodnar I); modeled from polls only, best non-R vs. R.")
    a("- **Independents**: Osborn (NE) and Achilles (ID) treated as the anti-Republican candidate; control reported both ways. "
      "**CA-6** (Kevin Kiley, now independent) is excluded from both parties' House counts.")
    a("- **House district leans** are Wikipedia's 2026 PVI on the new lines (mid-decade maps in TX, CA, MO, NC, UT, OH, VA, FL, TN, LA, AL). "
      "District error SD 6 pts and incumbency +2.5 pts are assumptions typical of district models. Same-party and uncontested seats are fixed.")
    a("- **District polls** (VoteHub, ~180) are sparse and often internal; partisan-sponsored polls are shifted against the sponsor (estimated: 6.3 pts for districts) and shrunk toward the prior.")
    a("- Expert ratings (Cook, Silver) are shown for comparison only and are not model inputs.")
    (ROOT / "FORECAST.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote FORECAST.md", len(comp), "competitive House seats")


if __name__ == "__main__":
    main()
