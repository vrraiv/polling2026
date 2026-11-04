"""Does the model still reproduce the frozen final forecast (data/final/) under this environment and this code?

    python src/check_frozen.py                            current code (HEAD) with this interpreter (a few minutes)
    python src/check_frozen.py --ref final-forecast-2026  the frozen code itself: isolates package/Python changes
    python src/check_frozen.py --seed-shift 41            self-test: change the random draws as a numpy upgrade would
                                                          (use a shift above 20); should PASS with "sim noise"
    python src/check_frozen.py --calibrate-noise          rebuild with the seed shifted by 1..20 (10 at a time) and record
                                                          how far each simulation output moves -> data/checks/sim_noise.json
    options: --python PATH (interpreter for the model; default this one), --keep (keep the temporary worktree)

Run it with the project environment (README "Environment"), before and after any package upgrade or model refactor.

How it works
  * A temporary git worktree of --ref, outside OneDrive, so the working copy is never touched.
  * Raw snapshots dated after the lock are deleted from the worktree: the model reads the newest snapshot of each
    source, so a later fetch (a special election, say) would otherwise change its inputs.
  * "Today" is the lock date: polls are aged as of it (pollavg.ASOF), and fetch() finds the lock-day file it found on
    Nov 3 (fundamentals.py fetches FRED series itself) instead of downloading. The network is switched off, so a
    step that needs a file the frozen inputs lack fails instead of quietly pulling new data.
  * The model steps of run_all.STEPS (src/model/*: no fetching, no site build) run in order.
  * Every file in data/final/ is compared with its rebuilt copy.

Verdicts
  identical    byte for byte
  rounding     numbers differ by less than 1e-9 (relative); text identical
  sim noise    only outputs that move with the random seed differ: each number by at most 5x its root-mean-square
               movement across 20 seed shifts, each set of labels by at most 2x the most that changed (sim_noise.json).
               Expected after a numpy upgrade: numpy keeps seeded draws stable only within a version. Fields that never
               moved with the seed must match to rounding.
  sim warning  a simulation output outside its usual noise (listed with the multiple). Rare jumps happen: a near-50/50
               race changing favourite reshuffles the most likely maps. The run still passes ("PASS WITH WARNINGS");
               many warnings, or large multiples, deserve a look. Headline numbers (control probabilities, seat means
               of the three published versions; HEADLINE) are smooth and fail instead. Outputs count as simulation
               outputs if they moved in calibration, sit in the sims files or a "reading" section, or share their name
               with a field in the same file that moved (a seat percentile in one scenario when it moved in another).
  by design    a file no run_all model step regenerates (BY_DESIGN: a one-off analysis and a cache)
  DIFFERS      anything else: find the cause before accepting the upgrade or refactor
  NOT REBUILT  the step that writes the file didn't rewrite it (a stale copy is never counted as a match)
Special cases
  * bias_confidence.json copies a table from senate_polls_fundamentals.csv as it stood before the run (LAGGED), so the
    frozen copy lags the final forecast by one run; the rebuilt table must equal the frozen forecast's values.
  * FORECAST.md renders the data files: its table rows are not compared (the CSVs and JSONs they restate are), and the
    rest must keep its wording and structure; numbers in it may move only as the data files do.
  * Lists in the simulations' "reading" sections (most likely maps, flip lists, seat ladders, tipping points,
    competitive races) rank near-tied items, so their order follows the draws: items are matched by identity (a map
    by its winners, a seat or race by its label), and the count in one file only plus the shared items' attributes are
    compared. Lists everywhere else are deterministic and compared position by position.
Deprecation and future warnings printed during the run are listed at the end: what the next major version will break.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "data" / "final"
NOISE = ROOT / "data" / "checks" / "sim_noise.json"
REL_TOL = 1e-9
K_SIGMA = 5.0          # numeric tolerance: 5x a field's root-mean-square seed-to-seed movement
LABEL_FACTOR = 2       # label tolerance: 2x the most labels a seed shift changed
CAL_SHIFTS = list(range(1, 21))
CAL_WORKERS = 10
# What the rebuild reads: uncommitted changes here would be missing from the worktree (data/raw snapshots after the lock
# are pruned anyway, and the scorecard's own raw folders aren't model inputs).
MODEL_PATHS = ["src/model", "src/collect", "src/run_all.py", "data/supplement", "data/interim", "data/raw/votehub",
               "data/raw/wikipedia", "data/raw/wikipedia_hist", "data/raw/fred", "data/raw/fred_state", "data/raw/alfred",
               "data/raw/538_github", "data/raw/538_wayback", "data/raw/ucsb", "data/raw/fec", "data/raw/medsl", "data/raw/bls"]
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WARN = re.compile(r"(DeprecationWarning|FutureWarning|PendingDeprecationWarning)")
NUMBER = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")

# Files in data/final/ that the run_all model steps don't regenerate (reported, never counted as failures).
BY_DESIGN = {
    "money_test.json": "one-off analysis (src/model/money_test.py, last run Nov 2), not a run_all step",
    "pollster_effects_bigloco.json": "cache: pollster_effects.py computes it only when the file is missing, then reads it",
}
# bias_confidence.py runs before forecast.py but copies this table from senate_polls_fundamentals.csv as it stands, so
# on Nov 3 it read the previous run's forecast: the frozen copy lags the final forecast by one run (mu by up to 0.02).
# A rebuild reads the frozen forecast, so its table must equal data/final's senate_polls_fundamentals.csv.
LAGGED = ("bias_confidence.json", "lean_based.races[*].", "senate_polls_fundamentals.csv",
          ["state", "pvi", "poll_avg", "mu", "p_dside"])
# Headline numbers of the three published versions: smooth averages over all simulations (no rare jumps), so moving
# beyond their noise is a failure, not a warning.
HEADLINE = {f"summary_{v}.json:{k}" for v in ("polls_only", "polls_fundamentals", "polls_fundamentals_biasadj")
            for k in ("senate.p_dem_control_without_osborn", "senate.p_dem_control_if_independents_caucus_D",
                      "senate.p_rep_control", "senate.dem_seats_mean", "house.p_dem_majority", "house.p_rep_majority",
                      "house.dem_seats_mean")}

# Runs one model step as __main__ with the lock date pinned and the network off (and, for noise runs, the seed shifted).
RUNNER = r"""
import os, runpy, sys
from pathlib import Path
script = Path(sys.argv[1]).resolve()
sys.argv = [str(script), *sys.argv[2:]]
sys.path.insert(0, str(script.parent))
sys.path.insert(1, str(script.parents[1] / "model"))
sys.path.insert(2, str(script.parents[1] / "collect"))
import pandas as pd
import common, pollavg
pollavg.ASOF = pd.Timestamp(os.environ["CHECK_ASOF"])
common.TODAY = os.environ["CHECK_ASOF"]      # fetch() then finds the lock-day file it found on Nov 3 and skips downloading
def _offline(*a, **k):
    raise RuntimeError("check_frozen: network is off; a model step tried to download a file missing from the frozen inputs")
