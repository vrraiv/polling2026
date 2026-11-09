# Data catalogue and Data pages plan

Every source this project collects, what it's used for, the terms it comes under, and a plan for presenting the
historical data on the site. Compiled Nov 9, 2026. Licences marked "to confirm" couldn't be read directly (the page
refuses automated requests); check them by hand before launch.

## 1. Sources

Raw copies live in `data/raw/<source>/<date>/` with a `manifest.json` of URLs and retrieval times.

| Source | What we take | Coverage | Raw copy (in git?) | Terms | How to credit on the site |
|---|---|---|---|---|---|
| **Wikipedia** (REST and action APIs) | Election overview pages (House 1946-2026, governors 1998-2026, presidential 1992-2024, House specials 2007-2026), 2026 race pages, per-race poll tables, aggregator tables | 1946-2026 | `wikipedia/`, `wikipedia_hist/`, `wikipedia_results/` (yes, 153 MB); `wikipedia_results_pages/`, `wikipedia_polls_asof/` (no, 442 MB; revision ids kept) | CC BY-SA 4.0. Election results are facts, but tables built from Wikipedia are adaptations: release them under CC BY-SA too | "Wikipedia contributors, CC BY-SA 4.0" with links to the pages; outputs carry revision ids |
| ... Cook PVI and expert ratings, via Wikipedia | District and state lean (PVI); Cook, Sabato, Inside Elections and other ratings | 2006-2026 | within the Wikipedia pages | The numbers are the Cook Political Report's and each rater's | "Cook PVI (Cook Political Report), via Wikipedia"; name each rater |
| ... Aggregator averages, via Wikipedia | 2026 generic-ballot and approval averages (DDHQ, RealClearPolitics, Silver Bulletin, NBC, FiftyPlusOne...) | 2026 | within the Wikipedia pages | Each aggregator's figures | Name each aggregator |
| **FiveThirtyEight data repository** (GitHub) | `raw_polls.csv` (20,466 final-three-week polls with results, 1998-2023: presidential, Senate, governor, House, generic; includes 485 polls for House specials), pollster ratings, generic-ballot topline history | 1998-2023 | `538_github/` (yes) | CC BY 4.0 (repository README: "Unless otherwise noted, our data sets are available under the Creative Commons Attribution 4.0 International License") | "FiveThirtyEight (ABC News), CC BY 4.0" |
| **FiveThirtyEight polls archive**, via the Internet Archive | Historical poll files: presidential approval (15,181 polls, 2017-2025); generic ballot, Senate, House, governor (2016-2024, including the 2023-24 governor races and some 2023-24 House specials) | 2016-2025 | `538_wayback/` (yes) | CC BY 4.0, as 538's polls data was published (to confirm: the archived page couldn't be fetched; mirrors of 538's data agree) | "FiveThirtyEight (ABC News), CC BY 4.0, via the Internet Archive" |
| **VoteHub** API | 2025-26 polls: Senate, House, governor, generic ballot, approval (6,108 records in the final snapshot) | 2025-2026 | `votehub/`, `votehub_audit/` (yes) | CC BY 4.0 per VoteHub's API page (to confirm the exact attribution wording) | "VoteHub, CC BY 4.0" |
| **American Presidency Project** (UC Santa Barbara) | Gallup presidential approval, poll by poll, Roosevelt-Trump | 1941-2021 | `ucsb/`, `data/interim/gallup_approval.csv` (yes) | Not openly licensed: "Data adapted from the Gallup Poll and compiled by Gerhard Peters", © The American Presidency Project, UCSB terms of service | "Gallup, via the American Presidency Project (Peters and Woolley)". Show derived figures (window averages, charts); don't offer the poll-level file for download |
| **FRED / ALFRED** (St. Louis Fed) | CPI, gasoline CPI and price, real disposable income, unemployment, payrolls, GDP growth, consumer sentiment; vintage series | 1946-2026 | `fred/`, `alfred/` (yes) | FRED terms of use. The BLS, BEA and EIA series are U.S. government works (public domain); consumer sentiment (UMCSENT) is the University of Michigan's (copyrighted) | "BLS, BEA, EIA via FRED"; credit the University of Michigan if sentiment is shown |
| **FRED state series** (BLS LAUS and others) | State unemployment rates and other state series | 1950-2026 | `fred_state/` (yes) | Public domain (BLS) | "BLS, via FRED" |
| **FEC** API | Candidate fundraising totals | 2002-2026 | `fec/` (yes, 88 MB) | Public domain (U.S. government). FEC rules bar using individual contributors' details for solicitation or commercial purposes; we use candidate totals only | "Federal Election Commission" |
| **California Secretary of State** API | 2026 House results by district | 2026 | `ca_sos/` (yes) | Public election records | "California Secretary of State" |
| **State election offices** (GA, IA, LA, MN, MT, NE, SC, TX) | 2026 official Senate results | 2026 | `official/`, `official_manual/` (yes) | Public election records | Name each state's office |
| **AtlasIntel** poll reports | Toplines of 8 battleground Senate polls missing from VoteHub (`data/supplement/polls_supplement.json`) | 2026 | PDFs not in git (checksums kept) | Proprietary reports; toplines are facts | "AtlasIntel" per poll |
| MEDSL, BLS (direct) | Nothing (folders empty) | | | | |

