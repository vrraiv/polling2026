# Post-mortem analyses

Analyses of the frozen 2026 forecast against the results, and of the historical data behind it, for two planned
pages: a **2026 post-mortem** and a **historical data exploration**. Each script answers one question, reads only
frozen or committed data (`data/final/`, `data/interim/`, `data/scorecard/`), and writes one JSON (some also a CSV)
to `data/postmortem/`. Nothing here changes the forecast or the scorecard.

Run from the repo root with the project environment (README "Environment"):

```powershell
python src/postmortem/whatif_environment.py      # ~1 min
python src/postmortem/house_2026_breakdown.py    # seconds
python src/postmortem/history_context.py         # seconds
python src/postmortem/state_error.py             # ~5 min; --no-sim skips the 2026 simulations
```

Everything that uses 2026 results is **provisional until the scorecard is final**: Brier uses called contested races,
margins use settled counts only. Rerun all four once counting ends; the findings below are as of Nov 8, 2026.

`frozen.py` holds the shared loaders: the frozen error structure (t degrees of freedom, region SD, lean-slope SD,
House national loading), each version's national inputs and race files, the scorecard, and `draw_wins()`, which
re-simulates races exactly as `forecast.simulate()` does, optionally with a state shock.

## Scripts

| Script | Page | Question | Output |
|---|---|---|---|
| `whatif_environment.py` | 2026 | How would the forecast have scored had the national environment been known? | `whatif_environment.json`, `.csv` |
| `house_2026_breakdown.py` | 2026 | Where did the House upsets fall: lean, state, seat type? | `house_2026_breakdown.json` |
| `history_context.py` | history | How unusual was 2026? How are Senate and House errors linked? Does approval change incumbents' protection? | `history_context.json` |
| `state_error.py` | both | Do districts in the same state share an error the model left out? What drives it? | `state_error.json` |

### `whatif_environment.py`

Holds the shared national draw at `E - G` for each target environment `E` (explorer scale: national House margin),
re-draws region, slope and race errors, and rescores. The `forecast` rows reproduce the scorecard's Brier, which
checks the rescoring against the scorer. Also: the chance each version gave to environments at least that
Democratic, and the coupling each version assumed (Senate points per point of House environment).

### `house_2026_breakdown.py`

Expected (sum of probabilities) against actual Democratic wins and upsets, by PVI band, state and seat type, plus
the R+2 to R+12 band by seat type and the Senate by seat type. Version: polls + fundamentals.

### `history_context.py`

1. Midterms 1946-2022 ranked by the president's party's House margin, with approval and the change from the previous
   election; 2026's fundamentals inputs against the training range.
2. Cycle-level Senate polling miss against the generic-ballot miss (1998-2022), with Fisher-z intervals.
3. Senate polling miss toward the president's party against approval (2002-2022); House incumbency premiums for
   president's-party and out-party incumbents by cycle (2006-2024).

### `state_error.py`

Residuals of House results (2006-2024) after region x cycle effects (the national environment and the model's region
layer), lean x cycle (the slope layer) and incumbency x cycle; the state-cycle shared component by REML and method of
moments, with a placebo. Then four tests and a 2026 simulation (see the docstring). Mid-decade redraws are detected
from breaks in district PVIs and checked by hand (`MID_DECADE`, with the dropped artifacts listed).

## Findings so far (provisional)

**National environment.** Every version scores best in the House at about D+15 and in the Senate at D+10 to D+13.
One national draw can't fit both: the model moved Senate races 0.83-1.45 points per point of House environment, but
in 2026 House districts moved more than Senate races.

**Chamber coupling.** The model treated the Senate and House national errors as perfectly correlated. Historically
the cycle-level correlation is 0.48 (13 cycles; 95% interval -0.10 to 0.81) and 0.13 in midterms (7 cycles). A lower
correlation changes the joint distribution (explorer, House-and-Senate outcomes), not single-race probabilities.

