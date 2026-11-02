"""Historical inputs for estimating the fundamentals model.

- Gallup presidential approval, FDR-Trump (American Presidency Project public Google Sheet, one tab per president)
- National House popular vote by party, 1946-2022 (Wikipedia per-year election pages, infobox)
- FRED long series: CPI (CPIAUCSL), gasoline CPI (CUUR0000SETB01, from 1935), real disposable income per capita (A229RX0, 1959+), unemployment (UNRATE)
"""
import re
import sys
from io import StringIO
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import fetch, latest, ROOT, SESSION  # noqa: E402

SHEET = "1iEl565M1mICTubTtoxXMdxzaHzAcPTnb3kpRndsrfyY"
GIDS = ["0", "1015541111", "1067240630", "1407107120", "148211037", "1517284305", "1868734071", "1904170856", "1957483948",
        "452265038", "460040875", "566304079", "671375968", "897221739"]


def approval():
    rows = []
    for g in GIDS:
        p = fetch("ucsb", f"approval_gid{g}.csv", f"https://docs.google.com/spreadsheets/d/{SHEET}/export",
                  params={"format": "csv", "gid": g})
        df = pd.read_csv(p)
        df.columns = [c.strip() for c in df.columns]
        if "End Date" not in df.columns:
            print("skip gid", g, list(df.columns)[:4]); continue
        df["gid"] = g
        rows.append(df)
    a = pd.concat(rows)
    a["end"] = pd.to_datetime(a["End Date"], errors="coerce")
    a = a.dropna(subset=["end"]).drop_duplicates(["Start Date", "End Date", "Approving"]).sort_values("end")
    out = ROOT / "data/interim/gallup_approval.csv"
    a[["Start Date", "End Date", "end", "Approving", "Disapproving", "gid"]].to_csv(out, index=False)
    print("approval polls", len(a), a.end.min().date(), a.end.max().date())


def house_vote(years=range(1946, 2025, 2)):
    rows = []
    for y in years:
        t = f"{y}_United_States_House_of_Representatives_elections"
        import time
        from common import raw_dir
        if not (raw_dir("wikipedia_hist") / (t + ".html")).exists():
            time.sleep(2.5)
        out = raw_dir("wikipedia_hist") / (t + ".html")
        if not out.exists():
            # action API (separate rate limit from the REST endpoint)
            for attempt in range(6):
                r = SESSION.get("https://en.wikipedia.org/w/api.php", params={"action": "parse", "page": t, "prop": "text",
                                "format": "json", "formatversion": 2}, timeout=60)
                if r.status_code == 429:
                    time.sleep(20 * (attempt + 1)); continue
                r.raise_for_status(); break
            out.write_text(r.json()["parse"]["text"], encoding="utf-8")
        p = out
        html = p.read_text(encoding="utf-8")
        tables = pd.read_html(StringIO(html))
        party = pct = None
        for t in tables[:4]:
            flat = [[str(x).replace(" ", " ").strip() for x in r] for r in t.itertuples(index=False)]
            pr = next((r for r in flat if r[0] == "Party"), None)
            pc = next((r for r in flat if r[0] == "Percentage"), None)
            if pr and pc:
                party, pct = pr, pc
                break
        shares = {}
        for name, v in zip(party[1:], pct[1:]):
            if name in ("Democratic", "Republican"):
                shares[name] = float(re.match(r"[\d.]+", v).group())
        rows.append({"year": y, "dem_pct": shares.get("Democratic"), "rep_pct": shares.get("Republican")})
    df = pd.DataFrame(rows)
    df["two_party_margin_D"] = 100 * (df.dem_pct - df.rep_pct) / (df.dem_pct + df.rep_pct)
    df.to_csv(ROOT / "data/interim/house_national_vote.csv", index=False)
    print(df.to_string(index=False))
    return rows


def fred_long():
    for s in ["CPIAUCSL", "CUUR0000SETB01", "CUSR0000SETB01", "A229RX0", "UNRATE"]:
        fetch("fred", f"{s}.csv", "https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": s})
    print("fred long series ok")


if __name__ == "__main__":
    for w in sys.argv[1:] or ["approval", "fred_long"]:
        r = globals()[w]()
        if w == "house_vote":
            for x in r: print(x)