### Licensing decisions before launch

1. **The repository has no licence file.** Without one, the code and derived data default to all rights reserved.
   A conventional choice: code under MIT; derived data under CC BY-SA 4.0. Share-alike is required for tables
   adapted from Wikipedia, and compatible with the CC BY sources (538, VoteHub). Each download should say which
   sources it draws on.
2. **Gallup approval in a public repository.** `data/raw/ucsb/` and `data/interim/gallup_approval.csv` republish
   the American Presidency Project's poll-level Gallup file. Charts and averages with attribution are ordinary use.
   Redistributing the file itself is less clear. Options: keep it (it's small and attributed), or gitignore it and
   keep the derived yearly approval in `fundamentals_dataset.csv`.
3. **Consumer sentiment** (`UMCSENT`) is copyrighted by the University of Michigan. It's in the raw folder, not
   used in any published output; keep it off the site and the downloads.
4. **Confirm by hand:** VoteHub's attribution wording (api.votehub.com) and the 538 polls archive's licence line.

## 2. Derived datasets

Built from the sources above; all in git.

| File | Built by | Coverage | What it holds |
|---|---|---|---|
| `data/interim/house_national_vote.csv` | `src/collect/history.py` | 1946-2024 | National House vote, two-party margin |
| `data/interim/gallup_approval.csv` | `history.py` | 1941-2021 | Gallup approval, poll by poll |
| `data/interim/fundamentals_dataset.csv` | `src/model/fundamentals.py` | 1946-2026 | Per election: president's party, House margin, previous margin, approval, inflation, gas, income, unemployment |
| `data/interim/house_history.csv` | `src/model/house_structure.py` | 2006-2024 | Every House district: Cook PVI, incumbent, status, vote shares, national vote (4,344 rows) |
| `data/interim/state_presidential.csv` | `src/collect/governors.py` | 1992-2024 | State presidential results and two-party lean vs the nation (459 rows) |
| `data/interim/governor_history.csv` | `governors.py` | 1998-2025 | Every governor race: incumbent, status, candidates and shares (370) |
| `data/interim/governor_dataset.csv` | `governors.py` | 1998-2025 | Governor races joined to lean, environment, approval, previous margin, poll averages |
| `data/interim/governor_polls_wiki.csv` | `governors.py` | 2022-2024 | Governor polls from Wikipedia race pages (236) |
| `data/interim/house_specials.csv` | `src/collect/specials.py` | 2007-2026 | House specials with lean on the lines in force (78) |
| `data/final/bias_race_level.csv` | `src/model/bias_analysis.py` | 2002-2022 | Senate and governor races: final-three-week poll average vs result (584) |
| `data/final/calibration.json` | `src/model/calibrate.py` | 1998-2022 | Polling misses by cycle (Senate, governor, House, generic); poll-average error by number of polls |
| `data/final/pollster_effects.json` | `src/model/pollster_effects.py` | 1998-2022 | Pollster house effects and the sponsored-poll shift |
| `data/final/error_structure.json` | `src/model/error_structure.py` | 1998-2022 | Census-region shocks, slope on lean |
| `data/final/state_econ.json`, `money_test.json` | `state_econ.py`, `money_test.py` | 1998-2022 | Tests of local unemployment and fundraising (both null) |
| `data/final/*` (rest) | the frozen forecast | 2026 | Forecast inputs and outputs; never rewritten |
| `data/scorecard/*` | `src/run_scorecard.py` | 2026 | Results, margins, poll audit (VoteHub vs Wikipedia coverage) |
| `data/postmortem/*` | `src/postmortem/*.py` | 1946-2026 | What-if environment, House upsets, history context, state-level error |
| `data/processed/governor_*`, `environment_offcycle.json`, `specials_environment.json`, `single_race_backtest.json` | `governor_model.py`, `environment.py`, `special_model.py`, `single_race.py` | 1946-2026 | Governor model and backtest, off-cycle environment, special elections |

## 3. Data pages plan

**Status (Nov 9, 2026): built.** `src/site/history.py` writes six pages to `site/history/` (overview with sources and
downloads; vote shares; approval and incumbency; states and regions; polling accuracy; off-cycle elections), 22
charts and 23 CSV downloads, linked from the forecast page's nav. Charts: `site/assets/charts.js`, styles:
`site/assets/history.css`. Two departures from the plan below: the forecast page keeps its own chart code (it's the
frozen page; only its nav changed), and each download's sources and licence are shown beside its link rather than
inside the CSV, so the files stay plain. Licences: `LICENSE` (MIT, code) and `LICENSE-DATA.md` (CC BY-SA 4.0,
derived data). Still to do: the gaps listed below, and refreshing the provisional 2026 points once certified (rerun
the script).

### Where they live

The forecast is one page (`site/index.html`, about 1 MB, tabs, hand-drawn SVG charts, data embedded). Its "Data"
tab lists sources and downloads for the forecast. The historical material is larger and doesn't depend on 2026, so
it should be **separate pages**: smaller files, linkable sections, and no changes to the frozen forecast page beyond
a nav link.

- Proposed path: `site/history/` (one page per section), built by a new `src/site/history.py` from the files in
  section 2. `site/data/` stays the downloads folder.
- Charts: the same hand-drawn SVG approach and styles as the forecast page, with the chart helpers moved into a
  shared script (`site/assets/charts.js`), so both look alike and there's no library to load.
- Each chart gets a download of exactly the numbers it shows (CSV), with its sources and licence in a header line.
- Provisional 2026 points (counting still finishing) are marked as such and refreshed when the scorecard is final.
  The rest can launch before then.

### Sections

Each lists its charts, the data behind them, and whether the numbers already exist (from analyses in this project)
or need new work.

**A. Vote shares over time** (the national picture)
- National House vote 1946-2026: two-party margin, president's party marked, midterms highlighted. *Exists*
  (`house_national_vote.csv`).
- Midterm penalty: the president's party's House margin in every midterm vs the previous election, 1946-2026; 2026
  alongside 1958, 1974 and 1982 (only 1974 was larger). *Exists* (`history_context.json`).
- Presidential vote 1992-2024: national two-party margin and every state's lean. *Exists*; **new:** extend to
  1948-1988 with the same collector (about 10 more pages).
- Polarization: spread of state leans by election, number of states within 5 points. **New** (from
  `state_presidential.csv`).

**B. Approval and incumbency**
- Approval vs the president's party's midterm result, 1946-2026, with the fundamentals fit (0.19 to 0.36 points of
  margin per point of approval, depending on the specification). *Exists* (`fundamentals.json`,
  `environment_offcycle.json`).
- Approval in the year of each off-cycle election and how much those electorates swung against the president: the
  term-year effect (year after a presidential election swings about twice a midterm; year before, barely).
  *Exists* (`environment_offcycle.json`, `governor_model.json`, `specials_environment.json`).
- House incumbency premium by cycle, 2006-2024: from about 20 points to about 4. *Exists* (`house_structure.json`).
  Split by president's party vs out-party. *Exists* (`history_context.json`).
- Governor incumbency (about 15 points) against House (4.5); Senate (needs data, see gaps).
- 2026: Republican House incumbents in R+2 to R+12 seats won 52 of 74 against about 64 expected. *Exists*
  (`house_2026_breakdown.json`).

**C. States and regions** (how places move together)
- State swing correlations: each state's change in presidential lean between elections, correlated across states
  and grouped by Census region. **New** (`state_presidential.csv`).
- The state-level shared House error: about 3.3 points, a rising share of district error as district-specific
  error collapsed (11 to 4.5), persistence 0.37 from one cycle to the next; not tied to new maps. *Exists*
  (`state_error.json`).
- Regional misses in 2026 (Midwest -2.2, South +3.2 vs the national miss) against the 0.48 the model assumed.
  *Exists* (`scorecard.json` layers).
- Same-state Senate and governor polling misses (correlation 0.34 after national misses); House shock vs the
  Senate result (0.22). *Exists* (`state_error.json`; governor plan figures).
- Governor results vs presidential lean (slope 0.37, against 0.96 for the Senate): how much governors run apart
  from their states' partisanship, by year. **New** chart from `governor_dataset.csv`.

**D. Polling accuracy**
- Final-poll misses by cycle, 1998-2022: generic ballot, Senate, governor. Polls overstated Democrats in 11 of 14
  elections 1998-2024. *Exists* (`calibration.json`, `bias_analysis.json`).
- How misses travel together: governor and Senate polling misses correlate 0.89 by cycle; Senate and generic 0.48
  (0.13 in midterms). *Exists* (`history_context.json`; governor plan figures).
- Error of a poll average by number of polls (10.5 points with 1-2 polls, 5 with 10+). *Exists*
  (`calibration.json`).
- Results land further toward a state's lean than its polls (about 0.08 points per point of lean). *Exists*
  (`bias_analysis.json`).
- Pollster house effects and the sponsored-poll shift. *Exists* (`pollster_effects.json`).
- 2026: VoteHub's coverage against Wikipedia's poll tables. *Exists* (`scorecard.json` poll audit).

**E. Off-cycle elections**
- Off-year governor races 1999-2025 against the environment: NJ and VA swung against the president in all 7
  years after a presidential election. *Exists* (`environment_offcycle.json`).
- House special elections 2007-2026 against lean and environment; the special electorate's shift toward Democrats
  since 2017. *Exists* (`specials_environment.json`, `single_race_backtest.json`).

**F. Sources and downloads**: section 1 of this file as a page, plus every chart's CSV.

### Gaps worth filling

- **Senate results history** (every race with incumbency, as for governors): needed for Senate incumbency,
  Senate-vs-presidential lean, and Senate/House split tickets. The yearly Senate overview pages have the same table
  format as the governor ones, so `governors.py` can be adapted.
- **Presidential state results 1948-1988**: extends section A's lean and polarization charts.
- **House district history before 2006**: pages are cached back to 1946, but district PVI isn't on the older pages;
  district results against presidential results by district would need another source.
- **Special-election polls**: 538's `raw_polls.csv` holds 485 polls for House specials (2012-2022, e.g. 14 for
  GA-6 2017), and its polls archive adds some for 2023-24 (RI-1, UT-2, NY-3). The search by hand is mainly
  2025-26.

### Order of work

1. Licensing decisions (section 1) and the shared chart script.
2. Sections A, B and C (the starting points): mostly existing numbers; new state swing correlations and
   polarization.
3. Sections D and E; F alongside.
4. Gaps, in the order above, as each section needs them; 2026 points finalized with the scorecard.
