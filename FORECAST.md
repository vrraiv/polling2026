# 2026 Midterm Forecast

_Generated 2026-11-01 21:30 from the latest data snapshot. Refresh data + rerun everything: `python src/run_all.py`._

## Topline

| | Polls-only | Polls + fundamentals | Scenario: polls overstate Dems by historical avg |
|---|---|---|---|
| National House environment (two-party) | D+9.0 | D+9.1 | D+6.4 |
| **P(Democratic House majority)** | 92% | 95% | 76% |
| P(Republican House majority) | 8% | 5% | 24% |
| Dem House seats, mean (80% range) | 238 (220–258) | 239 (222–255) | 227 (211–244) |
| **P(Democratic Senate control)** | 70% | 70% | 39% |
| P(Dem control if independents caucus D) | 71% | 71% | 40% |
| P(Republican Senate control) | 29% | 29% | 60% |
| Dem-caucus Senate seats, mean (80% range) | 51.7 (49–55) | 51.7 (49–55) | 49.8 (47–53) |

Democrats need 51 Senate seats for control (VP Vance breaks 50–50 ties); 34 Dem-caucus and 31 Republican seats are not up. Independent candidates (Osborn in NE, Achilles in ID) are counted separately; neither has committed to a caucus.

**Fundamentals sensitivity** (assumed coefficients varied: baseline A ∈ [−6, −2], approval slope B ∈ [0.4, 0.8]): fundamentals-only environment ranges D+5.7 to D+13.0; after blending with polls, D+8.0 to D+10.2, P(D House) 92%–97%, P(D Senate) 66%–73%.

**Benchmark:** Silver Bulletin's FLIPR (Nov 1 free summary) gives Democrats ~95% to win the House with a ~25-seat net gain (≈238 seats); Senate numbers are paywalled (described as a meaningful Democratic edge).

## National inputs

- **Generic ballot**: mean of 5 aggregators on Wikipedia (DDHQ, FiftyPlusOne, NBC, RCP, Silver Bulletin; updated Oct 30), converted to two-party: **D+9.0**. Own average of VoteHub polls (through early Oct, VoteHub stopped tracking): D+8.2.
- **Trump approval**: 36.8% (mean of 8 aggregators).
- **Economy** (FRED, as of 2026-09-01): unemployment 4.2% (-0.1 over 12 months), CPI inflation 4.0% y/y, real disposable income per capita +0.7% y/y.
- **Fundamentals estimate** of the House environment: D+9.3. Blended with polls by inverse variance (70% weight on polls) → D+9.1.
- **Uncertainty** (from 538 poll-vs-result archive, 1998–2022): national generic-ballot miss RMSE 3.6 pts (historical mean -2.7: polls have tended to overstate Democrats); Senate shared miss 3.1; race-level poll-average error 6.2. All errors are fat-tailed (t, 5 df), 40,000 simulations.

## Senate races

Margins are two-party D−R (Montana: best non-R minus R). The forecast blends the poll average (~70% weight when polled) with a structural prior (2×PVI + environment + incumbency).

