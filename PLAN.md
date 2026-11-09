# polling2026: 2026 Midterm Forecast, Data Collection Plan

_Written 2026-11-01. Election Day is **Tuesday, 2026-11-03**._

> **Status (2026-11-01 evening):** First forecast built. See `FORECAST.md`. Source notes from collection:
> - VoteHub stopped tracking the generic ballot and approval after June 2026. Those inputs come from Wikipedia's aggregator tables instead (DDHQ, FiftyPlusOne, NBC, RCP, Silver Bulletin, and others).
> - BLS flat files return 403 to scripts. State unemployment comes from FRED `<ST>UR` instead, and state income from FRED `<ST>PCPI` / `<ST>OTOT`.
> - MEDSL Dataverse downloads now require a guestbook form (personal details), so it was not used. Past results come from 538 `raw_polls.csv` actuals.
> - Wikipedia's 2026 House page provides 2026 PVI for all 435 districts on the new lines.
> - Live site: https://polling2026.vikramrai.com (Cloudflare Worker `polling2026`, rebuilt on every push to `main`). Headline models: unadjusted and bias-adjusted; see `src/model/bias_decay.py`.
> - Keys in `.env` (`fec_api_key`, `bea_api_key`) are loaded by `src/collect/common.py:env_key`.

## Goal

Forecast 2026 U.S. House and Senate outcomes (seat totals plus per-race win probabilities) with two models:

1. **Polls-only**: race polls, generic ballot, and district partisanship (the House needs a structural baseline because district polls are sparse).
2. **Polls + fundamentals**: model 1 plus national and state economic conditions, presidential approval, incumbency, candidate quality, and money.

Backtest both on the 2018 and 2022 midterms, then score them against the 2026 results.

## Timing (the hard constraint)

The election is about 48 hours away. Pollsters stop releasing and some averages freeze or disappear after Election Day, so the 2026 polling snapshot comes first. Everything historical can wait.

| Phase | When | Work |
|---|---|---|
| **0: Snapshot** | **Now (Nov 1–2)** | Pull and timestamp all 2026 polls, approval, generic ballot, FEC totals, expert ratings, candidate lists |
| 1: Historical | Nov 2–3 | 2018/2022 polls, results, ALFRED economic vintages |
| 2: Fundamentals | Nov 2–3 | National and state economics for 2018, 2022, and 2026; incumbency; district lean on the new maps |
| 3: Model | Nov 2–3 (quick version) / after (full version) | Polls-only model, then polls + fundamentals, with a backtest |
| 4: Score | After Nov 3 | Ingest 2026 results; Brier score, log loss, seat error |

**Decision needed:** do you want (a) a quick pre-election call by Nov 3, or (b) a properly built model scored against the 2026 results afterward? Phase 0 is the same either way.

## Sources

Status as of 2026-11-01: **verified** = I fetched it and checked its contents; **reachable** = it responds but I didn't inspect the contents in detail; **unverified** = not tested.

### Polling

