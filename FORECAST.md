# 2026 Midterm Forecast

_Generated 2026-11-03 16:08 from the latest data snapshot. Refresh data + rerun everything: `python src/run_all.py`._

## Topline

| | Polls-only | Polls + fundamentals (unadjusted) | Polls + fundamentals, bias-adjusted (-2.6 national, state-lean term) |
|---|---|---|---|
| National House environment (two-party) | D+9.0 | D+9.6 | D+7.4 |
| **P(Democratic House majority)** | 93% | 97% | 92% |
| P(Republican House majority) | 7% | 3% | 8% |
| Dem House seats, mean (80% range) | 236 (219–253) | 237 (224–252) | 228 (218–239) |
| **P(Democratic Senate control)** | 77% | 78% | 71% |
| P(Dem control if independents caucus D) | 79% | 80% | 73% |
| P(Republican Senate control) | 21% | 20% | 27% |
| Dem-caucus Senate seats, mean (80% range) | 52.3 (49–55) | 52.3 (49–55) | 51.7 (48–55) |

Democrats need 51 Senate seats for control (VP Vance breaks 50–50 ties); 34 Dem-caucus and 31 Republican seats are not up. Independent candidates (Osborn in NE, Achilles in ID) are counted separately; neither has committed to a caucus.

**Fundamentals sensitivity** (each of the ten top estimated specifications, both samples): fundamentals-only environment ranges D+8.0 to D+11.8; after blending with polls, D+8.5 to D+10.2, P(D House) 95%–97%, P(D Senate) 77%–78%.

## National inputs

- **Generic ballot**: mean of 5 aggregators on Wikipedia (DDHQ, FiftyPlusOne, NBC, RCP, Silver Bulletin; updated Oct 30), converted to two-party: **D+9.0**. Own average of VoteHub polls (through early Oct, VoteHub stopped tracking): D+8.4.
- **Trump approval**: 36.8% (mean of 8 aggregators).
- **Economy** (FRED, as of 2026-09-01): unemployment 4.2% (-0.1 over 12 months), CPI inflation 4.0% y/y, real disposable income per capita +0.7% y/y.
- **Real gas prices** +29.3% y/y (Sept; gasoline CPI ÷ CPI-U); **CPI inflation** 3.7% (Sept/Sept, unrevised CPI-U).
- **Fundamentals estimate** (estimated on 1962–2022; top specifications averaged, LOO RMSE 3.9, SD used 4.5): D+10.4. Blended with polls by inverse variance (56% weight on polls) → D+9.6.
- **Uncertainty** (from 538 poll-vs-result archive, 1998–2022): national generic-ballot miss RMSE 4.0 pts (historical mean -2.9: polls have tended to overstate Democrats); Senate shared miss 3.3; race-level poll-average error 7.4. All errors are fat-tailed (t, estimated df), 40,000 simulations.

## Senate races

Margins are two-party D−R (Montana: best non-R minus R). The forecast blends the poll average (on average 85% weight in polled races) with a structural prior (2×PVI + environment + incumbency). Nationally, polls get 56% of the weight vs. the fundamentals.

