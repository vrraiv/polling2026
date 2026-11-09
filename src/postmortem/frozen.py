"""Shared loaders for the post-mortem scripts: the frozen forecast (data/final/), its error parameters, the scorecard,
and the race-level simulation pieces of forecast.simulate(). Read-only: nothing here touches data/final/."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FINAL = ROOT / "data" / "final"
SCORECARD = ROOT / "data" / "scorecard"
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "data" / "postmortem"
VERSIONS = ["polls_only", "polls_fundamentals", "polls_fundamentals_biasadj"]


def _j(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# error structure exactly as frozen (forecast.py reads the same files from data/processed at build time)
DF_T = _j(FINAL / "poll_settings.json")["chosen"]["df_t"]
T_SCALE = np.sqrt((DF_T - 2) / DF_T)                   # scaled t has the stated SD
_ES = _j(FINAL / "error_structure.json")
SIGMA_REGION = _ES["sigma_region"]
SIGMA_SLOPE = _ES["lean_slope"]["all"]["sd_true"]
REGIONS = ["Northeast", "Midwest", "South", "West"]
STATE_REGION = {st: r for r, sts in _ES["regions"].items() for st in sts}
G_NAT = _j(FINAL / "house_structure.json")["chosen"]["g_nat"]   # House districts per point of national margin
SENATE_NOT_UP_D = _j(FINAL / "sims_polls_fundamentals.json")["senate_not_up_d"]


def national(version):
    """G_used (expected national House margin), sd_nat_house_used, sd_nat_senate_used, ..."""
    return _j(FINAL / f"summary_{version}.json")["national"]


def races(version, chamber):
    return pd.read_csv(FINAL / f"{chamber}_{version}.csv")


def scorecard():
    return _j(SCORECARD / "scorecard.json")


def called(chamber, sc=None):
    """Contested races with a called winner: race_key, y (1 = D side won), and each version's probability."""
    r = pd.DataFrame((sc or scorecard())[chamber]["races"])
    return r[r.contested & r.y.notna()].copy()


def settled_margins(chamber, sc=None):
    r = pd.DataFrame((sc or scorecard())["margins"][f"{chamber}_margins"])
    return r[r.settled & r.actual.notna()].copy()


def env_draws(version):
    """National-environment error of each published simulation (the explorer's file), in House-margin points."""
    m = _j(FINAL / f"sims_{version}.json")
    b = (FINAL / f"sims_{version}.bin").read_bytes()
    n = m["n"]
    return np.frombuffer(b, "<i2", n, 4 * n) * m["nat_scale"]


def region_index(df):
    return np.array([REGIONS.index(STATE_REGION.get(st, "South")) for st in df.state])


def idio_sd(df, extra_var=0.0):
    """Race-level SD left after the correlated layers, as forecast.correlated_part(); extra_var carves out further
    shared variance (e.g. a state shock) while each race keeps its total variance."""
    lean = 2.0 * df.pvi.values
    sd = df.sd_race.values
    return np.sqrt(np.maximum(sd ** 2 - (SIGMA_REGION ** 2 + (SIGMA_SLOPE * lean) ** 2 + extra_var), (0.5 * sd) ** 2))


def draw_wins(df, rng, n, shift, region, slope, state_shock=None, state_sd=0.0):
    """Win draws (n x races). shift: national move per draw (scalar or length-n array) already in this chamber's
    units. region (n x 4) and slope (n) are shared across chambers, as in forecast.simulate(). state_shock: optional
    (n x states) array with columns ordered as sorted(df.state.unique())."""
    ridx, lean = region_index(df), 2.0 * df.pvi.values
    idio = idio_sd(df, state_sd ** 2)
    sidx = df.state.map({s: i for i, s in enumerate(sorted(df.state.unique()))}).values
    win = np.empty((n, len(df)), bool)
    for j in range(len(df)):
        m = df.mu.values[j] + shift + region[:, ridx[j]] + slope * lean[j] + rng.standard_t(DF_T, n) * T_SCALE * idio[j]
        if state_shock is not None:
            m = m + state_shock[:, sidx[j]]
        win[:, j] = m > 0
    return win


def brier(p, races_called):
    """p: {race_key: probability}; races_called: called() frame."""
    return float(((races_called.race_key.map(p) - races_called.y) ** 2).mean())


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=_default), encoding="utf-8")
    print(f"wrote data/postmortem/{name}")


def _default(x):
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return None if np.isnan(x) else float(x)
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.bool_,)):
        return bool(x)
    raise TypeError(type(x))