| Data | Source | Access | Status | Notes |
|---|---|---|---|---|
| 2026 Senate, governor, generic ballot, Trump approval polls | VoteHub API `https://api.votehub.com/polls` | JSON, no key | **verified** | About 6,050 polls, latest ending 2026-10-30. Fields: pollster, dates, sample size, population (lv/rv/a), sponsors, internal/partisan flags. Includes 547 generic-ballot and about 1,000 Trump approval polls. **Primary 2026 source.** |
| 2026 averages: generic ballot, Trump approval, possibly Senate races | **Silver Bulletin** (Nate Silver's Substack). The closest current analog to 538. | Browser (Chrome) using your own login if posts are paywalled; check whether any CSVs are published | unverified | Primary **benchmark** and averaging reference for the current cycle. Polls-only output should be compared against it. Raw poll lists may sit behind a subscription. |
| 2018, 2020, 2022, 2024 Senate polls (full cycle) | 538 `senate_polls_historical.csv` via the Wayback Machine (2025-02 snapshot) | CSV (`web.archive.org/web/<ts>id_/...`) | **verified** | 2,016 polls for 2018 and 2,089 for 2022. Full 538 schema (pollster rating, methodology, population, partisan, race_id). 538 itself is shut down; `projects.fivethirtyeight.com` now redirects to ABC News. |
| 2018/2022 House district polls, generic ballot, presidential approval | 538 `house_polls_historical.csv`, `generic_ballot_polls_historical.csv`, `president_approval_polls_historical.csv` via Wayback | CSV | Wayback snapshots exist; contents unverified | Same schema as the Senate file |
| Final-21-day polls with actual results, 2018/2022 | 538 GitHub `pollster-ratings/raw_polls.csv` | CSV, raw.githubusercontent | **verified** | Includes `margin_actual`. Useful for estimating polling error by race type and for house effects. |
| Historical generic-ballot topline | 538 GitHub `congress-generic-ballot/generic_topline_historical.csv` | CSV | reachable | |
| 538 pollster ratings | 538 GitHub `pollster-ratings/pollster-ratings-combined.csv` | CSV | reachable | Frozen at 2024; usable as pollster-quality weights |
| 2026 House district polls | VoteHub (check for a House poll type); Wikipedia race pages | API / page scrape | unverified | Expect sparse coverage. Wikipedia has no single 2026 House or Senate polling page; polls are on per-race pages. |
| Cross-check aggregates | RealClearPolling, DDHQ/The Hill, NYT | Browser | RCP returns **403** to scripts | Use only as a benchmark; their terms limit scraping. Use Chrome manually if needed. |

### Results (training targets)

| Data | Source | Access | Status |
|---|---|---|---|
| House returns 1976–2024 by district | MEDSL, Harvard Dataverse `doi:10.7910/DVN/IG0UN2` | Dataverse API | **verified** (`1976-2024-house.tab`) |
| Senate returns 1976–2024 by state | MEDSL, Dataverse `doi:10.7910/DVN/PEJ5QU` | Dataverse API | **verified** (`1976-2024-senate-state.tab`) |
| 2026 results | AP/state SOS pages, Wikipedia; MEDSL later | Scrape after Nov 3 | Phase 4 |

### Economics

| Data | Series | Source | Status |
|---|---|---|---|
| National: unemployment, real GDP growth, real disposable personal income per capita, CPI inflation, consumer sentiment, gas price | `UNRATE`, `A191RL1Q225SBEA`, `A229RX0`, `CPIAUCSL`, `UMCSENT`, `GASREGW` | FRED keyless CSV `fred.stlouisfed.org/graph/fredgraph.csv?id=…` | Endpoint **verified** with `UNRATE` (through 2026-09); the other series IDs are unverified |
| **As-published vintages** for the 2018/2022 backtest | Same series with `vintage_date=` | ALFRED `alfred.stlouisfed.org/graph/alfredgraph.csv` | **verified** |
| State unemployment (monthly) | LAUS `la.data.3.AllStatesS` | BLS flat files (requires a User-Agent with contact email) | reachable (HTTP 200 with UA; 403 without; contents not inspected) |
| State personal income (quarterly) | BEA SQINC | BEA API (key) or FRED state series (e.g. `CAPI`) | unverified |
| State inflation | None exists | Use the 4 Census-region CPIs or metro CPIs | **No state-level CPI.** This is a known gap. |

### Other factors

| Factor | Source | Status |
|---|---|---|
| Presidential approval (Trump 2026; Trump 2018; Biden 2022) | VoteHub (2026), archived 538 approval file (2018/2022), Gallup | VoteHub verified |
| Candidates, incumbency, open seats | FEC API `api.open.fec.gov` (DEMO_KEY works; rate-limited) plus Wikipedia retirement lists | **verified** (685 Senate candidates for 2026) |
| Fundraising (receipts, cash on hand, outside spending) | FEC API `/candidates/totals`, `/schedules/schedule_e` | endpoint verified |
| District partisanship (presidential vote by district) | The Downballot / Daily Kos Elections district data; Dave's Redistricting | unverified |
| Mid-decade redistricting | Wikipedia "2025–2026 United States redistricting" lists passed plans in **TX, CA, MO, NC, UT, OH, VA, FL, TN, LA, AL** | Must confirm each map is in effect for 2026 (litigation, the VA referendum, *Louisiana v. Callais*) |
| Senate map | Wikipedia: 33 regular seats + **Florida special + Ohio special** = 35 races | Verify the final ballot list |
| Candidate quality | Prior elected office (hand-coded from Wikipedia/Ballotpedia) | Manual |
| Special-election swing, 2025–26 | Wikipedia / The Downballot special-election tracker | unverified |
| Expert ratings (Cook, Sabato, Inside Elections) | Sites, via Chrome | **Benchmark only, not a model input** |

### API keys you'll need to get (I can't create accounts)

- **FEC**: DEMO_KEY works for light use; a free key from api.data.gov raises the rate limit.
- **BEA**: free key, only if using the BEA API for state income.
- **FRED**: not needed for CSV downloads; only for the JSON API.

Store keys in a `.env` file. Add `.env` to `.gitignore` and never commit it.

## Data design

- **Race key**: `cycle|state|office|district` (e.g. `2026|TX|H|28`, `2026|OH|S|special`). Never join on district number alone; numbers point to different places after redistricting.
- **Raw is immutable**: `data/raw/<source>/<YYYY-MM-DD>/…`, with the retrieval timestamp and URL in a sidecar `manifest.json`.
- **Polls schema, all cycles**: `poll_id, race_key, pollster, sponsor, partisan, internal, start_date, end_date, sample_size, population (lv/rv/a), mode, candidate, party, pct`. 538 and VoteHub map onto this.
- **Race-format edge cases**:
  - Independents (e.g. the Nebraska Senate race): add a `caucus_with` field so the control math counts them correctly.
  - CA and WA top-two generals: same-party races have no D/R margin.
  - ME and AK ranked-choice voting: model the final-round result.
  - Runoffs (GA in December; check LA): the Election Night result may not be final.
  - Uncontested House seats in MEDSL: flag them, then exclude or impute before fitting district lean.
- **No look-ahead in the backtest**: 2018/2022 fundamentals use ALFRED vintages as of about Oct 1 of each year, and only polls with `end_date` before that cycle's cutoff.

```
data/raw/        untouched downloads, dated
data/interim/    normalized to the common schema
data/processed/  model-ready race tables
src/collect/     one script per source
src/model/       polls_only.py, fundamentals.py, simulate.py
notebooks/       exploration and backtests
```

## Modeling notes

- **Two midterms can't fit a fundamentals model.** Fit the national midterm-swing equation (seat or vote change vs. approval, real income growth, and the president's party) on 1946–2022 midterms. Use 2018 and 2022 as holdout tests, not as the training set.
- **House**: district vote = district lean (new lines) + national environment (generic ballot, polls-only; generic ballot blended with fundamentals in model 2) + incumbency + candidate quality, with district polls blended in where they exist.
- **Senate**: weighted poll average per race (recency, sample size, pollster rating, house effects, LV adjustment), shrunk toward a prior (state lean + national environment, plus fundamentals in model 2).
- **Simulation**: correlated errors (national + regional + race) estimated from 2018/2022 poll-vs-result misses (`raw_polls.csv`). About 10,000 draws produce seat distributions and control probabilities.
- **Python**: only 3.14 is installed. Some scientific packages may not ship 3.14 wheels yet, so create a 3.12 or 3.13 venv if installs fail.