| Race | Democrat / Ind. | Republican | PVI | Poll avg (n) | Prior | Forecast margin | P(D/I win) polls-only | P(D/I win) +fund | Cook | Silver |
|---|---|---|---|---|---|---|---|---|---|---|
| MA | Ed Markey | John Deaton | D+28.0 | D+32.3 (8) | D+39.1 | D+34.3 | >99% | >99% | Solid D | Solid D |
| RI | Jack Reed | Raymond McKay | D+16.0 | D+25.6 (4) | D+26.9 | D+26.0 | >99% | >99% | Solid D | Solid D |
| NM | Ben Ray Luján | Larry Marker | D+8.0 | D+19.2 (2) | D+19.5 | D+19.3 | 99% | >99% | Solid D | Solid D |
| VA | Mark Warner | Bert Mizusawa | D+6.0 | D+20.2 (2) | D+17.4 | D+19.3 | 99% | 99% | Solid D | Solid D |
| DE | Chris Coons | Michael Katz | D+16.0 | — (0) | D+27.0 | D+27.0 | 99% | 99% | Solid D | Solid D |
| IL | Juliana Stratton | Don Tracy | D+12.0 | D+13.5 (3) | D+21.4 | D+15.9 | 99% | 99% | Solid D | Solid D |
| OR | Jeff Merkley | David Brock Smith | D+16.0 | — (0) | D+27.1 | D+27.1 | 99% | 99% | Solid D | Solid D |
| CO | John Hickenlooper | Mark Baisley | D+12.0 | — (0) | D+23.3 | D+23.3 | 98% | 98% | Solid D | Solid D |
| NJ | Cory Booker | Justin Murphy | D+8.0 | — (0) | D+18.6 | D+18.6 | 97% | 96% | Solid D | Solid D |
| NC | Roy Cooper | Michael Whatley | R+2.0 | D+11.3 (24) | D+7.0 | D+10.1 | 96% | 95% | Likely D (flip) | Solid D (flip) |
| GA | Jon Ossoff | Mike Collins | R+2.0 | D+10.0 (11) | D+9.2 | D+9.7 | 95% | 95% | Likely D | Solid D |
| NH | Chris Pappas | John E. Sununu | D+4.0 | D+7.3 (9) | D+13.0 | D+8.9 | 93% | 93% | Lean D | Likely D |
| MN | Peggy Flanagan | Michele Tafoya | D+6.0 | D+4.0 (6) | D+15.5 | D+7.4 | 90% | 90% | Lean D | Likely D |
| ME | Troy Jackson | Susan Collins | D+8.0 | D+2.7 (18) | D+15.2 | D+6.3 | 86% | 87% | Tossup | Lean D (flip) |
| MI | Abdul El-Sayed | Mike Rogers | D+0.0 | D+4.3 (35) | D+9.3 | D+5.7 | 85% | 85% | Tossup | Likely D |
| OH (sp.) | Sherrod Brown | Jon Husted | R+10.0 | D+4.1 (21) | R+3.3 | D+2.0 | 65% | 65% | Tossup | Lean D (flip) |
| TX | James Talarico | Ken Paxton | R+12.0 | D+2.7 (38) | R+2.7 | D+1.2 | 59% | 59% | Tossup | Lean D (flip) |
| KS | Adam Hamilton | Roger Marshall | R+16.0 | D+3.9 (6) | R+8.7 | D+0.2 | 51% | 52% | Tossup | Lean D (flip) |
| IA | Josh Turek | Ashley Hinson | R+12.0 | D+0.1 (21) | R+2.9 | R+0.8 | 44% | 44% | Tossup | Tossup |
| AK | Mary Peltola | Dan S. Sullivan | R+12.0 | D+0.6 (8) | R+4.9 | R+1.0 | 43% | 43% | Tossup | Tossup |
| SC | Annie Andrews | Darline Graham | R+16.0 | R+2.3 (4) | R+9.1 | R+4.4 | 22% | 22% | Lean R | Lean R |
| NE | Dan Osborn (I) | Pete Ricketts | R+20.0 | R+2.1 (4) | R+12.8 | R+5.3 | 17% | 18% | Lean R | Lean R |
| FL (sp.) | Angie Nixon | Ashley Moody | R+10.0 | R+6.6 (15) | R+2.6 | R+5.5 | 16% | 16% | Likely R | Likely R |
| MT | Alani Bankhead | Kurt Alme | R+20.0 | R+10.0 (6) | R+10.9 | R+10.0 | 10% | 10% | Solid R | Likely R |
| LA | Jamie Davis | Julia Letlow | R+22.0 | — (0) | R+12.9 | R+12.9 | 9% | 9% | Solid R | Likely R |
| MS | Scott Colom | Cindy Hyde-Smith | R+22.0 | R+4.8 (2) | R+15.0 | R+8.2 | 9% | 9% | Likely R | Solid R |
| KY | Charles Booker | Andy Barr | R+30.0 | — (0) | R+20.7 | R+20.7 | 2% | 3% | Solid R | Solid R |
| ID | Todd Achilles (I) | Jim Risch | R+36.0 | R+6.2 (1) | R+28.8 | R+14.2 | 2% | 2% | Solid R | Solid R |
| OK | N'Kiyla Jasmine Thomas | Kevin Hern | R+34.0 | — (0) | R+24.4 | R+24.4 | 1% | 2% | Solid R | Solid R |
| SD | Brian Bengs (I) | Mike Rounds | R+30.0 | R+12.1 (4) | R+22.8 | R+16.2 | 1% | 1% | Solid R | Solid R |
| AR | Hallie Shoffner | Tom Cotton | R+30.0 | R+13.0 (4) | R+22.9 | R+16.0 | 1% | 1% | Solid R | Solid R |
| AL | Everett Wess | Barry Moore | R+30.0 | R+16.5 (5) | R+20.4 | R+17.8 | 1% | 1% | Solid R | Solid R |
| WV | Rachel Fetty Anderson | Shelley Moore Capito | R+42.0 | — (0) | R+34.9 | R+34.9 | <1% | <1% | Solid R | Solid R |
| WY | James W. Byrd | Harriet Hageman | R+46.0 | — (0) | R+36.9 | R+36.9 | <1% | <1% | Solid R | Solid R |
| TN | Marquita Bradshaw | Bill Hagerty | R+28.0 | R+24.4 (1) | R+20.8 | R+23.1 | <1% | <1% | Solid R | Solid R |