| Race | Democrat / Ind. | Republican | PVI | Poll avg (n) | Prior | Forecast margin | P(D/I win) polls-only | P(D/I win) +fund | Cook | Silver |
|---|---|---|---|---|---|---|---|---|---|---|
| MA | Ed Markey | John Deaton | D+28.0 | D+30.5 (9) | D+39.6 | D+31.4 | >99% | >99% | Solid D | Solid D |
| RI | Jack Reed | Raymond McKay | D+16.0 | D+27.0 (5) | D+27.6 | D+27.1 | >99% | >99% | Solid D | Solid D |
| OR | Jeff Merkley | David Brock Smith | D+16.0 | — (0) | D+27.6 | D+27.6 | 99% | 99% | Solid D | Solid D |
| DE | Chris Coons | Michael Katz | D+16.0 | — (0) | D+27.6 | D+27.6 | 99% | 99% | Solid D | Solid D |
| NJ | Cory Booker | Justin Murphy | D+8.0 | — (0) | D+19.6 | D+19.6 | 97% | 97% | Solid D | Solid D |
| NC | Roy Cooper | Michael Whatley | R+2.0 | D+11.3 (26) | D+7.6 | D+11.0 | 97% | 97% | Likely D | Solid D |
| VA | Mark Warner | Bert Mizusawa | D+6.0 | D+20.5 (2) | D+17.6 | D+19.6 | 97% | 97% | Solid D | Solid D |
| IL | Juliana Stratton | Don Tracy | D+12.0 | D+13.9 (3) | D+21.6 | D+15.3 | 97% | 97% | Solid D | Solid D |
| NM | Ben Ray Luján | Larry Marker | D+8.0 | D+18.6 (2) | D+19.6 | D+18.9 | 96% | 97% | Solid D | Solid D |
| CO | John Hickenlooper | Mark Baisley | D+12.0 | D+16.0 (1) | D+23.6 | D+18.4 | 96% | 96% | Solid D | Solid D |
| GA | Jon Ossoff | Mike Collins | R+2.0 | D+9.3 (12) | D+9.6 | D+9.3 | 94% | 94% | Likely D | Solid D |
| NH | Chris Pappas | John E. Sununu | D+4.0 | D+8.1 (12) | D+13.6 | D+8.6 | 93% | 93% | Lean D | Solid D |
| MI | Abdul El-Sayed | Mike Rogers | D+0.0 | D+4.2 (37) | D+9.6 | D+4.5 | 82% | 82% | Lean D | Likely D |
| ME | Troy Jackson | Susan Collins | D+8.0 | D+3.8 (22) | D+15.6 | D+4.6 | 82% | 82% | Tossup | Likely D |
| MN | Peggy Flanagan | Michele Tafoya | D+6.0 | D+3.4 (8) | D+15.6 | D+4.8 | 78% | 79% | Lean D | Likely D |
| OH (sp.) | Sherrod Brown | Jon Husted | R+10.0 | D+4.3 (25) | R+2.4 | D+3.8 | 78% | 78% | Tossup | Lean D |
| KS | Adam Hamilton | Roger Marshall | R+16.0 | D+5.0 (9) | R+8.4 | D+3.8 | 75% | 76% | Tossup | Lean D |
| TX | James Talarico | Ken Paxton | R+12.0 | D+3.2 (40) | R+2.4 | D+2.8 | 72% | 73% | Tossup | Likely D |
| AK | Mary Peltola | Dan S. Sullivan | R+12.0 | D+1.9 (10) | R+4.4 | D+1.2 | 58% | 59% | Tossup | Tossup |
| IA | Josh Turek | Ashley Hinson | R+12.0 | D+0.1 (24) | R+2.4 | R+0.1 | 49% | 49% | Tossup | Tossup |
| SC | Annie Andrews | Darline Graham | R+16.0 | R+1.4 (5) | R+8.4 | R+2.3 | 35% | 36% | Lean R | Lean R |
| NE | Dan Osborn (I) | Pete Ricketts | R+20.0 | R+1.8 (4) | R+12.4 | R+3.5 | 30% | 30% | Lean R | Lean R |
| MS | Scott Colom | Cindy Hyde-Smith | R+22.0 | R+5.7 (2) | R+14.4 | R+7.8 | 16% | 17% | Likely R | Solid R |
| FL (sp.) | Angie Nixon | Ashley Moody | R+10.0 | R+6.6 (16) | R+2.4 | R+6.2 | 13% | 13% | Likely R | Likely R |
| ID | Todd Achilles (I) | Jim Risch | R+36.0 | R+6.2 (1) | R+28.4 | R+13.1 | 8% | 9% | Solid R | Solid R |
| LA | Jamie Davis | Julia Letlow | R+22.0 | — (0) | R+12.4 | R+12.4 | 7% | 8% | Solid R | Likely R |
| MT | Alani Bankhead | Kurt Alme | R+20.0 | R+12.4 (6) | R+10.4 | R+12.4 | 5% | 5% | Solid R | Likely R |
| AR | Hallie Shoffner | Tom Cotton | R+30.0 | R+12.8 (4) | R+22.4 | R+14.3 | 3% | 3% | Solid R | Solid R |
| SD | Brian Bengs (I) | Mike Rounds | R+30.0 | R+13.2 (4) | R+22.4 | R+14.4 | 3% | 3% | Solid R | Solid R |
| KY | Charles Booker | Andy Barr | R+30.0 | — (0) | R+20.4 | R+20.4 | 2% | 2% | Solid R | Solid R |
| TN | Marquita Bradshaw | Bill Hagerty | R+28.0 | R+23.9 (1) | R+20.4 | R+22.8 | 2% | 2% | Solid R | Solid R |
| OK | N'Kiyla Jasmine Thomas | Kevin Hern | R+34.0 | — (0) | R+24.4 | R+24.4 | 1% | 1% | Solid R | Solid R |
| AL | Everett Wess | Barry Moore | R+30.0 | R+17.3 (5) | R+20.4 | R+17.7 | 1% | 1% | Solid R | Solid R |
| WV | Rachel Fetty Anderson | Shelley Moore Capito | R+42.0 | — (0) | R+34.4 | R+34.4 | <1% | <1% | Solid R | Solid R |
| WY | James W. Byrd | Harriet Hageman | R+46.0 | — (0) | R+36.4 | R+36.4 | <1% | <1% | Solid R | Solid R |

