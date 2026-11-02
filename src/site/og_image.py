"""Draw the 1200x630 link-preview card (site/og.png) from the current forecast, so it refreshes with every build."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS = Path("C:/Windows/Fonts")
BG, SURF, BORDER = "#1d1e22", "#23252b", "#363a47"
TEXT, TEXT2, TEXT3 = "#e8e6e1", "#a9adb8", "#80848f"
TINT, OCHRE, DEM, REP, PRIMARY = "#8e9fc4", "#b58835", "#5a8ad2", "#d0605a", "#3a4660"


def font(name, size):
    for n in (name, "segoeui.ttf"):
        try:
            return ImageFont.truetype(str(FONTS / n), size)
        except OSError:
            continue
    return ImageFont.load_default()


def q(hist, p):
    c = np.cumsum(hist) / np.sum(hist)
    return int(np.searchsorted(c, p))


def make(models, out_path, updated, final=False):
    F, A, PO = models["polls_fundamentals"], models["polls_fundamentals_biasadj"], models["polls_only"]
    im = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1200, 8], fill=OCHRE)
    d.text((60, 44), "2026 Midterm Forecast", font=font("segoeuib.ttf", 46), fill=TEXT)
    d.text((60, 104), (f"Final pre-election forecast · {updated}" if final else f"Polls + estimated fundamentals · updated {updated}"),
           font=font("segoeui.ttf", 22), fill=OCHRE if final else TEXT3)

    def card(x, title, pF, pA, hF, hA, thr, pP, hP):
        d.rounded_rectangle([x, 160, x + 520, 560], radius=18, fill=SURF, outline=BORDER, width=2)
        d.text((x + 28, 184), title, font=font("seguisb.ttf", 22), fill=TEXT2)
        lo, hi = min(round(100 * v) for v in (pA, pF, pP)), max(round(100 * v) for v in (pA, pF, pP))
        d.text((x + 26, 214), f"{lo}–{hi}%", font=font("segoeuib.ttf", 78), fill=TEXT)
        d.text((x + 28, 314), "chance Democrats win", font=font("segoeui.ttf", 24), fill=TEXT2)
        meds = [q(h, .5) for h in (hF, hA, hP)]
        r = [min(q(h, .025) for h in (hF, hA, hP)), max(q(h, .975) for h in (hF, hA, hP))]
        seats = f"{min(meds)}–{max(meds)}" if min(meds) != max(meds) else f"{meds[0]}"
        d.text((x + 28, 362), f"Dem seats: {seats}", font=font("seguisb.ttf", 28), fill=TEXT)
        d.text((x + 28, 400), f"95% range {r[0]}–{r[1]} · {thr} for control", font=font("segoeui.ttf", 20), fill=TEXT3)
        for i, (lab, p, col) in enumerate([("Polls only", pP, "#2f9e86"), ("Polls + fund.", pF, TINT), ("Bias-adjusted", pA, OCHRE)]):
            y = 440 + i * 36
            d.rectangle([x + 28, y + 12, x + 44, y + 16], fill=col)
            d.text((x + 52, y), lab, font=font("segoeui.ttf", 21), fill=TEXT2)
            bx, bw = x + 180, 230
            d.rounded_rectangle([bx, y + 6, bx + bw, y + 22], radius=6, fill=REP)
            d.rounded_rectangle([bx, y + 6, bx + int(bw * p), y + 22], radius=6, fill=DEM)
            d.text((bx + bw + 14, y - 1), f"{round(100 * p)}%", font=font("seguisb.ttf", 22), fill=TEXT)

    card(60, "HOUSE", F["house"]["p_dem_majority"], A["house"]["p_dem_majority"], F["house"]["hist"], A["house"]["hist"], 218,
         PO["house"]["p_dem_majority"], PO["house"]["hist"])
    card(620, "SENATE", F["senate"]["p_dem_control_without_osborn"], A["senate"]["p_dem_control_without_osborn"],
         F["senate"]["hist"], A["senate"]["hist"], 51, PO["senate"]["p_dem_control_without_osborn"], PO["senate"]["hist"])
    d.text((60, 584), "Three versions: polls only · polls + fundamentals · bias-adjusted", font=font("segoeui.ttf", 20), fill=TEXT3)
    d.text((1140, 584), "polling2026.vikramrai.com", font=font("segoeui.ttf", 20), fill=TINT, anchor="ra")
    im.save(out_path, optimize=True)
