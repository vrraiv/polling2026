# polling2026

2026 midterm Senate and House forecast and its post-election scorecard, live at https://polling2026.vikramrai.com.
The final forecast was frozen on Nov 3, 2026 (tag `final-forecast-2026`, outputs in `data/final/`) and is never
rewritten. The method is in `FORECAST.md`; the plan and its history are in `PLAN.md`; the data sources and derived
datasets are catalogued in `DATA.md`.

## Environment

Python 3.14.3 (uv-managed) with the exact package versions in `uv.lock`, in a virtual environment kept outside
OneDrive at `$HOME\.venvs\polling2026` (e.g. `C:\Users\<you>\.venvs\polling2026`). OneDrive would otherwise sync
its thousands of files. The environment is per device: a fresh clone, or this folder synced to a new machine, has
none until you create it.

### First-time setup on a new device

In PowerShell:

1. Install uv (once per machine), then open a new terminal so it is on `PATH`, and check it:

   ```powershell
   winget install --id=astral-sh.uv -e
   # or: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   uv --version
   ```

   No system Python is needed: uv downloads and manages CPython 3.14.3 itself.

2. From the repo root, point uv at the out-of-OneDrive location and create the environment. uv creates the folder,
   downloads Python 3.14.3 if this machine doesn't have it, and installs exactly what `uv.lock` lists:

   ```powershell
   $env:UV_PROJECT_ENVIRONMENT = "$HOME\.venvs\polling2026"   # this session only
   uv sync --locked --managed-python --python 3.14.3
   ```

3. Check it:

   ```powershell
   & "$HOME\.venvs\polling2026\Scripts\python.exe" --version   # Python 3.14.3
   & "$HOME\.venvs\polling2026\Scripts\python.exe" -c "import numpy, pandas, scipy, statsmodels, lxml, PIL; print('ok')"
   ```

   `run_scorecard.py --parse` re-parses saved snapshots, some of which are gitignored (see `.gitignore`), so on a
   bare `git clone` run `python src/run_scorecard.py` (which fetches) before `--parse`.

4. Optional: an FEC API key in `.env` at the repo root (`fec_api_key=...`, gitignored). Without it the FEC
   collectors use `DEMO_KEY`, which is rate-limited. If the folder is synced by OneDrive, `.env` comes with it.

If PowerShell refuses `Activate.ps1` below because scripts are disabled, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or call `python.exe` by its full path instead.

### Updating the environment

The same command updates it after `uv.lock` changes (e.g. after pulling an upgrade). In each new PowerShell session:

```powershell
$env:UV_PROJECT_ENVIRONMENT = "$HOME\.venvs\polling2026"   # this session only
uv sync --locked --managed-python --python 3.14.3
```

Set `UV_PROJECT_ENVIRONMENT` per session, not as a permanent user variable: it would apply to every uv project on the
machine. Without it, `uv sync` and `uv run` create `.venv/` inside this folder, in OneDrive (gitignored, but slow).

Run scripts with the environment's interpreter, directly or after activating it:

```powershell
& "$HOME\.venvs\polling2026\Scripts\python.exe" src/run_scorecard.py --build
# or, once per session:
& "$HOME\.venvs\polling2026\Scripts\Activate.ps1"
python src/run_scorecard.py --build
```

Python is pinned by the environment, not by a `.python-version` file, because Cloudflare's build image reads that
file when it deploys `site/`. `pyproject.toml` only requires 3.14.3 or later within 3.14.

The environment that matches the frozen forecast is tagged `env-2026`. To rebuild it exactly:
`git checkout env-2026 -- pyproject.toml uv.lock`, then the `uv sync` command above.

## Commands

| Command | What it does |
|---|---|
| `python src/run_scorecard.py` | Daily during counting: fetch results, then score. `--build` previews the site locally. |
| `python src/run_scorecard.py --manual` | Also read official results downloaded by hand into `data/raw/official_manual/<ST>/<date>/`. |
| `python src/run_scorecard.py --parse` | Re-parse the saved snapshots without fetching. After an upgrade, `git diff data/scorecard` should be empty. |
| `python src/check_scorecard.py` | Check a scorecard refresh against the last commit before publishing: HOLD, REVIEW or CLEAN. |
| `python src/model/single_race.py house --state TN --district 7 --date 2025-12-02` | Forecast one House special (or `governor --state VA --date 2025-11-04 --votehub ...`) from data before its date; `--poll D,R` adds polls. `backtest` scores every House special since 2008. |
| `python src/site/history.py` | Rebuild the Election data pages (`site/history/`, linked from the forecast's nav) and their CSV downloads from the committed data. `python src/collect/generic_ballot.py` rebuilds the daily generic-ballot series they use. |
| `python src/postmortem/<script>.py` | Post-mortem and historical analyses (what-if environment, where the House missed, history, state-level error). Each writes to `data/postmortem/`; see `src/postmortem/README.md`. |
| `python src/check_frozen.py` | Rebuild the model from the frozen inputs and compare every file in `data/final/`. |
| `python src/run_all.py` | The pre-election refresh. It refuses to run after polls closed on Nov 3, 2026. |

## Upgrading packages or Python

Upgrades are deliberate. `uv sync` never moves a version; only `uv lock --upgrade` does.

1. On a branch: `git switch -c upgrade-YYYY-MM-DD`.
2. Update the lock: `uv lock --upgrade` for everything, or `uv lock --upgrade-package pandas` for one package. The
   ranges in `pyproject.toml` stop at the next major version; raising a ceiling is its own decision. For a new
   Python, change `requires-python` and the `--python` version.
3. Update the environment with the `uv sync` command above, and commit any code changes on the branch: the check
   rebuilds committed code, and refuses to run while model code or inputs have uncommitted changes.
4. Run `python src/check_frozen.py` (a few minutes; it works in a temporary git worktree, so the working copy is
   never touched). The result is one of:
   - **FAIL**: a deterministic output changed (poll averages, pollster effects, `mu`, `sd`, regressions: the model
     itself), a headline number (control probabilities, seat means) moved beyond its simulation noise, or a file
     wasn't rebuilt. Find the cause before merging.
   - **PASS WITH WARNINGS**: everything above held, but a few simulation outputs landed outside their usual noise.
     A near-50/50 race changing favourite reshuffles the most likely maps and flip lists, so an occasional warning
     is expected after a numpy upgrade; many, or large multiples, deserve a look.
   - **PASS**: simulation outputs within noise (5x their seed-to-seed movement across 20 seed shifts, in
     `data/checks/sim_noise.json`), everything else identical or equal to rounding.

   A numpy upgrade can change the random draws, and that shows up as "sim noise". The deprecation warnings it lists
   are the to-do list for the next major version.
   `--ref final-forecast-2026` runs the frozen code itself, to separate package effects from code changes.
   `--seed-shift 9` is a self-test of the tolerances: it changes the random draws as a numpy upgrade would, and
   should come out as "sim noise". Recalibrate with `--calibrate-noise` (five rebuilds in parallel) only if the
   simulation design changes.
5. Run `python src/run_scorecard.py --parse --build` and check that `git diff data/scorecard site` is empty: the
   scorecard re-parses the same snapshots to the same numbers, and the page (frozen forecast plus scorecard) is
   rebuilt byte for byte.
6. Merge.

## Deploying

Cloudflare redeploys `site/` on every push to `main`; no Python runs at deploy time. In the Worker's build settings,
set `SKIP_DEPENDENCY_INSTALL=1` so the build image doesn't try to install the Python packages from `uv.lock`. After
any push, check the live page updated.