## Competitive House seats

62 seats have a Democratic win probability between 10% and 90% (polls+fundamentals). Full table: `data/processed/house_polls_fundamentals.csv`.

| District | Incumbent (party) | PVI | Open? | District poll avg | Forecast margin | P(D win) polls-only | P(D win) +fund |
|---|---|---|---|---|---|---|---|
| NC-1 | Don Davis (D) | R+5 |  | D+10.9 | D+6.6 | 87% | 89% |
| FL-25 | Jared Moskowitz (D) | R+3 |  | D+4.4 | D+6.1 | 85% | 88% |
| FL-14 | Kathy Castor (D) | R+4 |  | D+5.5 | D+5.5 | 83% | 86% |
| AZ-1 | David Schweikert (R) | R+1 | open | D+3.9 | D+5.3 | 82% | 85% |
| WA-3 | Marie Gluesenkamp Perez (D) | R+2 |  | R+0.6 | D+5.0 | 81% | 84% |
| MI-7 | Tom Barrett (R) | EVEN |  | D+5.4 | D+4.5 | 78% | 81% |
| PA-7 | Ryan Mackenzie (R) | R+1 |  | D+5.9 | D+3.7 | 74% | 77% |
| NY-17 | Mike Lawler (R) | D+1 |  | R+0.1 | D+3.1 | 71% | 74% |
| CO-8 | Gabe Evans (R) | EVEN |  | — | D+3.8 | 69% | 73% |
| NJ-7 | Thomas Kean Jr. (R) | EVEN |  | — | D+3.8 | 69% | 73% |
| AZ-6 | Juan Ciscomani (R) | EVEN |  | — | D+3.8 | 69% | 73% |
| PA-1 | Brian Fitzpatrick (R) | D+1 |  | R+2.3 | D+2.4 | 65% | 69% |
| NC-11 | Chuck Edwards (R) | R+5 |  | D+13.1 | D+2.2 | 64% | 67% |
| VA-2 | Jen Kiggans (R) | EVEN |  | R+1.2 | D+1.7 | 60% | 64% |
| OH-9 | Marcy Kaptur (D) | R+5 |  | R+1.2 | D+1.7 | 60% | 63% |
| MT-1 | Ryan Zinke (R) | R+5 | open | D+4.8 | D+1.5 | 59% | 62% |
| IA-2 | Ashley Hinson (R) | R+4 | open | D+2.0 | D+1.5 | 59% | 62% |
| MI-10 | John James (R) | R+3 | open | R+1.2 | D+1.2 | 57% | 59% |
| TX-35 | None (new seat) (O) | R+4 | open | D+0.7 | D+0.9 | 54% | 57% |
| IA-1 | Mariannette Miller-Meeks (R) | R+4 |  | D+6.7 | D+0.6 | 53% | 55% |
| OH-7 | Max Miller (R) | R+5 |  | D+7.9 | D+0.5 | 52% | 54% |
| FL-22 | None (new seat) (O) | R+4 | open | D+0.0 | D+0.6 | 52% | 54% |
| IA-3 | Zach Nunn (R) | R+2 |  | — | D+0.1 | 48% | 51% |
| WI-1 | Bryan Steil (R) | R+2 |  | R+0.7 | R+0.2 | 46% | 48% |
| VA-1 | Rob Wittman (R) | R+3 |  | D+1.7 | R+0.2 | 46% | 48% |
| PA-8 | Rob Bresnahan (R) | R+4 |  | D+4.0 | R+0.4 | 44% | 46% |
| FL-7 | Cory Mills (R) | R+5 | open | — | R+0.8 | 41% | 44% |
| KY-6 | Andy Barr (R) | R+7 | open | D+4.1 | R+0.7 | 42% | 44% |
| AL-2 | Shomari Figures (D) | R+7 |  | R+2.1 | R+0.8 | 42% | 44% |
| TX-15 | Monica De La Cruz (R) | R+7 |  | D+9.0 | R+1.1 | 40% | 41% |
| OH-10 | Mike Turner (R) | R+4 |  | D+2.1 | R+1.2 | 39% | 40% |
| PA-10 | Scott Perry (R) | R+3 |  | — | R+1.7 | 36% | 40% |
| MI-4 | Bill Huizenga (R) | R+3 |  | — | R+1.7 | 37% | 39% |
| WI-3 | Derrick Van Orden (R) | R+3 |  | — | R+1.7 | 36% | 39% |
| FL-9 | Darren Soto (D) | R+8 |  | — | R+1.7 | 36% | 39% |
| ME-2 | Jared Golden (D) | R+4 | open | R+5.1 | R+1.4 | 37% | 39% |
| MO-2 | Ann Wagner (R) | R+4 |  | D+1.3 | R+1.4 | 37% | 39% |
| SC-1 | Nancy Mace (R) | R+6 | open | D+0.1 | R+1.5 | 37% | 38% |
| NY-1 | Nick LaLota (R) | R+4 |  | — | R+3.5 | 28% | 28% |
| TX-23 | Vacant (O) | R+7 | open | R+1.2 | R+3.1 | 26% | 27% |
| CO-3 | Jeff Hurd (R) | R+5 |  | R+0.1 | R+3.2 | 26% | 27% |
| FL-16 | Vern Buchanan (R) | R+6 | open | R+4.4 | R+3.3 | 25% | 26% |
| FL-11 | Daniel Webster (R) | R+7 | open | — | R+4.4 | 23% | 24% |
| OH-15 | Mike Carey (R) | R+5 |  | R+2.0 | R+3.9 | 22% | 22% |
| MN-1 | Brad Finstad (R) | R+6 |  | D+0.3 | R+3.9 | 22% | 22% |
| NV-2 | Mark Amodei (R) | R+7 | open | R+3.4 | R+4.0 | 21% | 22% |
| NE-1 | Mike Flood (R) | R+6 |  | R+0.3 | R+4.2 | 20% | 20% |
| FL-4 | Aaron Bean (R) | R+5 |  | — | R+5.3 | 19% | 20% |
| WA-5 | Michael Baumgartner (R) | R+5 |  | — | R+5.3 | 19% | 20% |
| CO-5 | Jeff Crank (R) | R+5 |  | — | R+5.3 | 19% | 20% |
| AZ-2 | Eli Crane (R) | R+7 |  | D+2.0 | R+4.5 | 19% | 20% |
| FL-2 | Neal Dunn (R) | R+8 | open | — | R+6.2 | 16% | 17% |
| GA-1 | Buddy Carter (R) | R+8 | open | — | R+6.2 | 16% | 17% |
| TX-32 | None (new seat) (O) | R+8 | open | — | R+6.2 | 16% | 16% |
| FL-27 | María Elvira Salazar (R) | R+6 |  | R+2.3 | R+5.2 | 16% | 16% |
| FL-13 | Anna Paulina Luna (R) | R+6 |  | R+2.4 | R+5.1 | 16% | 16% |
| NY-2 | Andrew Garbarino (R) | R+6 |  | — | R+7.1 | 13% | 14% |
| NC-3 | Greg Murphy (R) | R+6 |  | — | R+7.1 | 13% | 14% |
| AR-2 | French Hill (R) | R+8 |  | R+0.2 | R+6.2 | 12% | 12% |
| VA-5 | John McGuire (R) | R+6 |  | R+5.2 | R+6.3 | 12% | 12% |
| TX-9 | None (new seat) (O) | R+9 | open | — | R+8.0 | 11% | 11% |
| NY-21 | Elise Stefanik (R) | R+10 | open | R+1.9 | R+6.6 | 12% | 11% |

