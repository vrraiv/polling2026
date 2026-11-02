# 2026 Midterm Forecast

_Generated 2026-11-02 06:02 from the latest data snapshot. Refresh data + rerun everything: `python src/run_all.py`._

## Topline

| | Polls-only | Polls + fundamentals (unadjusted) | Polls + fundamentals, bias-adjusted (-2.1) | Scenario: full historical bias (-3.1) |
|---|---|---|---|---|
| National House environment (two-party) | D+9.1 | D+9.7 | D+7.9 | D+7.2 |
| **P(Democratic House majority)** | 90% | 96% | 93% | 88% |
| P(Republican House majority) | 10% | 4% | 7% | 12% |
| Dem House seats, mean (80% range) | 239 (218–261) | 240 (223–259) | 232 (219–245) | 228 (217–240) |
| **P(Democratic Senate control)** | 68% | 70% | 50% | 38% |
| P(Dem control if independents caucus D) | 69% | 71% | 51% | 39% |
| P(Republican Senate control) | 31% | 29% | 49% | 61% |
| Dem-caucus Senate seats, mean (80% range) | 51.6 (48–55) | 51.8 (49–55) | 50.5 (48–53) | 49.9 (47–53) |

Democrats need 51 Senate seats for control (VP Vance breaks 50–50 ties); 34 Dem-caucus and 31 Republican seats are not up. Independent candidates (Osborn in NE, Achilles in ID) are counted separately; neither has committed to a caucus.

**Fundamentals sensitivity** (each of the ten top estimated specifications, both samples): fundamentals-only environment ranges D+8.0 to D+11.8; after blending with polls, D+8.6 to D+10.3, P(D House) 94%–97%, P(D Senate) 66%–72%.

**Benchmark:** Silver Bulletin's FLIPR (Nov 1 free summary) gives Democrats ~95% to win the House with a ~25-seat net gain (≈238 seats); Senate numbers are paywalled (described as a meaningful Democratic edge).

## National inputs

- **Generic ballot**: mean of 5 aggregators on Wikipedia (DDHQ, FiftyPlusOne, NBC, RCP, Silver Bulletin; updated Oct 30), converted to two-party: **D+9.1**. Own average of VoteHub polls (through early Oct, VoteHub stopped tracking): D+8.2.
- **Trump approval**: 36.8% (mean of 8 aggregators).
- **Economy** (FRED, as of 2026-09-01): unemployment 4.2% (-0.1 over 12 months), CPI inflation 4.0% y/y, real disposable income per capita +0.7% y/y.
- **Real gas prices** +29.3% y/y (Sept; gasoline CPI ÷ CPI-U); **CPI inflation** 3.7% (Sept/Sept, unrevised CPI-U).
- **Fundamentals estimate** (estimated on 1962–2022; top specifications averaged, LOO RMSE 3.9, SD used 4.5): D+10.4. Blended with polls by inverse variance (56% weight on polls) → D+9.7.
- **Uncertainty** (from 538 poll-vs-result archive, 1998–2022): national generic-ballot miss RMSE 4.0 pts (historical mean -3.1: polls have tended to overstate Democrats); Senate shared miss 3.3; race-level poll-average error 7.4. All errors are fat-tailed (t, 5 df), 40,000 simulations.

## Senate races

Margins are two-party D−R (Montana: best non-R minus R). The forecast blends the poll average (on average 64% weight in polled races) with a structural prior (2×PVI + environment + incumbency). Nationally, polls get 56% of the weight vs. the fundamentals.

