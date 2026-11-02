"""MEDSL election returns (Dataverse) and FEC candidates/financial totals (DEMO_KEY)."""
import json
import time

from common import fetch, raw_dir, SESSION, env_key

DATAVERSE = {"house": "doi:10.7910/DVN/IG0UN2", "senate": "doi:10.7910/DVN/PEJ5QU"}


def medsl():
    for k, doi in DATAVERSE.items():
        meta = SESSION.get("https://dataverse.harvard.edu/api/datasets/:persistentId/",
                           params={"persistentId": doi}, timeout=60).json()["data"]["latestVersion"]
        for f in meta["files"]:
            df = f["dataFile"]
            if df["filename"].endswith(".tab"):
                p = fetch("medsl", f"{k}_{df['filename']}",
                          f"https://dataverse.harvard.edu/api/access/datafile/{df['id']}",
                          timeout=600)
                print("medsl", k, df["filename"], p.stat().st_size)


def fec(cycle=2026):
    """Candidate financial totals for House and Senate. DEMO_KEY is rate-limited, so paginate gently."""
    d = raw_dir("fec")
    for office in ["S", "H"]:
        out = d / f"totals_{office}_{cycle}.json"
        if out.exists():
            continue
        rows, page = [], 1
        while True:
            for attempt in range(6):
                r = SESSION.get("https://api.open.fec.gov/v1/candidates/totals/",
                                params={"api_key": env_key("fec_api_key", "DEMO_KEY"), "cycle": cycle, "election_year": cycle,
                                        "office": office, "per_page": 100, "page": page,
                                        "is_active_candidate": "true", "sort": "-receipts"}, timeout=60)
                if r.status_code == 429:
                    time.sleep(30 * (attempt + 1))
                    continue
                r.raise_for_status()
                break
            j = r.json()
            rows += j["results"]
            pages = j["pagination"]["pages"]
            print(f"fec {office} page {page}/{pages}", flush=True)
            if page >= pages:
                break
            page += 1
            time.sleep(0.3 if env_key("fec_api_key") else 1.5)
        out.write_text(json.dumps(rows))
        print("fec", office, len(rows))


if __name__ == "__main__":
    import sys
    for w in sys.argv[1:] or ["medsl", "fec"]:
        globals()[w]()