## Competitive House seats

67 seats have a Democratic win probability between 10% and 90% (polls+fundamentals). Full table: `data/processed/house_polls_fundamentals.csv`.

| District | Incumbent (party) | PVI | Open? | District poll avg | Forecast margin | P(D win) polls-only | P(D win) +fund |
|---|---|---|---|---|---|---|---|
| MI-7 | Tom Barrett (R) | EVEN |  | D+6.8 | D+6.7 | 88% | 90% |
| TX-34 | Vicente Gonzalez (D) | R+3 |  | D+7.2 | D+6.2 | 87% | 88% |
| AZ-1 | David Schweikert (R) | R+1 | open | D+4.0 | D+6.0 | 86% | 88% |
| NY-17 | Mike Lawler (R) | D+1 |  | D+1.0 | D+6.0 | 86% | 88% |
| CO-8 | Gabe Evans (R) | EVEN |  | — | D+6.6 | 85% | 87% |
| AZ-6 | Juan Ciscomani (R) | EVEN |  | — | D+6.6 | 85% | 86% |
| NJ-7 | Thomas Kean Jr. (R) | EVEN |  | — | D+6.6 | 85% | 86% |
| PA-7 | Ryan Mackenzie (R) | R+1 |  | D+6.2 | D+5.2 | 83% | 84% |
| NC-1 | Don Davis (D) | R+5 |  | D+10.9 | D+4.7 | 80% | 82% |
| FL-25 | Jared Moskowitz (D) | R+3 |  | D+1.6 | D+4.3 | 78% | 80% |
| FL-14 | Kathy Castor (D) | R+4 |  | D+5.5 | D+4.2 | 78% | 80% |
| PA-1 | Brian Fitzpatrick (R) | D+1 |  | R+5.0 | D+4.1 | 77% | 79% |
| WA-3 | Marie Gluesenkamp Perez (D) | R+2 |  | R+2.9 | D+4.1 | 77% | 79% |
| VA-2 | Jen Kiggans (R) | EVEN |  | R+4.0 | D+3.1 | 71% | 73% |
| MI-10 | John James (R) | R+3 | open | — | D+3.1 | 69% | 70% |
| IA-3 | Zach Nunn (R) | R+2 |  | — | D+2.6 | 66% | 68% |
| NC-11 | Chuck Edwards (R) | R+5 |  | D+13.1 | D+2.1 | 65% | 67% |
| IA-2 | Ashley Hinson (R) | R+4 | open | D+2.7 | D+1.6 | 61% | 63% |
| IA-1 | Mariannette Miller-Meeks (R) | R+4 |  | D+6.7 | D+1.3 | 59% | 60% |
| ME-2 | Jared Golden (D) | R+4 | open | — | D+1.1 | 57% | 58% |
| MT-1 | Ryan Zinke (R) | R+5 | open | D+4.5 | D+0.9 | 56% | 57% |
| FL-22 | None (new seat) (O) | R+4 | open | D+0.0 | D+0.7 | 55% | 56% |
| OH-7 | Max Miller (R) | R+5 |  | D+7.7 | D+0.7 | 55% | 56% |
| TX-35 | None (new seat) (O) | R+4 | open | R+0.1 | D+0.7 | 55% | 56% |
| WI-3 | Derrick Van Orden (R) | R+3 |  | — | D+0.6 | 53% | 55% |
| PA-10 | Scott Perry (R) | R+3 |  | — | D+0.6 | 53% | 55% |
| MI-4 | Bill Huizenga (R) | R+3 |  | — | D+0.6 | 54% | 55% |
| WI-1 | Bryan Steil (R) | R+2 |  | R+3.4 | D+0.5 | 53% | 54% |
| PA-8 | Rob Bresnahan (R) | R+4 |  | D+4.0 | D+0.4 | 53% | 54% |
| VA-1 | Rob Wittman (R) | R+3 |  | R+0.7 | D+0.2 | 51% | 51% |
| OH-9 | Marcy Kaptur (D) | R+5 |  | R+4.0 | R+0.2 | 48% | 48% |
| FL-7 | Cory Mills (R) | R+5 | open | — | R+0.9 | 44% | 44% |
| MO-2 | Ann Wagner (R) | R+4 |  | D+0.1 | R+0.9 | 43% | 44% |
| OH-10 | Mike Turner (R) | R+4 |  | R+0.7 | R+1.2 | 41% | 41% |
| NY-1 | Nick LaLota (R) | R+4 |  | — | R+1.4 | 40% | 41% |
| TX-15 | Monica De La Cruz (R) | R+7 |  | D+8.1 | R+1.8 | 36% | 36% |
| AL-2 | Shomari Figures (D) | R+7 |  | R+2.1 | R+2.3 | 33% | 32% |
| KY-6 | Andy Barr (R) | R+7 | open | D+1.6 | R+2.6 | 31% | 30% |
| SC-1 | Nancy Mace (R) | R+6 | open | R+2.0 | R+2.6 | 31% | 30% |
| OH-15 | Mike Carey (R) | R+5 |  | R+1.5 | R+2.7 | 30% | 29% |
| FL-4 | Aaron Bean (R) | R+5 |  | — | R+3.4 | 28% | 28% |
| CO-5 | Jeff Crank (R) | R+5 |  | — | R+3.4 | 29% | 28% |
| WA-5 | Michael Baumgartner (R) | R+5 |  | — | R+3.4 | 28% | 28% |
| CO-3 | Jeff Hurd (R) | R+5 |  | R+2.9 | R+3.2 | 27% | 27% |
| FL-9 | Darren Soto (D) | R+8 |  | — | R+4.4 | 23% | 23% |
| MN-1 | Brad Finstad (R) | R+6 |  | R+1.5 | R+4.0 | 22% | 22% |
| FL-11 | Daniel Webster (R) | R+7 | open | — | R+4.9 | 21% | 21% |
| AZ-2 | Eli Crane (R) | R+7 |  | D+2.0 | R+4.2 | 21% | 21% |
| TX-23 | Vacant (O) | R+7 | open | R+4.0 | R+4.6 | 20% | 19% |
| FL-13 | Anna Paulina Luna (R) | R+6 |  | R+3.2 | R+4.6 | 19% | 19% |
| NC-3 | Greg Murphy (R) | R+6 |  | — | R+5.4 | 19% | 18% |
| NY-2 | Andrew Garbarino (R) | R+6 |  | — | R+5.4 | 19% | 18% |
| FL-16 | Vern Buchanan (R) | R+6 | open | R+8.9 | R+4.9 | 18% | 18% |
| NE-1 | Mike Flood (R) | R+6 |  | R+4.1 | R+4.9 | 18% | 17% |
| VA-5 | John McGuire (R) | R+6 |  | R+5.2 | R+5.3 | 16% | 16% |
| FL-27 | María Elvira Salazar (R) | R+6 |  | R+5.1 | R+5.3 | 16% | 16% |
| NV-2 | Mark Amodei (R) | R+7 | open | R+6.2 | R+5.3 | 17% | 15% |
| TX-32 | None (new seat) (O) | R+8 | open | — | R+6.9 | 14% | 13% |
| GA-1 | Buddy Carter (R) | R+8 | open | — | R+6.9 | 13% | 13% |
| FL-2 | Neal Dunn (R) | R+8 | open | — | R+6.9 | 13% | 13% |
| SC-2 | Joe Wilson (R) | R+7 |  | — | R+7.4 | 12% | 12% |
| NC-7 | David Rouzer (R) | R+7 |  | — | R+7.4 | 12% | 12% |
| GA-12 | Rick Allen (R) | R+7 |  | — | R+7.4 | 12% | 11% |
| FL-21 | Brian Mast (R) | R+7 |  | — | R+7.4 | 12% | 11% |
| FL-26 | Mario Díaz-Balart (R) | R+7 |  | — | R+7.4 | 12% | 11% |
| MN-8 | Pete Stauber (R) | R+7 |  | — | R+7.4 | 12% | 11% |
| FL-12 | Gus Bilirakis (R) | R+7 |  | — | R+7.4 | 12% | 11% |

