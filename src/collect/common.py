"""Shared download helpers: every raw file lands in data/raw/<source>/<date>/ with a manifest."""
import datetime as dt
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
TODAY = dt.date.today().isoformat()
UA = "polling2026-research/0.1 (personal election forecasting project; https://polling2026.vikramrai.com; https://github.com/vrraiv/polling2026)"

SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA


def raw_dir(source: str) -> Path:
    d = RAW / source / TODAY
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log(d: Path, name: str, url: str, nbytes: int):
    mf = d / "manifest.json"
    m = json.loads(mf.read_text()) if mf.exists() else {}
    m[name] = {"url": url, "retrieved": dt.datetime.now().isoformat(timespec="seconds"), "bytes": nbytes}
    mf.write_text(json.dumps(m, indent=2))


def fetch(source: str, name: str, url: str, params=None, headers=None, retries=3, skip_existing=True, timeout=120) -> Path:
    d = raw_dir(source)
    out = d / name
    if skip_existing and out.exists() and out.stat().st_size > 0:
        return out
    last = None
    for i in range(retries):
        try:
            r = SESSION.get(url, params=params, headers=headers, timeout=timeout)
            r.raise_for_status()
            out.write_bytes(r.content)
            _log(d, name, r.url, len(r.content))
            return out
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"failed {url}: {last}")


def latest(source: str, name: str) -> Path:
    """Most recent raw copy of a file."""
    cands = sorted((RAW / source).glob(f"*/{name}"))
    if not cands:
        raise FileNotFoundError(f"{source}/{name}")
    return cands[-1]


def env_key(name: str, default=None):
    """Read a key from .env (falls back to .env.txt, which Windows Notepad sometimes creates). Never printed."""
    import os
    if os.environ.get(name.upper()):
        return os.environ[name.upper()]
    for fn in (".env", ".env.txt"):
        f = ROOT / fn
        if f.exists():
            for line in f.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    if k.strip().lower() == name.lower():
                        return v.strip().strip('"').strip("'")
    return default
