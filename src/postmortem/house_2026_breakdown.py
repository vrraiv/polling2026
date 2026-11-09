"""2026 post-mortem: where the House upsets fell.

Called contested House races, by district lean (PVI band), state, and seat type (incumbent party / open), with the
Democratic wins each version expected (sum of its probabilities) against the wins that happened, and upsets against
the favourite. Also the Senate by seat type, with mean errors on settled counts.

    python src/postmortem/house_2026_breakdown.py

Writes data/postmortem/house_2026_breakdown.json. Provisional while races are uncalled.
"""
import numpy as np
import pandas as pd

import frozen as F

LEAN_BANDS = [-40, -12, -8, -5, -2, 2, 5, 40]     # PVI (Cook, R negative); R+12..R+2 is the "drawn safe enough" band
V = "polls_fundamentals"


def table(r, by):
    g = r.groupby(by, observed=True).agg(n=("y", "size"), d_won=("y", "sum"), d_expected=("p", "sum"),
                                         upsets=("upset", "sum"), upsets_expected=("p_upset", "sum"))
    g["excess_d"] = g.d_won - g.d_expected
    return g.reset_index().round(2)


def main():
    sc = F.scorecard()
    r = F.called("house", sc).merge(F.races(V, "house")[["race_key", "state", "pvi", "inc_party", "open_seat", "n_polls"]], on="race_key")
    r["p"] = r[V]
    r["upset"] = (r.p > 0.5) != (r.y == 1)
    r["p_upset"] = np.where(r.p > 0.5, 1 - r.p, r.p)
    r["lean_band"] = pd.cut(r.pvi, LEAN_BANDS).astype(str)
    r["seat"] = np.where(r.open_seat, "open", "incumbent " + r.inc_party.astype(str))
    band = r[(r.pvi <= -2) & (r.pvi >= -12)]
    s = F.called("senate", sc).merge(F.races(V, "senate")[["race_key", "inc_party"]], on="race_key")
    m = F.settled_margins("senate", sc).rename(columns={"race": "race_key"})[["race_key", "actual", f"mu_{V}"]]
    s = s.merge(m, on="race_key", how="left")
    s["err"] = s.actual - s[f"mu_{V}"]
    sen = s.groupby("inc_party").agg(n=("y", "size"), d_won=("y", "sum"), d_expected=(V, "sum"),
                                     n_settled=("err", "count"), mean_error=("err", "mean")).reset_index().round(2)
    out = {
        "question": "Where did the 2026 House upsets fall: which leans, states and seat types?",
        "version": V, "provisional": sc.get("provisional", True),
        "totals": {"n": len(r), "upsets": int(r.upset.sum()), "upsets_expected": float(r.p_upset.sum()),
                   "d_won": int(r.y.sum()), "d_expected": float(r.p.sum())},
        "by_lean": table(r, "lean_band").to_dict("records"),
        "by_state": table(r, "state").sort_values("excess_d", ascending=False).to_dict("records"),
        "by_seat": table(r, "seat").to_dict("records"),
        "band_R2_R12_by_seat": table(band, "seat").to_dict("records"),
        "upsets": r[r.upset][["race_key", "pvi", "seat", "p", "n_polls"]].sort_values("p").round(3).to_dict("records"),
        "senate_by_seat": sen.to_dict("records"),
    }
    F.write("house_2026_breakdown.json", out)
    for k in ("by_lean", "by_seat", "band_R2_R12_by_seat", "senate_by_seat"):
        print(k); print(pd.DataFrame(out[k]).to_string(index=False))


if __name__ == "__main__":
    main()