_PVI column in the House table is Cook-style share PVI (district vs. nation); in the Senate table it is shown as the implied margin (2×PVI)._

## Backtest (2018 & 2022, poll-average component)

- **2018 Senate**: 30 races, winner called correctly 90%, Brier 0.044, mean error -0.1 (D−R), MAE 5.5. Misses: Florida (polls D+0.5, actual R+0.1), Indiana (polls D+0.6, actual R+5.9), Nevada (polls R+0.5, actual D+5.0)
- **2022 Senate**: 28 races, winner called correctly 100%, Brier 0.035, mean error -2.0 (D−R), MAE 4.7. Misses: 
- **2018 generic ballot**: my average D+7.5 vs. actual House vote D+8.5 (error +1.0).
- **2022 generic ballot**: my average R+1.0 vs. actual House vote R+2.6 (error -1.7).
- Calibration by forecast bin: 0%–10%: forecast 3%, Dems won 0% of 14; 10%–30%: forecast 21%, Dems won 0% of 4; 30%–50%: forecast 41%, Dems won 25% of 4; 50%–70%: forecast 56%, Dems won 60% of 5; 70%–90%: forecast 85%, Dems won 100% of 5; 90%–100%: forecast 98%, Dems won 100% of 26. The middle bins resolve more decisively than forecast, i.e. the model is somewhat under-confident with the two-party error scales. Caveat: error scales were estimated on data that include these cycles (in-sample).