common.SESSION.get = _offline
shift = int(os.environ.get("CHECK_SEED_SHIFT", "0"))
if shift:
    import numpy as np
    _rng = np.random.default_rng
    def _shifted(seed=None, *a, **k):       # integer seeds only: libraries also pass Generators and None through here
        if isinstance(seed, (int, np.integer)) and not isinstance(seed, bool):
            seed = int(seed) + shift
        return _rng(seed, *a, **k)
    np.random.default_rng = _shifted
runpy.run_path(str(script), run_name="__main__")
"""


# ---- worktree and model run ---------------------------------------------------------------------------------------
def git(*args, cwd=ROOT):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def lock_date():
    return (FINAL / "MADE_AT.txt").read_text().split()[0]          # "2026-11-03 16:08 EST" -> 2026-11-03


def final_files():
    return sorted(p.relative_to(FINAL).as_posix() for p in FINAL.rglob("*") if p.is_file() and p.name != "MADE_AT.txt")


def rebuilt_path(wt, rel):
    return wt / "FORECAST.md" if rel == "FORECAST.md" else wt / "data" / "processed" / rel


class Worktree:
    """A temporary checkout of ref outside OneDrive, with inputs dated after the lock removed."""

    def __init__(self, ref, day, keep=False):
        self.tmp = Path(tempfile.mkdtemp(prefix="polling2026-check-"))
        self.path, self.keep = self.tmp / "wt", keep
        git("worktree", "add", "--detach", str(self.path), ref)
        self.pruned = []
        for src in sorted((self.path / "data" / "raw").iterdir()):
            for d in sorted(p for p in src.iterdir() if p.is_dir() and DATED.match(p.name) and p.name > day):
                shutil.rmtree(d)
                self.pruned.append(f"{src.name}/{d.name}")
        self.before = {rel: self._mtime(rel) for rel in final_files()}

    def _mtime(self, rel):
        p = rebuilt_path(self.path, rel)
        return p.stat().st_mtime_ns if p.exists() else None

    def rewritten(self, rel):
        return self._mtime(rel) is not None and self._mtime(rel) != self.before[rel]

    def remove(self):
        if self.keep:
            print(f"   worktree kept: {self.path}")
            return
        subprocess.run(["git", "worktree", "remove", "--force", str(self.path)], cwd=ROOT, capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True)   # OneDrive can delay the delete


def model_steps(wt):
    spec = importlib.util.spec_from_file_location("run_all_wt", wt / "src" / "run_all.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return [s for s in mod.STEPS if s[0].startswith("src/model/")]


def run_model(wt, python, day, shift=0, quiet=False):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "CHECK_ASOF": day, "CHECK_SEED_SHIFT": str(shift),
           "PYTHONWARNINGS": "default::DeprecationWarning,default::FutureWarning,default::PendingDeprecationWarning"}
    env.pop("FORECAST_FINAL", None)
    log, warns = [], {}
    for step in model_steps(wt):
        if not quiet:
            print(f"   >> {' '.join(step)}", flush=True)
        r = subprocess.run([python, "-c", RUNNER, str(wt / step[0]), *step[1:]], cwd=wt, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        log.append(f"===== {' '.join(step)} (exit {r.returncode})\n{r.stdout}\n{r.stderr}")
        for line in r.stderr.splitlines():
            if WARN.search(line):
                warns.setdefault(re.sub(r"^.*?(\w*Warning)", r"\1", line.strip())[:220], step[0])
        if r.returncode:
            (wt / "check_log.txt").write_text("\n".join(log), encoding="utf-8")
            raise RuntimeError(f"step failed: {step} (shift {shift}; log: {wt / 'check_log.txt'})\n{r.stderr[-2000:]}")
    (wt / "check_log.txt").write_text("\n".join(log), encoding="utf-8")
    return warns


# ---- comparison: each file becomes {field: (kind, max abs diff, max rel diff, mismatches)} --------------------------
def num_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    both_nan = np.isnan(a) & np.isnan(b)
    d = np.where(both_nan, 0.0, np.abs(a - b))
    d = np.where(np.isnan(d), np.inf, d)                         # NaN on one side only
    scale = np.maximum(np.maximum(np.abs(a), np.abs(b)), 1e-12)
    return (float(d.max()) if d.size else 0.0), (float((d / scale).max()) if d.size else 0.0)


def flatten(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from flatten(v, f"{path}.{k}" if path else str(k))
    elif isinstance(x, list):
        for v in x:
            yield from flatten(v, f"{path}[*]")
    else:
        yield path, x


def compare_csv(fa, fb):
    a, b = pd.read_csv(fa, low_memory=False), pd.read_csv(fb, low_memory=False)
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return {"(structure)": ("text", 0, 0, 1)}
    out = {}
    for c in a.columns:
        x, y = a[c], b[c]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y) and not pd.api.types.is_bool_dtype(x):
            out[c] = ("num", *num_diff(x, y), 0)
        else:                                                    # missing on both sides is a match (NaN != NaN)
            same = (x.astype(object) == y.astype(object)) | (x.isna() & y.isna())
            out[c] = ("text", 0, 0, int((~same).sum()))
    return out


def ranked_id(e):
    """Identity of an item in a simulation-ranked list: a map by its winners, a seat or race by its label, a string as is."""
    if isinstance(e, str):
        return e
    if isinstance(e, dict) and isinstance(e.get("winners"), dict):
        return json.dumps(e["winners"], sort_keys=True)
    if isinstance(e, dict):
        return e.get("label", e.get("race"))
    return None


def pop_ranked(x, path="", in_reading=False):
    """Remove and return (by path) the lists inside the simulations' "reading" sections: most likely maps, flip lists,
    seat ladders, tipping points, competitive races. They rank near-tied items, so their order follows the draws."""
    found = {}
    if isinstance(x, dict):
        for k in list(x):
            p, v = (f"{path}.{k}" if path else k), x[k]
            if in_reading and isinstance(v, list) and v and all(ranked_id(e) is not None for e in v):
                found[p] = x.pop(k)
            else:
                found.update(pop_ranked(v, p, in_reading or k == "reading"))
    return found


def compare_ranked(ra, rb):
    """Ranked lists are matched by identity, not position: the number of items in one file only, and each scalar
    attribute of the shared items (nested lists, e.g. a map's upsets, follow from the identity and are skipped)."""
    isnum = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    out = {}
    for p in sorted(set(ra) | set(rb)):
        if p not in ra or p not in rb:
            out[p] = ("text", 0, 0, 1)
            continue
        A, B = {ranked_id(e): e for e in ra[p]}, {ranked_id(e): e for e in rb[p]}
        only = len(A.keys() ^ B.keys())
        out[f"{p} (items in one file only)"] = ("num", float(only), only / max(len(A) + len(B), 1), 0)
        shared = sorted(A.keys() & B.keys())
        attrs = sorted({k for s in shared if isinstance(A[s], dict) for k, v in A[s].items() if not isinstance(v, (list, dict))})
        for k in attrs:
            x, y = [A[s].get(k) for s in shared], [B[s].get(k) for s in shared]
            if all(isnum(v) for v in x + y):
                out[f"{p}[*].{k}"] = ("num", *num_diff(x, y), 0)
            else:
                out[f"{p}[*].{k}"] = ("text", 0, 0, sum(u != w for u, w in zip(x, y)))
    return out


def compare_json(fa, fb):
    """Values are grouped by path (list positions -> [*]). Lists may differ in length (a seat ladder's length follows
    the simulations): overlapping values are compared and the length difference is its own field. Lists in the
    simulations' "reading" sections are matched by identity instead (compare_ranked)."""
    ja, jb = (json.loads(Path(f).read_text(encoding="utf-8")) for f in (fa, fb))
    out = compare_ranked(pop_ranked(ja), pop_ranked(jb))

    def groups(j):
        g = {}
        for k, v in flatten(j):
            g.setdefault(k, []).append(v)
        return g
    isnum = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    a, b = groups(ja), groups(jb)
    for k in sorted(set(a) | set(b)):
        if k not in a or k not in b:
            out[k] = ("text", 0, 0, 1)                      # present on one side only
            continue
        x, y = a[k], b[k]
        n = min(len(x), len(y))
        if all(isnum(v) for v in x[:n] + y[:n]):
            out[k] = ("num", *(num_diff(x[:n], y[:n]) if n else (0.0, 0.0)), 0)
        else:
            out[k] = ("text", 0, 0, sum(p != q for p, q in zip(x, y)))
        if len(x) != len(y):
            d = abs(len(x) - len(y))
            out[f"{k} (count)"] = ("num", float(d), d / max(len(x), len(y)), 0)
    return out


def sims_stats(f):
    meta = json.loads(f.with_suffix(".json").read_text(encoding="utf-8"))
    raw, n = f.read_bytes(), meta["n"]
    bits = np.frombuffer(raw[:4 * n], "<u4")
    nat = np.frombuffer(raw[4 * n:6 * n], "<i2") * meta["nat_scale"]
    hs = np.frombuffer(raw[6 * n:8 * n], "<u2").astype(float)
    ss = np.frombuffer(raw[8 * n:9 * n], "u1").astype(float)
    win = {r: ((bits >> np.uint32(i)) & 1).mean() for i, r in enumerate(meta["races"])}
    return win, {"nat_mean": nat.mean(), "nat_sd": nat.std(), "house_mean": hs.mean(), "house_p10_p90": np.percentile(hs, [10, 90]),
                 "senate_mean": ss.mean(), "senate_p10_p90": np.percentile(ss, [10, 90])}


def compare_bin(fa, fb):
    """The file keeps the 32 races closest to 50-50, so which races (and in what order) follows the draws: win rates are
    compared by race name, and races in only one file are counted."""
    (wa, sa), (wb, sb) = sims_stats(Path(fa)), sims_stats(Path(fb))
    common = sorted(set(wa) & set(wb))
    out = {k: ("num", *num_diff(np.atleast_1d(sa[k]), np.atleast_1d(sb[k])), 0) for k in sa}
    out["race_win_rate"] = ("num", *num_diff([wa[r] for r in common], [wb[r] for r in common]), 0)
    d = len(set(wa) ^ set(wb))
    out["races_in_one_file_only"] = ("num", float(d), d / max(len(wa), 1), 0)
    return out


def compare_md(fa, fb):
    """Table rows restate the data files and aren't compared. Other lines that differ only in their numbers are keyed by
    their wording (numbers -> #); a change of wording, or in the number of lines, is a text difference."""
    keep = lambda f: [l for l in Path(f).read_text(encoding="utf-8").splitlines()
                      if not l.startswith("_Generated") and not l.lstrip().startswith("|")]
    a, b = keep(fa), keep(fb)
    if len(a) != len(b):
        return {"(line count outside tables)": ("text", 0, 0, 1)}
    out = {}
    for x, y in zip(a, b):
        if x != y:
            tx, ty = NUMBER.sub("#", x), NUMBER.sub("#", y)
            out[f"line '{tx[:90]}'"] = ("mdnum", 0, 0, 0) if tx == ty else ("text", 0, 0, 1)
    return out or None


def compare(fa, fb):
    if fa.read_bytes() == fb.read_bytes():
        return None
    return {".csv": compare_csv, ".json": compare_json, ".bin": compare_bin, ".md": compare_md}.get(
        fa.suffix, lambda x, y: {"(bytes)": ("text", 0, 0, 1)})(fa, fb)


def compare_all(w):
    return {rel: (compare(FINAL / rel, rebuilt_path(w.path, rel)) if w.rewritten(rel) else "stale") for rel in final_files()}


def lagged_check(wt):
    """The rebuilt lean_based table must equal the frozen forecast it read (to the 2 decimals the table keeps)."""
    rel, prefix, src, cols = LAGGED
    got = pd.DataFrame(json.loads((wt / "data/processed" / rel).read_text(encoding="utf-8"))["lean_based"]["races"])
    want = pd.read_csv(FINAL / src)[cols].round(2).set_index("state")
    got = got.set_index("state")[cols[1:]]
    d = (got - want.loc[got.index]).abs().max().max()
    return [] if d < 0.0051 else [f"{prefix}* doesn't match the frozen {src} it was copied from (max diff {d:.3g})"]


def leaf(field):
    """A field's own name: 'strong_region_2pt.house_p10' -> 'house_p10', 'senate.hist[*] (count)' -> 'hist'."""
    return re.sub(r" \(.*\)$", "", field).replace("[*]", "").split(".")[-1]


def moved_names(noise, text_noise):
    """Per file, the names of fields that moved with the seed in calibration."""
    out = {}
    for k in [*noise, *text_noise]:
        rel, field = k.split(":", 1)
        out.setdefault(rel, set()).add(leaf(field))
    return out


def sim_by_construction(rel, field, siblings=None):
    """Simulation outputs whatever calibration saw: the sims files, the forecast's "reading" sections, and fields whose
    namesakes in the same file moved with the seed (a seat percentile in one scenario when it moved in another)."""
    return (rel.endswith(".bin") or Path(rel).name.startswith("sims_") or ".reading." in f".{field}"
            or leaf(field) in (siblings or {}).get(rel, ()))


def verdict(rel, fields, noise, text_noise, wt, siblings=None):
    """-> (verdict, failures, warnings). A failure is a deterministic output that changed, or a headline number outside
    its noise. A warning is a simulation output outside its usual noise: rare jumps happen (a near-50/50 race changing
    favourite reshuffles the most likely maps), so these are listed for a look rather than failed."""
    if fields is None:
        return "identical", [], []
    bad, warn, sim = [], [], False
    if rel == LAGGED[0]:
        fields = {f: v for f, v in fields.items() if not f.startswith(LAGGED[1])}
        bad += lagged_check(wt)
    for field, (kind, ad, rd, mism) in fields.items():
        key = f"{rel}:{field}"
        if kind == "mdnum":
            sim = True                                       # numbers in prose; the data files they come from are checked
        elif kind == "text":
            if not mism:
                continue
            cap = max(1, LABEL_FACTOR * text_noise[key]["max"]) if key in text_noise else 0
            if mism <= cap:
                sim = True                                   # a label that follows the simulations
            elif key in text_noise or sim_by_construction(rel, field, siblings):
                warn.append(f"{field}: {mism} label(s) differ" + (f" (seed shifts changed up to {text_noise[key]['max']})" if key in text_noise else ""))
            else:
                bad.append(f"{field}: {mism} value(s) differ")
        elif rd >= REL_TOL:
            tol = K_SIGMA * noise[key]["rms"] if key in noise else 0.0
            if ad <= tol:
                sim = True
            elif key in HEADLINE:
                bad.append(f"{field}: headline moved {ad:.3g}, beyond its noise ({tol:.3g})")
            elif key in noise:
                warn.append(f"{field}: {ad:.3g} vs usual noise up to {tol:.3g} ({ad / tol:.1f}x)")
            elif sim_by_construction(rel, field, siblings):
                warn.append(f"{field}: {ad:.3g} (a simulation output that never moved in calibration)")
            else:
                bad.append(f"{field}: max diff {ad:.3g} (deterministic: never moved with the seed)")
    if bad:
        return "DIFFERS", bad, warn
    if warn:
        return "sim warning", [], warn
    if sim:
        return "sim noise", [], []
    if rel == LAGGED[0]:
        return "identical", [], [f"(apart from {LAGGED[1]}*, which matches the frozen {LAGGED[2]} it copies; the frozen copy lags by one run)"]
    return "rounding", [], []


# ---- modes ----------------------------------------------------------------------------------------------------------
def calibrate(a, day, sha, pyver):
    n = len(CAL_SHIFTS)
    print(f"   calibrating: {n} rebuilds with the seed shifted by 1..{n}, {CAL_WORKERS} at a time")
    num, txt, stale = {}, {}, set()               # key -> list of per-run differences (absent run = 0)

    trees_lock = threading.Lock()                 # git worktree add/remove must not run concurrently

    def one_locked(shift):
        with trees_lock:
            w = Worktree(a.ref, day)
        try:
            run_model(w.path, a.python, day, shift=shift, quiet=True)
            return compare_all(w)
        finally:
            with trees_lock:
                w.remove()

    with ThreadPoolExecutor(max_workers=CAL_WORKERS) as ex:
        runs = list(ex.map(one_locked, CAL_SHIFTS))
    for i, res in enumerate(runs):
        for rel, fields in res.items():
            if fields == "stale":
                stale.add(rel)
                continue
            for field, (kind, ad, rd, mism) in (fields or {}).items():
                if rel == LAGGED[0] and field.startswith(LAGGED[1]):
                    continue                              # checked against the frozen forecast, not by noise
                key = f"{rel}:{field}"
                if kind == "num" and rd >= REL_TOL:
                    num.setdefault(key, [0.0] * n)[i] = ad
                elif kind == "text" and mism:
                    txt.setdefault(key, [0] * n)[i] = mism
    noise = {k: {"rms": float(np.sqrt(np.mean(np.square(v)))), "max": float(max(v)), "moved": int(sum(x > 0 for x in v))}
             for k, v in sorted(num.items())}
    text_noise = {k: {"max": int(max(v)), "moved": int(sum(x > 0 for x in v))} for k, v in sorted(txt.items())}
    NOISE.parent.mkdir(parents=True, exist_ok=True)
    NOISE.write_text(json.dumps({
        "what": f"how each simulation output moved when the forecast's random seed (2026) was shifted by 1..{n}: rms and max "
                f"of the absolute difference from data/final, and in how many of the {n} runs it moved at all. "
                f"check_frozen.py allows {K_SIGMA:g}x the rms for a number and {LABEL_FACTOR}x the max for labels "
                "(text_fields). Anything not listed never moved with the seed and must match to rounding.",
        "ref": f"{a.ref} ({sha})", "environment": pyver, "lock_date": day, "runs": n,
        "stale_files": sorted(stale), "fields": noise, "text_fields": text_noise}, indent=1), encoding="utf-8")
    files = {k.split(":")[0] for k in [*noise, *text_noise]}
    print(f"\nseed-shift noise: {len(noise)} numeric and {len(text_noise)} label fields in {len(files)} files -> {NOISE.relative_to(ROOT)}")


def check(a, day, shift):
    cal = json.loads(NOISE.read_text(encoding="utf-8")) if NOISE.exists() else {}
    noise, text_noise = cal.get("fields", {}), cal.get("text_fields", {})
    siblings = moved_names(noise, text_noise)
    if not cal:
        print("   (no data/checks/sim_noise.json yet: every difference counts as DIFFERS)")
    if shift:
        print(f"   self-test: random seed shifted by {shift}, as a numpy upgrade might; expect 'sim noise', not DIFFERS")
    w = Worktree(a.ref, day, keep=a.keep)
    try:
        print(f"   inputs dated after {day} removed: {', '.join(w.pruned) or 'none'}")
        deprecations = run_model(w.path, a.python, day, shift=shift)
        counts, lines, n_warn = {}, [], 0
        for rel, fields in compare_all(w).items():
            if fields == "stale":
                v, bad, notes = ("by design", [], [BY_DESIGN[rel]]) if rel in BY_DESIGN else ("NOT REBUILT", [], [])
            else:
                v, bad, notes = verdict(rel, fields, noise, text_noise, w.path, siblings)
            counts[v] = counts.get(v, 0) + 1
            n_warn += len(notes) if v in ("sim warning", "DIFFERS") else 0
            if v not in ("identical", "sim noise", "rounding") or (v == "identical" and notes):
                lines.append(f"   {v:11} {rel}" + "".join(f"\n               {x}" for x in bad[:8])
                             + "".join(f"\n               (warning) {x}" if v in ("sim warning", "DIFFERS") else f"\n               {x}"
                                       for x in notes[:8]))
        print(f"\n{len(final_files())} files in data/final: " + ", ".join(f"{n} {v}" for v, n in sorted(counts.items())))
        print("\n".join(lines) if lines else "   every file rebuilt byte for byte")
        if deprecations:
            print(f"\n{len(deprecations)} deprecation/future warning(s) during the run:")
            for msg, step in sorted(deprecations.items(), key=lambda t: t[1]):
                print(f"   [{step}] {msg}")
        else:
            print("\nno deprecation or future warnings during the run")
        ok = not ({"DIFFERS", "NOT REBUILT"} & set(counts))
        result = "FAIL" if not ok else ("PASS WITH WARNINGS" if n_warn else "PASS")
        print(f"\nRESULT: {result}" + (f" (log: {w.path / 'check_log.txt'})" if a.keep else ""))
        if n_warn and ok:
            print("   Warnings are simulation outputs outside their usual noise. A near-50/50 race changing favourite\n"
                  "   reshuffles maps and lists, so an occasional one is expected after a numpy upgrade. Many of them,\n"
                  "   or large multiples, deserve a look. Deterministic outputs and headline numbers all passed.")
        return ok
    finally:
        w.remove()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default="HEAD")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--calibrate-noise", action="store_true")
    ap.add_argument("--seed-shift", type=int, default=0, help="self-test: shift the random seed (use one above 20)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    day, sha = lock_date(), git("rev-parse", "--short", a.ref)
    pyver = subprocess.run([a.python, "-c", "import sys, numpy, pandas, scipy, statsmodels; print(sys.version.split()[0], "
                            "'numpy', numpy.__version__, 'pandas', pandas.__version__, 'scipy', scipy.__version__, "
                            "'statsmodels', statsmodels.__version__)"], capture_output=True, text=True, check=True).stdout.strip()
    print(f"check_frozen: ref {a.ref} ({sha}), lock date {day}, python {a.python}\n   {pyver}")
    if a.ref == "HEAD":   # the worktree holds committed files only: uncommitted model code would go untested
        dirty = git("status", "--porcelain", "--", *MODEL_PATHS)
        if dirty:
            sys.exit("check_frozen rebuilds the committed code, but these model files have uncommitted changes:\n"
                     + "\n".join(f"   {l}" for l in dirty.splitlines()[:20])
                     + "\nCommit them (on a branch) first, then run the check.")
    try:
        if a.calibrate_noise:
            calibrate(a, day, sha, pyver)
        else:
            sys.exit(0 if check(a, day, a.seed_shift) else 1)
    except RuntimeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