| Race | Democrat / Ind. | Republican | PVI | Poll avg (n) | Prior | Forecast margin | P(D/I win) polls-only | P(D/I win) +fund | Cook | Silver |
|---|---|---|---|---|---|---|---|---|---|---|
| MA | Ed Markey | John Deaton | D+28.0 | D+30.8 (9) | D+39.7 | D+34.0 | >99% | >99% | Solid D | Solid D |
| RI | Jack Reed | Raymond McKay | D+16.0 | D+28.6 (5) | D+27.7 | D+28.3 | >99% | >99% | Solid D | Solid D |
| VA | Mark Warner | Bert Mizusawa | D+6.0 | D+20.2 (2) | D+17.7 | D+19.3 | 99% | 99% | Solid D | Solid D |
| NM | Ben Ray Luján | Larry Marker | D+8.0 | D+19.2 (2) | D+19.7 | D+19.4 | 99% | 99% | Solid D | Solid D |
| DE | Chris Coons | Michael Katz | D+16.0 | — (0) | D+27.7 | D+27.7 | 99% | 99% | Solid D | Solid D |
| OR | Jeff Merkley | David Brock Smith | D+16.0 | — (0) | D+27.7 | D+27.7 | 99% | 99% | Solid D | Solid D |
| IL | Juliana Stratton | Don Tracy | D+12.0 | D+13.5 (3) | D+21.7 | D+16.6 | 99% | 99% | Solid D | Solid D |
| CO | John Hickenlooper | Mark Baisley | D+12.0 | — (0) | D+23.7 | D+23.7 | 98% | 98% | Solid D | Solid D |
| NJ | Cory Booker | Justin Murphy | D+8.0 | — (0) | D+19.7 | D+19.7 | 97% | 97% | Solid D | Solid D |
| NH | Chris Pappas | John E. Sununu | D+4.0 | D+8.7 (10) | D+13.7 | D+10.5 | 94% | 94% | Lean D | Likely D |
| GA | Jon Ossoff | Mike Collins | R+2.0 | D+10.0 (11) | D+9.7 | D+9.9 | 93% | 94% | Likely D | Solid D |
| NC | Roy Cooper | Michael Whatley | R+2.0 | D+11.1 (25) | D+7.7 | D+9.9 | 93% | 94% | Likely D (flip) | Solid D (flip) |
| MN | Peggy Flanagan | Michele Tafoya | D+6.0 | D+3.6 (7) | D+15.7 | D+8.1 | 89% | 90% | Lean D | Likely D |
| ME | Troy Jackson | Susan Collins | D+8.0 | D+3.7 (20) | D+15.7 | D+8.0 | 89% | 90% | Tossup | Likely D (flip) |
| MI | Abdul El-Sayed | Mike Rogers | D+0.0 | D+4.8 (36) | D+9.7 | D+6.6 | 85% | 85% | Tossup | Likely D |
| OH (sp.) | Sherrod Brown | Jon Husted | R+10.0 | D+4.1 (23) | R+2.3 | D+1.8 | 61% | 62% | Tossup | Lean D (flip) |
| TX | James Talarico | Ken Paxton | R+12.0 | D+3.1 (39) | R+2.3 | D+1.2 | 56% | 58% | Tossup | Likely D (flip) |
| KS | Adam Hamilton | Roger Marshall | R+16.0 | D+4.2 (7) | R+8.3 | R+0.3 | 47% | 48% | Tossup | Lean D (flip) |
| IA | Josh Turek | Ashley Hinson | R+12.0 | D+0.2 (22) | R+2.3 | R+0.7 | 44% | 46% | Tossup | Tossup |
| AK | Mary Peltola | Dan S. Sullivan | R+12.0 | D+1.0 (9) | R+4.3 | R+1.0 | 42% | 43% | Tossup | Tossup |
| SC | Annie Andrews | Darline Graham | R+16.0 | R+2.3 (4) | R+8.3 | R+4.6 | 22% | 23% | Lean R | Lean R |
| FL (sp.) | Angie Nixon | Ashley Moody | R+10.0 | R+6.6 (15) | R+2.3 | R+5.1 | 19% | 20% | Likely R | Likely R |
| NE | Dan Osborn (I) | Pete Ricketts | R+20.0 | R+2.1 (4) | R+12.3 | R+5.9 | 16% | 17% | Lean R | Lean R |
| MT | Alani Bankhead | Kurt Alme | R+20.0 | R+10.0 (6) | R+10.3 | R+10.0 | 12% | 12% | Solid R | Likely R |
| LA | Jamie Davis | Julia Letlow | R+22.0 | — (0) | R+12.3 | R+12.3 | 9% | 10% | Solid R | Likely R |
| MS | Scott Colom | Cindy Hyde-Smith | R+22.0 | R+4.8 (2) | R+14.3 | R+8.6 | 9% | 10% | Likely R | Solid R |
| KY | Charles Booker | Andy Barr | R+30.0 | — (0) | R+20.3 | R+20.3 | 2% | 3% | Solid R | Solid R |
| ID | Todd Achilles (I) | Jim Risch | R+36.0 | R+6.2 (1) | R+28.3 | R+15.4 | 2% | 2% | Solid R | Solid R |
| SD | Brian Bengs (I) | Mike Rounds | R+30.0 | R+12.1 (4) | R+22.3 | R+16.5 | 1% | 2% | Solid R | Solid R |
| OK | N'Kiyla Jasmine Thomas | Kevin Hern | R+34.0 | — (0) | R+24.3 | R+24.3 | 1% | 1% | Solid R | Solid R |
| AR | Hallie Shoffner | Tom Cotton | R+30.0 | R+13.0 (4) | R+22.3 | R+16.5 | 1% | 1% | Solid R | Solid R |
| AL | Everett Wess | Barry Moore | R+30.0 | R+16.5 (5) | R+20.3 | R+18.0 | 1% | 1% | Solid R | Solid R |
| WV | Rachel Fetty Anderson | Shelley Moore Capito | R+42.0 | — (0) | R+34.3 | R+34.3 | <1% | <1% | Solid R | Solid R |
| TN | Marquita Bradshaw | Bill Hagerty | R+28.0 | R+24.4 (1) | R+20.3 | R+22.7 | <1% | <1% | Solid R | Solid R |
| WY | James W. Byrd | Harriet Hageman | R+46.0 | — (0) | R+36.3 | R+36.3 | <1% | <1% | Solid R | Solid R |