## Caveats and judgment calls

- **Fundamentals are estimated** (`src/model/fundamentals.py`): president's-party House margin on Gallup approval, the previous House margin, real gas-price change, inflation, real income growth and unemployment change; every subset of up to 4 predictors scored by leave-one-out RMSE, top five averaged. Best specification: const -10.72 (±3.33), approval +0.26 (±0.07), prev +0.79 (±0.11), gas -0.08 (±0.05), midterm -8.96 (±1.59). Inflation adds nothing once approval is in; real gas has the expected sign but is only ~1.5 SE from zero. 2026 approval and the gas-price rise are both outside the 1962–2022 range, so the estimate extrapolates. Unemployment (12-month change and level) was tested nationally: both are weak (coefficients within ~1.5 SE of zero) and enter only as minor terms in the averaged model.
- **State unemployment** (`src/model/state_econ.py`, 584 Senate/governor races 1998–2022). Relative to state lean and the national environment, a worse local job trend is associated with -1.71 pts for Democrats-under-a-Republican-president (cluster SE 1.29; wrong sign, no held-out gain), so the Senate prior uses 0.0. As a correction to poll averages the effect is +0.78 (SE 0.39), but it improves held-out error by only 0.1%, so it is not applied.
- **Polls vs. partisanship (Senate).** On 328 races 1998–2022, the optimal weight on final-three-week polls vs. a lean + environment prior is 0.87 (SE 0.05); the prior's errors are fat-tailed (robust SD 9.7, SD 16.4). Polled races use prior SD 18.7 (≈0.87 weight on polls); unpolled races use 9.7. Previously an assumed 10 for both (0.64 weight). See `src/model/prior_weight.py`.
- **House district model (estimated)** on 3752 contested races 2006–2024: margin = 0.75 + 0.91×(2×PVI) + 0.78×national ± 4.5 incumbency; district SD 7.4; district polls get ~0.46 weight (poll SD 8.1). Incumbency fell from ~20 pts (2006) to ~4 (2018–2024). Expected-seat RMSE over 2006–2024: 6.7 vs 11.9 for the old assumed model; recent cycles undercount Democratic contested-seat wins by ~6.
- **Is the bias adjustment justified?** Polls overstated Democrats in 11 of 14 elections 1998–2024 (mean -3.1, predictive SD 2.5; P(overstate again) 88%); LV-only polls 2018–2024 averaged -2.3; Senate polls missed against Democrats in all five cycles since 2014 (mean -3.7). Nothing observable predicts the size. This year's generic-ballot pollsters are a typical mix (house effect -0.06); the battleground Senate pollsters lean slightly Republican (-0.52; historical miss -1.9). The Bias-adjusted model: national shift -2.55 (estimate + LV discount 0.38), Senate shift +0.00 (battleground pollsters' record + discount) plus the state-lean term. The Senate moves ~10 pts of control probability per point of national shift because five races in R-leaning states sit within 3 pts of even.
- **Poll-averaging settings (estimated, `src/model/poll_settings.py`)**: sponsor shift by pollster track record (see pollster_effects.json: ~1.2 pts for established pollsters, ~4 for firms without a record); population weights RV 0.69, adults 0.5, with RV/adult polls shifted 0.45 pts toward Democrats (paired LV-vs-RV surveys, historical prior + 2026 pairs); half-life 60 days (backtest prefers no decay); t with 3.9 df.
- **Correlated errors.** Beyond the shared national miss, each simulation draws a Census-region shock (SD 0.5) and a random slope on state lean (SD 0.078 per point), with each race's total variance held fixed. The regional component is small in 1998–2022 data; a 2-pt regional sensitivity moves Senate control by about 1 point (see `data/processed/error_sensitivity.json`).
- **Polling bias.** On a two-party basis, final generic-ballot averages overstated Democrats by 3.1 pts on average over 1998–2022 (9 of 13 elections; 2018 was the main exception at +0.5). A decay-weighted re-estimate that up-weights recent midterms gives -2.9; adding party in the White House, House incumbency, a second-term flag or a president-specific effect makes out-of-sample prediction worse, so none is used. The bias-adjusted model shifts the generic-ballot polls by -2.6 (the estimate plus the estimated likely-voter discount). In a real-time test (estimate from earlier elections only), this shift cut generic-ballot error from 3.91 to 2.87 pts (3.68 to 2.31 in midterms). A Senate-wide shift on Senate race polls did not pass the same test (midterm cycle error 3.05 to 3.30), so Senate polls are not shifted. Details: `src/model/bias_realtime.py`, `data/processed/bias_realtime.json`.
- **State-level poll misses.** Since 2010, results have landed further toward a state's partisan lean than final poll averages (about 0.08 pts per point of lean, symmetric in red and blue states). In a real-time Senate test the lean term cut competitive-race error from 4.53 to 4.06 pts, improving 6 of 6 test years. Applied in the bias-adjusted model. This is an outcome-based pattern, not a test of differential non-response by party: no source here records response rates.
- **Michigan**: Haley Stevens endorsed Mike Rogers on Nov 1, after most polls were taken. Not modeled; Silver Bulletin estimates ~1 pt effect.
- **Alaska** uses ranked-choice voting and has multiple 'Dan Sullivan' candidates on the ballot; modeled as a head-to-head.
- **Montana** is a genuine three-way race (Alme R, Bankhead D, Bodnar I); modeled from polls only, best non-R vs. R.
- **Independents**: Osborn (NE) and Achilles (ID) treated as the anti-Republican candidate; control reported both ways. **CA-6** (Kevin Kiley, now independent) is excluded from both parties' House counts.
- **House district leans** are Wikipedia's 2026 PVI on the new lines (mid-decade maps in TX, CA, MO, NC, UT, OH, VA, FL, TN, LA, AL). District error SD 6 pts and incumbency +2.5 pts are assumptions typical of district models. Same-party and uncontested seats are fixed.
  *Correction (Nov 8, 2026): the sentence on district error SD and incumbency is out of date; it described the House model before it was estimated. The final forecast used the estimated values in "House district model (estimated)" above: district SD 7.4 and incumbency ±4.5 (see `data/final/house_structure.json`; e.g. `prior_inc` in `data/final/house_polls_fundamentals.csv`). The frozen copy, `data/final/FORECAST.md`, keeps the original wording, as does `src/model/report.py`, so that `check_frozen.py` can still compare rebuilds against it.*
- **District polls** (VoteHub, ~180) are sparse and often internal; partisan-sponsored polls are shifted against the sponsor (estimated: 6.3 pts for districts) and shrunk toward the prior.
- Expert ratings (Cook, Silver) are shown for comparison only and are not model inputs.