## Browser use

Use direct downloads and APIs wherever possible. Use Chrome only for sources with no export (expert ratings, RCP cross-checks, some Wikipedia tables if the API parse falls short), and keep that light given aggregators' terms of service.

## Immediate next steps (Phase 0)

1. `src/collect/votehub.py`: snapshot all VoteHub polls to `data/raw/votehub/2026-11-01/`.
2. `src/collect/fec.py`: 2026 House and Senate candidates and totals.
3. Snapshot the Wikipedia Senate race list, retirements, and redistricting status.
4. Snapshot Silver Bulletin's current averages and expert ratings via Chrome (benchmarks).
5. Pull the archived 538 historical poll files and MEDSL results (stable, but quick).


## Election week

**Morning of Nov 3 (before 6 pm ET): final forecast.** Run `python src/run_all.py --final`. It refreshes all data,
re-estimates everything, builds the site with a "Final pre-election forecast" banner, copies every model output to
`data/final/` (frozen for scoring), commits, tags `final-forecast-2026`, and pushes. Then confirm the Cloudflare build
started. `run_all.py` refuses to run after 23:00 UTC Nov 3 (polls closing; Wikipedia fills with partial results).

**After results settle: scorecard (not built yet).** Score the frozen `data/final/` forecasts against results:
- Senate: Brier score and log loss per race, face value vs. adjusted; which races each version got wrong.
- House: seat-total error vs. the 95% range; district-level Brier for the competitive seats.
- National: actual House popular vote vs. the generic-ballot average, i.e. this year's polling miss vs. the -2.55 /
  -1.56 shifts the adjusted model assumed. Did the adjustment pay off?
