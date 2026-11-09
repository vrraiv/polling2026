"""2026 post-mortem: what if the national environment had been known?

Rescores the frozen forecast with the shared national draw held at E - G for a target environment E (the scenario
explorer's scale: national two-party House margin, D minus R; G = the version's expected environment). House
districts move g_nat * (E - G) and Senate races (sd_nat_senate / sd_nat_house) * (E - G), exactly as
forecast.simulate() couples them; region, lean-slope and race-level errors are re-drawn as there.

    python src/postmortem/whatif_environment.py                    D+8 to D+18
    python src/postmortem/whatif_environment.py --envs 12,13,15.5

Writes data/postmortem/whatif_environment.json and .csv. "forecast" rows are the frozen probabilities and must
equal the scorecard's Brier (a check that the rescoring matches the scorer).
"""
import sys

import numpy as np
import pandas as pd

import frozen as F

N, SEED = 40000, 20261108


def main(envs):
    sc = F.scorecard()
    cs, ch = F.called("senate", sc), F.called("house", sc)
    rng = np.random.default_rng(SEED)
    region = rng.standard_normal((N, len(F.REGIONS))) * F.SIGMA_REGION
    slope = rng.standard_normal(N) * F.SIGMA_SLOPE
    rows, chance, coupling = [], {}, {}
    for v in F.VERSIONS:
        nat = F.national(v)
        G, sd_h, sd_s = nat["G_used"], nat["sd_nat_house_used"], nat["sd_nat_senate_used"]
        coupling[v] = {"senate_per_point": sd_s / sd_h, "house_per_point": F.G_NAT, "senate_over_house": sd_s / sd_h / F.G_NAT}
        s, h = F.races(v, "senate"), F.races(v, "house")
        hf, hc = h[h.fixed.notna()], h[h.fixed.isna()]
        fixed_p = {k: float(f == "D") for k, f in zip(hf.race_key, hf.fixed)}
        rows.append({"version": v, "env": round(G, 2), "kind": "forecast", "nat_error": 0.0, "senate_shift": 0.0, "house_shift": 0.0,
                     "senate_brier": F.brier(dict(zip(s.race_key, s.p_dside)), cs),
                     "house_brier": F.brier(dict(zip(h.race_key, h.p_dem)), ch), "n_senate": len(cs), "n_house": len(ch)})
        for E in envs:
            e = E - G
            ss, hs = sd_s / sd_h * e, F.G_NAT * e
            sw = F.draw_wins(s, rng, N, ss, region, slope)
            hw = F.draw_wins(hc, rng, N, hs, region, slope)
            sen = F.SENATE_NOT_UP_D + sw[:, (s.dside != "I").values].sum(1)
            hou = int((hf.fixed == "D").sum()) + hw.sum(1)
            rows.append({"version": v, "env": E, "kind": "fixed", "nat_error": e, "senate_shift": ss, "house_shift": hs,
                         "senate_brier": F.brier(dict(zip(s.race_key, sw.mean(0))), cs),
                         "house_brier": F.brier({**dict(zip(hc.race_key, hw.mean(0))), **fixed_p}, ch),
                         "n_senate": len(cs), "n_house": len(ch),
                         "senate_d_mean": sen.mean(), "senate_d_p10": np.percentile(sen, 10), "senate_d_p90": np.percentile(sen, 90),
                         "house_d_mean": hou.mean(), "house_d_p10": np.percentile(hou, 10), "house_d_p90": np.percentile(hou, 90)})
            print(f"  {v} D+{E:g}", file=sys.stderr)
        env = G + F.env_draws(v)
        chance[v] = {f"{t:g}": float((env >= t).mean()) for t in envs}
    out = pd.DataFrame(rows)
    F.OUT.mkdir(parents=True, exist_ok=True)
    out.round(4).to_csv(F.OUT / "whatif_environment.csv", index=False)
    realized = {}
    for chamber in ("senate", "house"):
        r = F.settled_margins(chamber, sc)
        realized[chamber] = {"n_settled": len(r), **{f"mean_error_{v}": float((r.actual - r[f"mu_{v}"]).mean()) for v in F.VERSIONS}}
    fixed = out[out.kind == "fixed"]
    best = {v: {c: float(fixed[fixed.version == v].set_index("env")[f"{c}_brier"].idxmin()) for c in ("senate", "house")}
            for v in F.VERSIONS}
    F.write("whatif_environment.json", {
        "question": "How would the frozen forecast have scored if the national environment had been known?",
        "provisional": sc.get("provisional", True), "scorecard_stage": sc.get("stage"),
        "coupling": coupling, "best_env_by_brier": best, "chance_env_at_least": chance, "realized": realized,
        "rows": out.round(4).to_dict("records")})
    cols = ["version", "env", "kind", "senate_shift", "house_shift", "senate_brier", "house_brier", "senate_d_mean", "house_d_mean"]
    pd.set_option("display.width", 200)
    print(out[cols].round(3).to_string(index=False))
    print("best environment by Brier:", best)


if __name__ == "__main__":
    a = sys.argv[1:]
    main([float(x) for x in a[a.index("--envs") + 1].split(",")] if "--envs" in a else [float(x) for x in range(8, 19)])
