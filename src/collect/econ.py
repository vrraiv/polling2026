"""Economic fundamentals: FRED (current), ALFRED (as-published vintages), BLS LAUS state unemployment."""
from common import fetch, SESSION

NATIONAL = {
    "UNRATE": "unemployment rate",
    "A191RL1Q225SBEA": "real GDP growth, SAAR",
    "A229RX0": "real disposable personal income per capita",
    "CPIAUCSL": "CPI-U",
    "UMCSENT": "UMich consumer sentiment",
    "GASREGW": "regular gasoline price, weekly",
    "PAYEMS": "nonfarm payrolls",
}
# As-published vintages ~5 weeks before each election (what a forecaster would have had)
VINTAGES = {"2018": "2018-10-01", "2022": "2022-10-01", "2026": "2026-10-01",
            "2014": "2014-10-01", "2010": "2010-10-01", "2006": "2006-10-01"}
STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
          "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
          "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]


def fred():
    for s in NATIONAL:
        try:
            fetch("fred", f"{s}.csv", "https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": s})
            print("fred", s)
        except Exception as e:  # noqa: BLE001
            print("FAILED fred", s, e)


def alfred():
    for s in NATIONAL:
        if s == "GASREGW":
            continue  # gas prices are not revised
        for cyc, v in VINTAGES.items():
            try:
                fetch("alfred", f"{s}_{cyc}.csv", "https://alfred.stlouisfed.org/graph/alfredgraph.csv",
                      params={"id": s, "vintage_date": v})
                print("alfred", s, cyc)
            except Exception as e:  # noqa: BLE001
                print("FAILED alfred", s, cyc, e)


def state_fred():
    """State unemployment (<ST>UR) and per-capita personal income (<ST>PCPI, annual) from FRED."""
    for st in STATES:
        for suffix in ["UR", "PCPI", "OTOT"]:  # OTOT = total quarterly personal income
            sid = f"{st}{suffix}"
            try:
                fetch("fred_state", f"{sid}.csv", "https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": sid})
            except Exception as e:  # noqa: BLE001
                print("FAILED", sid, e)
    print("state fred done")


def bls_laus():
    hdr = {"User-Agent": "polling2026 research (contact: project owner)"}
    for f in ["la.data.3.AllStatesS", "la.series", "la.area"]:
        try:
            fetch("bls", f + ".txt", f"https://download.bls.gov/pub/time.series/la/{f}", headers=hdr)
            print("bls", f)
        except Exception as e:  # noqa: BLE001
            print("FAILED bls", f, e)


if __name__ == "__main__":
    import sys
    for w in sys.argv[1:] or ["fred", "alfred", "state_fred", "bls_laus"]:
        globals()[w]()