## Competitive House seats

67 seats have a Democratic win probability between 10% and 90% (polls+fundamentals). Full table: `data/processed/house_polls_fundamentals.csv`.

| District | Incumbent (party) | PVI | Open? | District poll avg | Forecast margin | P(D win) polls-only | P(D win) +fund |
|---|---|---|---|---|---|---|---|
| TX-34 | Vicente Gonzalez (D) | R+3 |  | D+7.2 | D+6.5 | 86% | 89% |
| AZ-1 | David Schweikert (R) | R+1 | open | D+4.0 | D+6.4 | 86% | 89% |
| NY-17 | Mike Lawler (R) | D+1 |  | D+1.0 | D+6.3 | 85% | 89% |
| NJ-7 | Thomas Kean Jr. (R) | EVEN |  | — | D+7.2 | 84% | 88% |
| AZ-6 | Juan Ciscomani (R) | EVEN |  | — | D+7.2 | 84% | 88% |
| CO-8 | Gabe Evans (R) | EVEN |  | — | D+7.2 | 84% | 88% |
| PA-7 | Ryan Mackenzie (R) | R+1 |  | D+6.2 | D+5.6 | 82% | 86% |
| NC-1 | Don Davis (D) | R+5 |  | D+10.9 | D+5.1 | 80% | 84% |
| FL-25 | Jared Moskowitz (D) | R+3 |  | D+1.6 | D+4.7 | 77% | 82% |
| FL-14 | Kathy Castor (D) | R+4 |  | D+5.5 | D+4.6 | 77% | 81% |
| WA-3 | Marie Gluesenkamp Perez (D) | R+2 |  | R+2.9 | D+4.5 | 76% | 81% |
| PA-1 | Brian Fitzpatrick (R) | D+1 |  | R+5.0 | D+4.5 | 77% | 81% |
| VA-2 | Jen Kiggans (R) | EVEN |  | R+4.0 | D+3.5 | 71% | 75% |
| IA-3 | Zach Nunn (R) | R+2 |  | — | D+3.2 | 66% | 71% |
| NC-11 | Chuck Edwards (R) | R+5 |  | D+13.1 | D+2.5 | 65% | 69% |
| IA-2 | Ashley Hinson (R) | R+4 | open | D+2.7 | D+2.0 | 62% | 66% |
| IA-1 | Mariannette Miller-Meeks (R) | R+4 |  | D+6.7 | D+1.7 | 59% | 63% |
| MT-1 | Ryan Zinke (R) | R+5 | open | D+4.5 | D+1.3 | 57% | 60% |
| FL-22 | None (new seat) (O) | R+4 | open | D+0.0 | D+1.1 | 55% | 59% |
| MI-10 | John James (R) | R+3 | open | R+4.0 | D+1.1 | 55% | 59% |
| WI-3 | Derrick Van Orden (R) | R+3 |  | — | D+1.2 | 54% | 59% |
| OH-7 | Max Miller (R) | R+5 |  | D+7.7 | D+1.1 | 55% | 59% |
| MI-4 | Bill Huizenga (R) | R+3 |  | — | D+1.2 | 54% | 58% |
| TX-35 | None (new seat) (O) | R+4 | open | R+0.1 | D+1.0 | 55% | 58% |
| PA-10 | Scott Perry (R) | R+3 |  | — | D+1.2 | 54% | 58% |
| WI-1 | Bryan Steil (R) | R+2 |  | R+3.4 | D+0.8 | 54% | 57% |
| PA-8 | Rob Bresnahan (R) | R+4 |  | D+4.0 | D+0.8 | 53% | 56% |
| VA-1 | Rob Wittman (R) | R+3 |  | R+0.7 | D+0.5 | 51% | 54% |
| OH-9 | Marcy Kaptur (D) | R+5 |  | R+4.0 | D+0.1 | 48% | 51% |
| FL-7 | Cory Mills (R) | R+5 | open | — | R+0.3 | 44% | 48% |
| MO-2 | Ann Wagner (R) | R+4 |  | D+0.1 | R+0.5 | 43% | 46% |
| ME-2 | Jared Golden (D) | R+4 | open | R+5.1 | R+0.6 | 44% | 46% |
| NY-1 | Nick LaLota (R) | R+4 |  | — | R+0.8 | 41% | 44% |
| OH-10 | Mike Turner (R) | R+4 |  | R+0.7 | R+0.8 | 41% | 44% |
| TX-15 | Monica De La Cruz (R) | R+7 |  | D+8.1 | R+1.4 | 37% | 39% |
| AL-2 | Shomari Figures (D) | R+7 |  | R+2.1 | R+1.9 | 34% | 35% |
| SC-1 | Nancy Mace (R) | R+6 | open | R+2.0 | R+2.2 | 32% | 33% |
| KY-6 | Andy Barr (R) | R+7 | open | D+1.6 | R+2.2 | 32% | 33% |
| OH-15 | Mike Carey (R) | R+5 |  | R+1.5 | R+2.4 | 31% | 32% |
| WA-5 | Michael Baumgartner (R) | R+5 |  | — | R+2.8 | 29% | 32% |
| FL-4 | Aaron Bean (R) | R+5 |  | — | R+2.8 | 30% | 31% |
| CO-5 | Jeff Crank (R) | R+5 |  | — | R+2.8 | 30% | 31% |
| CO-3 | Jeff Hurd (R) | R+5 |  | R+2.9 | R+2.9 | 28% | 28% |
| FL-9 | Darren Soto (D) | R+8 |  | — | R+3.8 | 24% | 26% |
| MN-1 | Brad Finstad (R) | R+6 |  | R+1.5 | R+3.6 | 24% | 23% |
| FL-11 | Daniel Webster (R) | R+7 | open | — | R+4.3 | 23% | 23% |
| AZ-2 | Eli Crane (R) | R+7 |  | D+2.0 | R+3.9 | 23% | 23% |
| NC-3 | Greg Murphy (R) | R+6 |  | — | R+4.8 | 20% | 21% |
| TX-23 | Vacant (O) | R+7 | open | R+4.0 | R+4.2 | 20% | 21% |
| NY-2 | Andrew Garbarino (R) | R+6 |  | — | R+4.8 | 20% | 21% |
| FL-13 | Anna Paulina Luna (R) | R+6 |  | R+3.2 | R+4.2 | 21% | 20% |
| FL-16 | Vern Buchanan (R) | R+6 | open | R+8.9 | R+4.5 | 20% | 19% |
| NE-1 | Mike Flood (R) | R+6 |  | R+4.1 | R+4.6 | 19% | 19% |
| FL-27 | María Elvira Salazar (R) | R+6 |  | R+5.1 | R+4.9 | 18% | 17% |
| VA-5 | John McGuire (R) | R+6 |  | R+5.2 | R+4.9 | 18% | 17% |
| NV-2 | Mark Amodei (R) | R+7 | open | R+6.2 | R+4.9 | 17% | 17% |
| GA-1 | Buddy Carter (R) | R+8 | open | — | R+6.3 | 15% | 15% |
| FL-2 | Neal Dunn (R) | R+8 | open | — | R+6.3 | 14% | 15% |
| TX-32 | None (new seat) (O) | R+8 | open | — | R+6.3 | 15% | 15% |
| NC-7 | David Rouzer (R) | R+7 |  | — | R+6.8 | 13% | 13% |
| FL-21 | Brian Mast (R) | R+7 |  | — | R+6.8 | 13% | 13% |
| SC-2 | Joe Wilson (R) | R+7 |  | — | R+6.8 | 13% | 13% |
| FL-26 | Mario Díaz-Balart (R) | R+7 |  | — | R+6.8 | 13% | 13% |
| GA-12 | Rick Allen (R) | R+7 |  | — | R+6.8 | 13% | 13% |
| MN-8 | Pete Stauber (R) | R+7 |  | — | R+6.8 | 13% | 13% |
| FL-12 | Gus Bilirakis (R) | R+7 |  | — | R+6.8 | 13% | 13% |
| AR-2 | French Hill (R) | R+8 |  | R+2.5 | R+6.6 | 11% | 10% |

