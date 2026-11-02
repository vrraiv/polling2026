"""What the adjusted model's move comes from: the mean shift vs. the narrower national error, and the sensitivity of
control probabilities to the size of the national shift.  Writes data/processed/bias_decomposition.json"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))
import forecast as F  # noqa: E402


def main():
    res = {}
    cases = [("unadjusted", dict(shift=0.0, bias_removed=False)),
             ("shift_only_sd_unchanged", dict(shift=F.BIAS_ADJ, bias_removed=False, senate_shift=F.SENATE_BIAS_ADJ, use_lean=F.ADJ_USE_LEAN)),
             ("sd_only_no_shift", dict(shift=0.0, bias_removed=True)),
             ("adjusted", dict(shift=F.BIAS_ADJ, bias_removed=True, senate_shift=F.SENATE_BIAS_ADJ, use_lean=F.ADJ_USE_LEAN)),
             ("flat_minus1", dict(shift=-1.0, bias_removed=True)), ("flat_minus2", dict(shift=-2.0, bias_removed=True)),
             ("flat_minus3", dict(shift=-3.0, bias_removed=True)), ("flat_minus4", dict(shift=-4.0, bias_removed=True))]
    for lab, kw in cases:
        _, _, r = F.run("polls_fundamentals", tag="_decomp", **kw)
        res[lab] = {"shift": kw["shift"], "senate_shift": r["national"]["senate_bias_shift"], "lean": r["national"]["senate_lean_correction"],
                    "sd_nat_house": float(r["national"]["sd_nat_house_used"]), "sd_nat_senate": float(r["national"]["sd_nat_senate_used"]),
                    "p_sen": r["senate"]["p_dem_control_without_osborn"], "sen_seats": r["senate"]["dem_seats_mean"],
                    "p_house": r["house"]["p_dem_majority"], "house_seats": r["house"]["dem_seats_mean"]}
        print(lab, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in res[lab].items()})
    for f in F.OUT.glob("*_decomp*"):
        f.unlink()
    (F.OUT / "bias_decomposition.json").write_text(json.dumps(res, indent=1))
    F.run("polls_fundamentals")  # restore national_inputs.json to the base model


if __name__ == "__main__":
    main()