- Results source: Wikipedia race tables once settled (vandalism guard on), cross-checked against state certifications
  for close races; MEDSL later.
- Publish as a "Scorecard" tab on the site.
- Also score the off-site pocket scenarios in `data/final/pocket/` (not published): `pocket_senate_wide_shift` (the dropped -1.56 Senate-wide shift on top of Bias-adjusted) and `pocket_full_historical_bias` (full -2.93 on all polls). Did dropping the Senate-wide shift help or hurt?

## After the scorecard: post-mortem, model rework, governors, special elections (added Nov 8, 2026)

Target: the reworked model ready before Christmas 2026, so a special election can be forecast whenever one is called.

**1. Finish the scorecard.** Counting and certification run into December (California certifies last). The
post-mortem's 2026 numbers are provisional until then.

**2. Post-mortem analyses** (`src/postmortem/`, outputs in `data/postmortem/`; questions, methods and findings so far
in `src/postmortem/README.md`). Two planned site pages once the scorecard is final: a 2026 post-mortem and a
historical data exploration. Deferred until counting ends, so 2026 is included: extend the House history to
1998/2002 (popular-president midterms) and 2026; code each state's map type by cycle.

**3. Model rework** (candidate changes in `src/postmortem/README.md`): a state-level shared House error plus a
carried-forward state intercept; Senate and House national errors correlated well below 1 (better framed as
national errors grouped by measurement: statewide polls for Senate and governors, generic ballot and district
structure for the House; see item 4); a wave nonlinearity
(competitive and modestly-opposed districts swing more; incumbents of the party the wave runs against are protected
less); a wider national SD when fundamentals inputs leave their training range. Each is estimated and backtested on
2006-2024 first, with 2026 added as a held-out check once final, so the work doesn't wait for certification.
Upgrades follow README "Upgrading packages or Python" (branch, `check_frozen.py` against the frozen forecast).

**4. Governors (next cycle).** Plan below. Design on history now; run the model on the pre-election Nov 3
snapshot; score it against 2026 once certified.

*What the data already says* (computed Nov 8, 2026 from `data/final/bias_race_level.csv`, 256 governor and 328
Senate races with final-three-week polls, 2002-2022, and `data/final/calibration.json`):

| | Governor | Senate |
|---|---|---|
| Weight on polls vs a lean + environment prior (within cycle) | 0.95 (SE 0.02) | 0.87 (SE 0.05; matches `prior_weight.py`) |
| Result on state lean (within cycle): slope, R² | 0.50, 0.27 | 0.96, 0.57 |
| Residual SD, lean only / polls only | 18.6 / 6.9 | 16.4 / 6.8 |
| National polling miss SD by cycle (all / midterms) | 3.3 / 3.1 | 3.4 / 2.8 |

- Polls carry almost everything in polled races; partisanship is a weak guide, so unpolled races need a wide prior.
- The cycle-level governor polling miss correlates 0.89 with the Senate miss and 0.57 with the generic-ballot miss
  (13 cycles). Within a state and cycle, after national misses, governor and Senate misses correlate 0.34 (159 pairs).
  Errors group by what was measured (statewide polls vs the generic ballot and district structure), not by office.
- 2026 coverage (VoteHub, Nov 3): 31 of 36 races polled, 25 with 3+ polls since Sep 1. Unpolled: AR, HI, ID, OK,
  WY. The snapshot also has 2025 Virginia (53) and New Jersey (39) governor polls: off-cycle races with known results.

*Model*
1. **Races and candidates:** a collector for Wikipedia's 2026 gubernatorial overview (nominees, incumbents, term
   limits, status), on the Senate collector's pattern. Alaska (top-four, ranked choice) and serious independents are
   handled like Montana's Senate race: best non-Republican minus Republican.
2. **Poll average:** generalize `pollavg.senate()` by poll type (VoteHub `poll_type` "governor", state in `subject`).
   Same sponsor shifts, population weights and decay, after checking whether the pollster effects, estimated mostly on
   Senate and generic polls, hold for governor polls.