_PVI column in the House table is Cook-style share PVI (district vs. nation); in the Senate table it is shown as the implied margin (2×PVI)._

## Backtest (2018 & 2022, poll-average component)

- **2018 Senate**: 30 races, winner called correctly 93%, Brier 0.050, mean error -0.3 (D−R), MAE 5.6. Misses: Florida (polls D+1.1, actual R+0.1), Indiana (polls D+0.5, actual R+5.9)
- **2022 Senate**: 28 races, winner called correctly 96%, Brier 0.047, mean error -1.8 (D−R), MAE 4.6. Misses: Nevada (polls R+0.1, actual D+0.8)
- **2018 generic ballot**: my average D+8.4 vs. actual House vote D+8.5 (error +0.1).
- **2022 generic ballot**: my average R+0.0 vs. actual House vote R+2.6 (error -2.6).
- Calibration by forecast bin: 0%–10%: forecast 2%, Dems won 0% of 12; 10%–30%: forecast 21%, Dems won 0% of 5; 30%–50%: forecast 40%, Dems won 20% of 5; 50%–70%: forecast 55%, Dems won 67% of 6; 70%–90%: forecast 80%, Dems won 100% of 6; 90%–100%: forecast 98%, Dems won 100% of 24. The middle bins resolve more decisively than forecast, i.e. the model is somewhat under-confident with the two-party error scales. Caveat: error scales were estimated on data that include these cycles (in-sample).