**Extreme environment.** About D+13 puts 2026 with 1958, 1974 and 1982, not 1994 or 2010 (both about R+7, though 2010
had the biggest swing from the previous election). 2026 approval (35.6) and gas prices (+29%) were outside the
fundamentals training range. The polling calibration starts in 1998, so no comparable polled midterm exists.

**Where the House missed.** 25 upsets against 20.4 expected, all to Democrats. The excess is in R+2 to R+12 seats and
mostly Republican incumbents: in that band they lost 22 of 74 against 10.1 expected (open seats 10 of 31 against 6.8).
NC: 6 of 7 contested seats to Democrats against 1.8 expected.

**State-level shared error** (history 2006-2024):
- A state-cycle shock of about 3.3 points (3.0-3.6 by subset), 11-17% of district residual variance, 21-36% since
  2016. Placebo 0.7. The model's region shock was 0.48.
- **The rising share is the district error shrinking, not the state shock growing.** The state SD has no upward
  trend (2006-2014: 1.6-4.9; 2016-2024: 2.1-3.8), while the district-specific SD fell from 11.0 (2006) to 4.5-4.7
  (2022-2024), alongside the incumbency premium (about 20 points in 2006, about 4 in 2022). These SDs come from a
  richer fit over all contested districts, so they are not comparable with the model's district SD of 7.4
  (competitive districts only, 2016-2024, simpler fit). Whether that 7.4 is too wide is a separate question; the 2026
  coverage check (91% of House races inside their 80% intervals) suggests it may be.
- **Not a new-map effect:** smaller in the first cycle under a new map (2.6) than later (4.2); mid-decade redraws
  1.4 against 2.4 for other states in the same years (8 cases).
- **Not a band effect:** no larger in states with many lean-but-not-safe districts (3.7 against 3.7); district residual
  SD doesn't rise in that band.
- **A wave nonlinearity instead:** in wave years (|national| >= 5: 2006, 2008, 2010, 2014, 2018), near-even districts
  and those leaning modestly against the wave move 1-2 points further toward it than a linear swing; districts deep on
  either side move less. Strongest for incumbents of the party the wave runs against (+1.3 to +1.7, about 1 SE each).
- **Weakly shared across offices:** House shock against the same state's Senate result residual, r = 0.22; governor
  0.09. The Senate polls' own miss correlates about as weakly (0.17), so statewide polls carry little signal for the
  state's House districts.
- **Persistent:** a state's shock correlates 0.37 with its next cycle's (0.39 on the same map, 0.28 across a redraw).
  Carrying 0.4 x last cycle's shock forward cuts the state-shock error by 18% out of sample.
- **2026:** adding a 3.3 state shock leaves Brier unchanged and the seat range 2 seats wider; NC's result goes from
  1-in-700 to 1-in-60 with the environment fixed at D+15 (1-in-20 with a 5-point shock). NC stays a tail event.

## Deferred until counting ends

Both extend the history, and 2026 should be in it, so they wait for the final scorecard. Then rerun all four scripts.

1. **Popular-president midterms and 2026 in the House history.** `data/interim/house_history.csv` covers 2006-2024,
   and every midterm in it had approval 38.9-44.9. Extend it back to 1998 (Clinton, 64) and 2002 (Bush, 67) with the
   collector in `src/model/house_structure.py` (Wikipedia House pages by year), and forward to 2026. That is the only
   way to test whether approval changes how incumbents and chambers respond to the environment.
2. **Map-type coding.** Code who drew each state's congressional map in each cycle (partisan legislature, commission,
   court), and add `map_type` to `state_error.py`. Manual and needs checking by hand. Tests whether the state shock
   or the wave nonlinearity is larger under partisan maps, which the redraw and lean-band proxies could not show.

## Candidate model changes these point to

1. A state-level shared House error (SD about 3.3), plus a state intercept carried from the previous cycle.
2. Separate Senate and House national errors with a correlation well below 1.
3. A nonlinear response to the environment: competitive and modestly-opposed districts move more in waves, and
   incumbents of the party the wave runs against are protected less.
4. A wider national SD when fundamentals inputs fall outside their training range.