_PVI column in the House table is Cook-style share PVI (district vs. nation); in the Senate table it is shown as the implied margin (2×PVI)._

## Backtest (2018 & 2022, poll-average component)

- **2018 Senate**: 30 races, winner called correctly 93%, Brier 0.048, mean error -0.3 (D−R), MAE 5.6. Misses: Florida (polls D+1.1, actual R+0.1), Indiana (polls D+0.5, actual R+5.9)
- **2022 Senate**: 28 races, winner called correctly 96%, Brier 0.042, mean error -1.8 (D−R), MAE 4.6. Misses: Nevada (polls R+0.1, actual D+0.8)
- **2018 generic ballot**: my average D+8.4 vs. actual House vote D+8.5 (error +0.1).
- **2022 generic ballot**: my average R+0.0 vs. actual House vote R+2.6 (error -2.6).
- Calibration: races given 90%+ went 24/24; 70–90% went 6/6; the model was, if anything, slightly under-confident. Caveat: error scales were estimated on data that include these cycles (in-sample).

## Caveats and judgment calls

- **Fundamentals coefficients are assumed, not estimated.** Two midterms can't identify them and keyless historical approval data wasn't available (UCSB tables are JavaScript-rendered; MEDSL now requires a guestbook form). Formula: president's-party House margin = −4 + 0.6×(approval − 45) + 0.5×(real disposable income growth − 1.5). It happens to land within 0.3 pts of the polls this year, so the two models nearly agree. State economics enter the Senate prior only as a small adjustment (0.5 pts per point of state-vs-national change in unemployment).
- **Polling bias scenario**: final generic-ballot averages have overstated Democrats by 2.7 pts on average since 1998 (but were accurate in 2018). The third column shifts every race by that amount.
- **Michigan**: Haley Stevens endorsed Mike Rogers on Nov 1, after most polls were taken. Not modeled; Silver Bulletin estimates ~1 pt effect.
- **Alaska** uses ranked-choice voting and has multiple 'Dan Sullivan' candidates on the ballot; modeled as a head-to-head.
- **Montana** is a genuine three-way race (Alme R, Bankhead D, Bodnar I); modeled from polls only, best non-R vs. R.
- **Independents**: Osborn (NE) and Achilles (ID) treated as the anti-Republican candidate; control reported both ways. **CA-6** (Kevin Kiley, now independent) is excluded from both parties' House counts.
- **House district leans** are Wikipedia's 2026 PVI on the new lines (mid-decade maps in TX, CA, MO, NC, UT, OH, VA, FL, TN, LA, AL). District error SD 6 pts and incumbency +2.5 pts are assumptions typical of district models. Same-party and uncontested seats are fixed.
- **District polls** (VoteHub, ~180) are sparse and often internal; partisan-sponsored polls are shifted 2 pts against the sponsor and shrunk toward the prior.
- Expert ratings (Cook, Silver) are shown for comparison only and are not model inputs.