## Caveats and judgment calls

- **Fundamentals are estimated** (`src/model/fundamentals.py`): president's-party House margin on Gallup approval, the previous House margin, real gas-price change, inflation, real income growth and unemployment change; every subset of up to 4 predictors scored by leave-one-out RMSE, top five averaged. Best specification: const -10.72 (±3.33), approval +0.26 (±0.07), prev +0.79 (±0.11), gas -0.08 (±0.05), midterm -8.96 (±1.59). Inflation adds nothing once approval is in; real gas has the expected sign but is only ~1.5 SE from zero. 2026 approval and the gas-price rise are both outside the 1962–2022 range, so the estimate extrapolates. Unemployment (12-month change and level) was tested nationally: both are weak (coefficients within ~1.5 SE of zero) and enter only as minor terms in the averaged model.
- **State unemployment** (`src/model/state_econ.py`, 584 Senate/governor races 1998–2022). Relative to state lean and the national environment, a worse local job trend is associated with -1.71 pts for Democrats-under-a-Republican-president (cluster SE 1.29; wrong sign, no held-out gain), so the Senate prior uses 0.0. As a correction to poll averages the effect is +0.78 (SE 0.39), but it improves held-out error by only 0.1%, so it is not applied.
- **Correlated errors.** Beyond the shared national miss, each simulation draws a Census-region shock (SD 0.5) and a random slope on state lean (SD 0.078 per point), with each race's total variance held fixed. The regional component is small in 1998–2022 data; a 2-pt regional sensitivity moves Senate control by about 1 point (see `data/processed/error_sensitivity.json`).
- **Polling bias.** On a two-party basis, final generic-ballot averages overstated Democrats by 3.1 pts on average over 1998–2022 (9 of 13 elections; 2018 was the main exception at +0.5). A decay-weighted re-estimate that up-weights recent midterms gives -3.1; adding party in the White House, House incumbency, a second-term flag or a president-specific effect makes out-of-sample prediction worse, so none is used. The bias-adjusted model shifts every race by -2.1 (the estimate less 1 pt because the 2026 aggregators already adjust to likely voters, which ran 1–1.5 pts less Democratic than registered-voter polls in 2020/2022). The scenario column applies the full -3.1. Details: `src/model/bias_decay.py`, `data/processed/bias_decay.json`.
- **State-level poll misses.** Since 2010, results have landed further toward a state's partisan lean than final poll averages (about 0.08 pts per point of lean, symmetric in red and blue states; a real-time 2014–2022 backtest improved race-level RMSE from 5.6 to 5.3). This is an outcome-based pattern, not a test of differential non-response by party: no source here records response rates. Not applied in the published models; `APPLY_LEAN_CORRECTION` in `src/model/forecast.py`.
- **Michigan**: Haley Stevens endorsed Mike Rogers on Nov 1, after most polls were taken. Not modeled; Silver Bulletin estimates ~1 pt effect.
- **Alaska** uses ranked-choice voting and has multiple 'Dan Sullivan' candidates on the ballot; modeled as a head-to-head.
- **Montana** is a genuine three-way race (Alme R, Bankhead D, Bodnar I); modeled from polls only, best non-R vs. R.
- **Independents**: Osborn (NE) and Achilles (ID) treated as the anti-Republican candidate; control reported both ways. **CA-6** (Kevin Kiley, now independent) is excluded from both parties' House counts.
- **House district leans** are Wikipedia's 2026 PVI on the new lines (mid-decade maps in TX, CA, MO, NC, UT, OH, VA, FL, TN, LA, AL). District error SD 6 pts and incumbency +2.5 pts are assumptions typical of district models. Same-party and uncontested seats are fixed.
- **District polls** (VoteHub, ~180) are sparse and often internal; partisan-sponsored polls are shifted 2 pts against the sponsor and shrunk toward the prior.
- Expert ratings (Cook, Silver) are shown for comparison only and are not model inputs.