3. **Prior:** estimated on governor results history: lean (expect a slope near 0.5, not 1), environment,
   incumbency, and possibly the previous governor margin (candidate and brand persistence), tested against
   lean-only. It matters mainly for the five unpolled races and the thinly polled ones; the poll weight is
   re-estimated for governors (expect about 0.95).
4. **Errors:** two national factors, correlated about 0.5: a statewide-poll factor shared by Senate and governor
   races (correlation about 0.9) and the generic-ballot/House factor. This is the same change as the chamber-coupling
   fix in item 3 (group national errors by measurement, not by chamber). Plus a state-level component shared by a
   state's governor and Senate races (about 0.34), the House state shock, and fat tails as now.
5. **Outputs:** P(win) per race, Democratic governorships (mean, range), a Governors tab on the site.

*Backtest*
- 2018 and 2022, pseudo-prospective on `backtest.py`'s pattern (538 raw polls include governor races through 2022).
- 2025 Virginia and New Jersey: off-cycle, so it also tests the environment estimate special elections will need.
- 2026: hold it out. Freeze the governor design on history first, run it on the Nov 3 snapshot, and score once
  after certification. Nobody has looked at 2026 governor results with this model in mind, so this can be a genuine
  out-of-sample test, but only if the design is fixed before the results are scored.

*Data* (`src/collect/governors.py`, Nov 8, 2026; run `python src/collect/governors.py all`, then `check`)

Collected:
- `data/interim/governor_history.csv`: all 370 governor races 1998-2025 (odd years, specials and recalls included)
  from Wikipedia's yearly overview pages: incumbent, party, whether they ran, every candidate's share. Two-party
  margins match 538's actuals on 255 polled races (median difference 0.04; the 7 over 1 point are New York and
  Connecticut fusion tickets, where Wikipedia's totals are the right ones). D-side overrides for AK 2014 (Walker) and
  VT 2020 (Zuckerman); 14 races flagged multi-candidate (a third candidate at 15%+); 3 recalls flagged.
- `data/interim/state_presidential.csv`: state presidential results 1992-2024, all 50 states and DC, with two-party
  lean against the nation (national margins check against the known results).
- `data/interim/governor_2026_races.csv`: the 36 races as Wikipedia stood at the final VoteHub snapshot (revision of
  Nov 3, 19:59 UTC): nominees, incumbents (17 running), status, PVI. The collector stops if that revision shows
  vote shares, so 2026 stays held out.
- `data/interim/governor_dataset.csv`: the estimation table. Each race joined to lean from the last presidential
  election before it (and the one before), the national House vote, president's party and approval, the state's
  previous governor margin, and the final-three-week poll average (538 raw polls, identical to
  `bias_race_level.csv` where they overlap, plus 1998, 2000 and odd years; VoteHub for 2025 VA and NJ). 335 of 370
  races polled.

First look (smoke test, 318 two-way even-year races): margin = -1.6 + 0.34 x lean + 0.66 x national + 15.5 x
incumbent (R² 0.53, residual SD 14.6). Governor incumbency is worth far more than the House's 4.5.
2025: polls understated the Democrat by about 6 points in both races (NJ D+5.9 polled, D+14.5 result; VA D+9.5,
D+15.4).

Still open:
- **2024 governor polls** (11 races): 538's raw polls end in 2022. Optional; Wikipedia race pages as in the poll audit.
- **Lean measure:** presidential lean explains little. Test a statewide-composite lean (recent Senate and governor
  results, or the previous governor margin, now in the dataset) against it.
- **2026 poll averages:** generalize `pollavg.senate()` to governors (558 VoteHub polls; part of the model work).
- **Scorecard:** collect 2026 governor results only after the governor design is frozen.
- **Off-cycle environment for 2025:** generic-ballot and approval figures as of each date (VoteHub has both).

**5. Special elections.** Infrastructure to forecast one House, Senate or governor race on its own schedule. Needs:
the single-race path through the reworked model (environment, lean, incumbency, polls, error layers) without a
national seat simulation; a history of special-election results against lean, since specials have run well ahead of
the national environment for the out-party; and an environment estimate for an off-cycle date (generic ballot,
approval, recent specials).
