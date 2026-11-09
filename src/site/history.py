"""Build the Election data pages (site/history/): the historical data behind the forecast, presented. Plan: DATA.md,
section 3. Reads only committed data (data/interim, data/final, data/processed, data/scorecard, data/postmortem);
writes site/history/*.html and one CSV per chart in site/history/data/. Charts are drawn in the browser by
site/assets/charts.js from the specs embedded in each page; styles in site/assets/history.css.

    python src/site/history.py

2026 figures that depend on the count are marked provisional while data/scorecard/scorecard.json says so.
"""
import datetime as dt
import html
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "collect"))
from wiki import STATE_ABBR  # noqa: E402

I, F, P, SC, PM = (ROOT / "data" / d for d in ("interim", "final", "processed", "scorecard", "postmortem"))
OUT = ROOT / "site" / "history"
DL = OUT / "data"
NAME = {v: k for k, v in STATE_ABBR.items()}
REGION = {st: r for r, sts in json.loads((F / "error_structure.json").read_text())["regions"].items() for st in sts}
REGIONS = ["Northeast", "Midwest", "South", "West"]

SRC = {
    "wiki": "Wikipedia (CC BY-SA 4.0)", "538": "FiveThirtyEight (CC BY 4.0)", "gallup": "Gallup via the American Presidency Project",
    "vh": "VoteHub (CC BY 4.0)", "cook": "Cook PVI via Wikipedia", "fred": "BLS, BEA via FRED", "model": "polling2026 analysis",
}
LICENCE = "CC BY-SA 4.0"
PAGES = [("index", "Overview"), ("votes", "Vote shares"), ("approval", "Approval and incumbency"),
         ("states", "States and regions"), ("polling", "Polling accuracy"), ("offcycle", "Off-cycle elections")]
DOWNLOADS = []


def J(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dr(v, d=1):
    """D+3.2 / R+3.2 / Even."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "–"
    return "Even" if round(abs(v), d) == 0 else f"{'D' if v > 0 else 'R'}+{abs(v):.{d}f}"


def sg(v, d=1):
    return f"{v:+.{d}f}".replace("-", "−")


def fit(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    b, a = np.polyfit(x, y, 1)
    return float(a), float(b), float(np.corrcoef(x, y)[0, 1])


def within_slope(df, x, y, by):
    """Slope of y on x after removing each group's mean (a fixed effect per group)."""
    xd = df[x] - df.groupby(by)[x].transform("mean")
    yd = df[y] - df.groupby(by)[y].transform("mean")
    return float((xd * yd).sum() / (xd ** 2).sum())


def pt(x, y, tip, **kw):
    return {"x": float(x), "y": float(y), "tip": tip, **kw}


# ---------------- page assembly ----------------
class Page:
    def __init__(self, key, title, lede, desc):
        self.key, self.title, self.lede, self.desc = key, title, lede, desc
        self.parts, self.charts = [], {}

    def add(self, s):
        self.parts.append(s)
        return self

    def h2(self, t, anchor=None):
        return self.add(f'<h2{f" id={anchor!r}" if anchor else ""}>{t}</h2>')

    def p(self, t):
        return self.add(f"<p>{t}</p>")

    def fig(self, cid, title, spec, csv, sources, caption, prov=False, heat=False):
        """Register a chart (spec + CSV download) and return its HTML."""
        spec = dict(spec, title=title)
        self.charts[cid] = spec
        DL.mkdir(parents=True, exist_ok=True)
        csv.to_csv(DL / f"{cid}.csv", index=False)
        DOWNLOADS.append({"file": f"data/{cid}.csv", "title": title, "page": self.key, "sources": sources})
        return (f'<figure class="fig" id="{cid}"><h3>{title}{" <span class=prov>provisional</span>" if prov else ""}</h3>'
                f'<div class="chart{" heat" if heat else ""}" data-chart="{cid}"></div>'
                f'<figcaption>{caption}</figcaption>'
                f'<div class="src"><span>Sources: {"; ".join(sources)}</span><span>Licence: {LICENCE}</span>'
                f'<a href="data/{cid}.csv" download>Download CSV</a></div></figure>')

    def grid(self, *figs):
        return self.add('<div class="grid2">' + "".join(figs) + "</div>")

    def stats(self, items):
        return self.add('<div class="stats">' + "".join(f'<div class="stat"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in items) + "</div>")

    def table(self, head, rows, num=()):
        th = "".join(f'<th{" class=num" if i in num else ""}>{h}</th>' for i, h in enumerate(head))
        tr = "".join("<tr>" + "".join(f'<td{" class=num" if i in num else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
        return self.add(f'<div class="tbl-wrap"><table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></div>')

    def html(self, built):
        nav = "".join(f'<a href="{"./" if k == "index" else k + ".html"}"{" class=on" if k == self.key else ""}>{t}</a>' for k, t in PAGES)
        charts = json.dumps(self.charts, separators=(",", ":")).replace("</", "<\\/")
        title = "Election data" if self.key == "index" else f"{self.title} · Election data"
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(self.desc)}">
<meta name="theme-color" content="#1d1e22">
<link rel="icon" type="image/svg+xml" href="../favicon.svg">
<link rel="stylesheet" href="../assets/history.css">
</head>
<body>
<header class="top"><div class="wrap">
  <div class="topbar"><h1><a href="./">Election data</a></h1><span class="stamp">Built {built} · <a href="../">2026 forecast</a></span></div>
  <nav class="tabs" aria-label="Sections">{nav}</nav>
</div></header>
<main class="wrap">
{"<p class='lede'>" + self.lede + "</p>" if self.lede else ""}
{chr(10).join(self.parts)}
</main>
<footer><div class="wrap">
  Derived data: {LICENCE} (<a href="https://github.com/vrraiv/polling2026/blob/main/LICENSE-DATA.md">terms</a>); code: MIT. Credit the original
  sources: Wikipedia (CC BY-SA 4.0); FiveThirtyEight (CC BY 4.0); VoteHub (CC BY 4.0); Gallup via the American Presidency Project
  (not openly licensed); Cook PVI (Cook Political Report); BLS and BEA via FRED. Full catalogue: <a href="https://github.com/vrraiv/polling2026/blob/main/DATA.md">DATA.md</a>.
</div></footer>
<script>window.CHARTS = {charts};</script>
<script src="../assets/charts.js"></script>
</body>
</html>
"""


# ---------------- shared data ----------------
def load():
    fd = pd.read_csv(I / "fundamentals_dataset.csv")
    pres = {**dict(zip(fd.year, fd.pres_party)), 2024: "D"}
    sc = J(SC / "scorecard.json")
    nat = sc["margins"]["national"]
    return {"fd": fd, "pres": pres, "sc": sc, "prov": bool(sc.get("provisional", True)),
            "nat2026": float(nat["house_vote_margin"]), "nat2026_ready": bool(nat.get("ready"))}


# ---------------- A. vote shares ----------------
def page_votes(D):
    pg = Page("votes", "Vote shares", "How the national vote has moved since 1946, how hard midterms punish the president's "
              "party, and how far apart the states have pulled.",
              "National House vote 1946-2026, midterm losses, state presidential leans and polarization.")
    v = pd.read_csv(I / "house_national_vote.csv")
    v["president"] = v.year.map(D["pres"])
    v["midterm"] = v.year % 4 == 2
    pts = [pt(r.year, r.two_party_margin_D, f"<b>{r.year}</b> {'midterm' if r.midterm else 'presidential year'}<br>House vote {dr(r.two_party_margin_D)}"
              f"<br>President: {'Democrat' if r.president == 'D' else 'Republican'}", color="dem" if r.president == "D" else "rep", hollow=not r.midterm)
           for r in v.itertuples()]
    pts.append(pt(2026, D["nat2026"], f"<b>2026</b> midterm<br>House vote {dr(D['nat2026'])} (partial count)", color="rep", label="2026*"))
    csv = v.rename(columns={"two_party_margin_D": "house_two_party_margin_D"})[["year", "house_two_party_margin_D", "president", "midterm"]]
    csv = pd.concat([csv, pd.DataFrame([{"year": 2026, "house_two_party_margin_D": round(D["nat2026"], 2), "president": "R", "midterm": True}])])
    csv["provisional"] = csv.year == 2026
    big = v.loc[v.two_party_margin_D.abs().nlargest(3).index]
    f1 = pg.fig("house_vote", "National House vote, 1946-2026",
                {"type": "xy", "height": 300, "series": [{"pts": pts, "line": False}],
                 "x": {"min": 1944, "max": 2028, "ticks": list(range(1950, 2030, 10)), "fmt": "year"},
                 "y": {"fmt": "dr0", "label": "Two-party margin"}, "refs": [{"y": 0}],
                 "legend": [{"name": "Democratic president", "color": "dem", "dot": True}, {"name": "Republican president", "color": "rep", "dot": True},
                            {"name": "Hollow: presidential year", "color": "text-3", "hollow": True}]},
                csv, [SRC["wiki"]],
                f"Two-party margin of the national House vote. The widest margins: {', '.join(f'{r.year} ({dr(r.two_party_margin_D)})' for r in big.itertuples())}. "
                f"*2026 is the partial count ({dr(D['nat2026'])}), not yet final.", prov=D["prov"])
    pg.add(f1)

    fd = D["fd"]
    mt = fd[(fd.midterm == 1) & fd.prev.notna() & fd.outcome.notna()].copy()
    mt["change"] = mt.outcome - mt.prev
    p26 = float(fd[fd.year == 2026].prev.iloc[0])
    c26 = -D["nat2026"] - p26
    cats = [str(y) for y in mt.year] + ["2026*"]
    vals = [round(c, 2) for c in mt.change] + [round(c26, 2)]
    colors = ["dem" if p == "D" else "rep" for p in mt.pres_party] + ["rep"]
    tips = [f"<b>{r.year}</b>: president's party {sg(r.change)} pts<br>{dr(r.outcome)} for them, after {dr(r.prev)}<br>Gallup approval {r.approval:.0f}%"
            for r in mt.itertuples()] + [f"<b>2026</b> (partial count): {sg(c26)} pts<br>Gallup-scale approval {fd[fd.year == 2026].approval.iloc[0]:.0f}%"]
    csv = mt[["year", "pres_party", "prev", "outcome", "change", "approval"]].rename(columns={
        "prev": "pres_party_margin_previous", "outcome": "pres_party_margin", "change": "change", "approval": "gallup_approval"})
    csv = pd.concat([csv, pd.DataFrame([{"year": 2026, "pres_party": "R", "pres_party_margin_previous": p26, "pres_party_margin": -D["nat2026"], "change": c26,
                                         "gallup_approval": fd[fd.year == 2026].approval.iloc[0]}])]).round(2)
    worse = (mt.change < c26).sum()
    f2 = pg.fig("midterm_penalty", "The midterm penalty, 1950-2026",
                {"type": "bars", "cats": cats, "series": [{"name": "Change", "values": vals, "colors": colors, "tips": tips, "opacity": [1] * len(mt) + [0.6]}],
                 "y": {"fmt": "signed0", "label": "President's party, change in margin"}, "rotate": True, "height": 280},
                csv, [SRC["wiki"], SRC["gallup"]],
                f"Change in the president's party's House margin from the previous election, in every midterm since 1950. "
                f"The president's party lost ground in {int((mt.change < 0).sum())} of {len(mt)}. "
                f"2026's {sg(c26)} (partial count) is {'the largest' if worse == 0 else f'larger than all but {worse}'}. Approval figures: Gallup.", prov=D["prov"])
    pg.add(f2)

    sp = pd.read_csv(I / "state_presidential.csv")
    sp = sp[sp.state != "DC"]
    rng = np.random.default_rng(7)
    jit = {s: rng.uniform(-1.2, 1.2) for s in sorted(sp.state.unique())}
    pts = [pt(r.year + jit[r.state], r.lean_2p, f"<b>{NAME[r.state]} {r.year}</b><br>{dr(r.margin_2p)} ({dr(r.lean_2p)} vs the nation)",
              color="dem" if r.lean_2p > 0 else "rep", r=2.6, opacity=0.85) for r in sp.itertuples()]
    nat = sp.drop_duplicates("year")[["year", "national_margin_2p"]]
    f3 = pg.fig("state_leans", "Every state's presidential lean, 1992-2024",
                {"type": "xy", "height": 320, "series": [{"pts": pts}], "refs": [{"y": 0, "label": "the nation"}],
                 "x": {"min": 1989, "max": 2027, "ticks": sorted(sp.year.unique().tolist()), "fmt": "year"},
                 "y": {"fmt": "dr0", "label": "State margin minus national margin"}},
                sp[["year", "state", "margin_2p", "national_margin_2p", "lean_2p"]].round(2), [SRC["wiki"]],
                "Each dot is a state: its two-party presidential margin minus the nation's. National margins: "
                + ", ".join(f"{r.year} {dr(r.national_margin_2p)}" for r in nat.itertuples()) + ".")
    pg.add(f3)

    pol = sp.groupby("year").agg(sd=("lean_2p", "std"), close=("margin_2p", lambda m: int((m.abs() < 5).sum()))).reset_index()
    f4 = pg.fig("polarization", "How far apart the states are",
                {"type": "xy", "width": 420, "height": 280, "series": [{"line": True, "color": "ochre", "pts": [pt(r.year, r.sd, f"<b>{r.year}</b>: spread of state leans {r.sd:.1f} pts") for r in pol.itertuples()]}],
                 "x": {"ticks": pol.year.tolist(), "fmt": "year"}, "y": {"fmt": "int", "label": "Spread (SD) of state leans"}},
                pol.rename(columns={"sd": "sd_state_lean", "close": "states_within_5"}).round(2), [SRC["wiki"]],
                f"Standard deviation of the 50 states' leans: {pol.sd.iloc[0]:.1f} points in {pol.year.iloc[0]}, {pol.sd.iloc[-1]:.1f} in {pol.year.iloc[-1]}.")
    f5 = pg.fig("close_states", "States decided by under 5 points",
                {"type": "bars", "cats": [str(y) for y in pol.year], "series": [{"name": "States", "values": pol.close.tolist(), "color": "tint"}],
                 "y": {"fmt": "int", "label": "States"}, "width": 420, "height": 280},
                pol.rename(columns={"sd": "sd_state_lean", "close": "states_within_5"}).round(2), [SRC["wiki"]],
                f"Presidential two-party margin under 5 points: {pol.close.iloc[0]} states in {pol.year.iloc[0]}, {pol.close.iloc[-1]} in {pol.year.iloc[-1]}.")
    pg.grid(f4, f5)
    return pg


# ---------------- B. approval and incumbency ----------------
def page_approval(D):
    pg = Page("approval", "Approval and incumbency", "What the president's standing does to the president's party, when in the term it bites "
              "hardest, and how much being the incumbent is still worth.",
              "Approval and midterm losses, the term-year effect in off-cycle elections, and incumbency in House and governor races.")
    fd = D["fd"]
    mt = fd[(fd.midterm == 1) & fd.prev.notna() & fd.outcome.notna() & fd.approval.notna()].copy()
    mt["change"] = mt.outcome - mt.prev
    a, b, r = fit(mt.approval, mt.change)
    a26 = float(fd[fd.year == 2026].approval.iloc[0])
    c26 = -D["nat2026"] - float(fd[fd.year == 2026].prev.iloc[0])
    pts = [pt(x.approval, x.change, f"<b>{x.year}</b>: approval {x.approval:.0f}%, change {sg(x.change)}", color="dem" if x.pres_party == "D" else "rep", label=str(x.year))
           for x in mt.itertuples()]
    pts.append(pt(a26, c26, f"<b>2026</b> (partial count): approval {a26:.0f}%, change {sg(c26)}", color="rep", label="2026*", hollow=True))
    csv = mt[["year", "pres_party", "approval", "change"]].rename(columns={"approval": "gallup_approval", "change": "pres_party_margin_change"})
    csv = pd.concat([csv, pd.DataFrame([{"year": 2026, "pres_party": "R", "gallup_approval": a26, "pres_party_margin_change": c26}])]).round(2)
    pg.add(pg.fig("approval_midterm", "Approval and the midterm result",
                  {"type": "xy", "height": 320, "series": [{"pts": pts}], "fits": [{"a": a, "b": b, "color": "ochre"}],
                   "x": {"fmt": "int", "label": "Gallup approval before the midterm (%)"}, "y": {"fmt": "signed0", "label": "President's party, change in margin"},
                   "refs": [{"y": 0}], "legend": [{"name": "Democratic president", "color": "dem", "dot": True}, {"name": "Republican president", "color": "rep", "dot": True},
                                                  {"name": f"Fit: {b:.2f} pts per point of approval", "color": "ochre", "line": True}]},
                  csv, [SRC["gallup"], SRC["wiki"]],
                  f"Midterms 1950-2022: each point of approval is worth about {b:.2f} points of House margin to the president's party "
                  f"(correlation {r:.2f}). 2026 (hollow, partial count): approval {a26:.0f}%, the lowest at a midterm since 1946 "
                  f"({fd[fd.year == 1946].approval.iloc[0]:.0f}%, not shown: no previous House margin). "
                  "Approval: Gallup, averaged over mid-July to October.", prov=D["prov"]))

    gm, se = J(P / "governor_model.json"), J(P / "specials_environment.json")
    om, hv = gm["offcycle_m"], se["prospective"]["m_by_half_all_data"]
    cats = ["Governors, year 1 (NJ, VA)", "Governors, year 3 (KY, LA, MS)", "House specials, years 1-2", "House specials, years 3-4"]
    vals = [om["1"], om["3"], hv["years_1_2"], hv["years_3_4"]]
    pg.add(pg.fig("term_year", "When in the term the president's party pays",
                  {"type": "bars", "cats": cats, "series": [{"name": "m", "values": [round(x, 2) for x in vals], "colors": ["tint", "tint", "teal", "teal"]}],
                   "y": {"fmt": "dec1", "label": "Midterm-likeness (m)"}, "refs": [{"y": 1, "label": "a midterm"}, {"y": 0, "label": "a presidential year", "color": "text-3"}],
                   "height": 260},
                  pd.DataFrame({"group": cats, "m": vals}).round(3), [SRC["wiki"], SRC["gallup"], SRC["model"]],
                  "How strongly off-cycle electorates swing against the president, on a scale where 1 is a midterm's swing and 0 a presidential "
                  "year's. Two independent sets of races agree: the first half of a term behaves like a midterm or stronger, the second half barely "
                  "at all. Governors: 35 odd-year races 1999-2025; specials: 77 House specials 2007-2026."))

    hs = J(F / "house_structure.json")["chosen"]["inc_by_year"]
    hc = pd.DataFrame(J(PM / "history_context.json")["approval_effects"]["house_incumbency"]["cycles"])
    ser = [{"name": "All incumbents", "line": True, "color": "ochre", "pts": [pt(int(y), v, f"<b>{y}</b>: {v:.1f} pts") for y, v in hs.items()]},
           {"name": "President's party", "line": True, "color": "tint", "dash": "5 4", "r": 2.6,
            "pts": [pt(x.year, x.inc_premium_pres_party, f"<b>{x.year}</b> president's party: {x.inc_premium_pres_party:.1f}") for x in hc.itertuples()]},
           {"name": "Out-party", "line": True, "color": "teal", "dash": "2 4", "r": 2.6,
            "pts": [pt(x.year, x.inc_premium_out_party, f"<b>{x.year}</b> out-party: {x.inc_premium_out_party:.1f}") for x in hc.itertuples()]}]
    csv = pd.DataFrame({"year": [int(y) for y in hs], "all_incumbents": list(hs.values())}).merge(
        hc[["year", "inc_premium_pres_party", "inc_premium_out_party"]], on="year").round(2)
    pg.add(pg.fig("house_incumbency", "What a House incumbent is worth, 2006-2024",
                  {"type": "xy", "height": 270, "series": ser, "x": {"ticks": list(range(2006, 2026, 2)), "fmt": "year"},
                   "y": {"fmt": "int", "label": "Margin points", "zero": True},
                   "legend": [{"name": s["name"], "color": s["color"], "line": True} for s in ser]},
                  csv, [SRC["wiki"], SRC["cook"], SRC["model"]],
                  f"Incumbent's margin over an open seat with the same lean and environment: {hs['2006']:.0f} points in 2006, "
                  f"{hs['2022']:.0f} in 2022. Split by party it is noisier, and in this period every midterm had an unpopular president."))

    pg.stats([(f"{gm['prior_coef']['inc']:.0f} pts", "Governor incumbency premium, 1998-2025"),
              (f"{J(F / 'house_structure.json')['chosen']['inc']:.1f} pts", "House incumbency premium, 2018-2024"),
              (f"{hs['2006']:.0f} pts", "House incumbency premium, 2006")])

    bd = pd.DataFrame(J(PM / "house_2026_breakdown.json")["band_R2_R12_by_seat"])
    bd = bd[bd.seat != "incumbent I"]
    lab = {"incumbent R": "Republican incumbent", "open": "Open seat", "incumbent D": "Democratic incumbent"}
    cats = [f"{lab[s]} ({n})" for s, n in zip(bd.seat, bd.n)]
    pg.add(pg.fig("incumbents_2026", "2026: Republican incumbents in R+2 to R+12 seats",
                  {"type": "bars", "cats": cats, "series": [{"name": "Forecast Democratic wins", "values": bd.d_expected.round(1).tolist(), "color": "text-3"},
                                                             {"name": "Actual Democratic wins", "values": bd.d_won.tolist(), "color": "dem"}],
                   "y": {"fmt": "int", "label": "Democratic wins"}, "height": 240, "values": True,
                   "legend": [{"name": "Forecast", "color": "text-3"}, {"name": "Won", "color": "dem"}]},
                  bd[["seat", "n", "d_expected", "d_won"]].round(2), [SRC["wiki"], SRC["model"]],
                  f"Contested 2026 House seats leaning Republican by 2 to 12 points. Democrats won {int(bd[bd.seat == 'incumbent R'].d_won.iloc[0])} "
                  f"of {int(bd[bd.seat == 'incumbent R'].n.iloc[0])} held by a Republican incumbent, against {bd[bd.seat == 'incumbent R'].d_expected.iloc[0]:.0f} "
                  "forecast: the incumbency premium protected them far less than in quiet years.", prov=D["prov"]))
    return pg


# ---------------- C. states and regions ----------------
def page_states(D):
    pg = Page("states", "States and regions", "Which states move together, how much of a district's surprise it shares with "
              "the rest of its state, and how far governors run from their state's partisanship.",
              "State swing correlations, the state-level shared House error, regional misses, governor and Senate lean.")
    sp = pd.read_csv(I / "state_presidential.csv")
    sp = sp[sp.state != "DC"]
    lean = sp.pivot(index="state", columns="year", values="lean_2p").sort_index(axis=1)
    sw = lean.diff(axis=1).iloc[:, 1:]
    C = sw.T.corr()
    order = sorted(C.index, key=lambda s: (REGIONS.index(REGION.get(s, "South")), s))
    C = C.loc[order, order]
    M = []
    for ra in REGIONS:
        row = []
        for rb in REGIONS:
            a = [s for s in order if REGION.get(s, "South") == ra]
            b = [s for s in order if REGION.get(s, "South") == rb]
            vals = [C.loc[x, y] for x in a for y in b if x != y]
            row.append(round(float(np.mean(vals)), 2))
        M.append(row)
    within = np.mean([M[i][i] for i in range(4)])
    between = np.mean([M[i][j] for i in range(4) for j in range(4) if i != j])
    pg.add(pg.fig("swing_regions", "Do neighbours swing together?",
                  {"type": "heatmap", "labels": REGIONS, "matrix": M, "vmin": -0.4, "vmax": 0.4, "cell": 76, "margin": 100,
                   "tipNote": "mean correlation of state swings"},
                  pd.DataFrame(M, index=REGIONS, columns=REGIONS).reset_index().rename(columns={"index": "region"}), [SRC["wiki"], SRC["model"]],
                  f"Each state's change in presidential lean (relative to the nation) over the 8 elections from 1996 to 2024, correlated with every other "
                  f"state's, then averaged by Census region. States in the same region correlate {within:.2f} on average; states in different regions "
                  f"{between:.2f}. Eight swings per state make any one pair noisy; the regional averages are steadier.", heat=True))
    top = []
    for s in order:
        o = C.loc[s].drop(s).sort_values(ascending=False)
        top.append([NAME[s], REGION.get(s, "South"), ", ".join(f"{NAME[t]} ({o[t]:.2f})" for t in o.index[:3])])
    full = C.round(3).reset_index().rename(columns={"index": "state"})
    DL.mkdir(parents=True, exist_ok=True)
    full.to_csv(DL / "swing_correlations.csv", index=False)
    DOWNLOADS.append({"file": "data/swing_correlations.csv", "title": "State swing correlations, every pair", "page": "states", "sources": [SRC["wiki"], SRC["model"]]})
    pg.add("<details class='fig'><summary><b>Each state's three closest swing partners</b> "
           "(<a href='data/swing_correlations.csv' download>all pairs, CSV</a>)</summary>")
    pg.table(["State", "Region", "Swings most like"], top)
    pg.add("</details>")

    se = J(PM / "state_error.json")
    comp = pd.DataFrame(se["estimate"]["components"])
    yrs = comp[comp.subset.str.startswith("year ")].copy()
    yrs["year"] = yrs.subset.str[5:].astype(int)
    allc = comp[comp.subset == "all contested"].iloc[0]
    ser = [{"name": "Shared by the state", "line": True, "color": "ochre", "pts": [pt(r.year, r.sd_state_reml, f"<b>{r.year}</b> state-shared SD {r.sd_state_reml:.1f}") for r in yrs.itertuples()]},
           {"name": "District's own", "line": True, "color": "tint", "pts": [pt(r.year, r.sd_idio_reml, f"<b>{r.year}</b> district-specific SD {r.sd_idio_reml:.1f}") for r in yrs.itertuples()]}]
    f1 = pg.fig("state_shared_error", "A district's surprise: its own, or its state's?",
                {"type": "xy", "width": 420, "height": 300, "series": ser, "x": {"ticks": yrs.year.tolist()[::2], "fmt": "year"}, "y": {"fmt": "int", "zero": True, "label": "SD of the surprise (pts)"},
                 "legend": [{"name": s["name"], "color": s["color"], "line": True} for s in ser]},
                yrs[["year", "sd_state_reml", "sd_idio_reml", "share_of_variance"]].round(3), [SRC["wiki"], SRC["cook"], SRC["model"]],
                f"House results 2006-2024 after the national and regional environment, lean and incumbency: the part every district in a state "
                f"shares (about {allc.sd_state_reml:.1f} points) has held steady, while each district's own surprise fell from "
                f"{yrs.sd_idio_reml.iloc[0]:.0f} to {yrs.sd_idio_reml.iloc[-1]:.1f} points.")
    lay = D["sc"]["margins"]["layers"]
    rg = lay["region"]["by_region"]
    names = [r for r in REGIONS if r in rg]
    f2 = pg.fig("regions_2026", "2026: misses by region",
                {"type": "bars", "cats": [f"{r} ({rg[r]['n']})" for r in names],
                 "series": [{"name": "Miss", "values": [round(rg[r]["mean"], 2) for r in names], "err": [round(rg[r]["se"], 2) for r in names],
                             "colors": ["dem" if rg[r]["mean"] > 0 else "rep" for r in names]}],
                 "y": {"fmt": "signed0", "label": "vs the national miss (pts)"}, "width": 420, "height": 300,
                 "refs": [{"y": lay["region"]["sigma_assumed"], "label": "forecast's assumed SD"}, {"y": -lay["region"]["sigma_assumed"]}]},
                pd.DataFrame([{"region": r, **rg[r]} for r in names]).round(3), [SRC["wiki"], SRC["model"]],
                f"Settled 2026 races' errors by region, after removing the national miss (bars: ± one standard error). The forecast assumed regional "
                f"shocks of about {lay['region']['sigma_assumed']:.2f} points.", prov=D["prov"])
    pg.grid(f1, f2)

    b = pd.read_csv(F / "bias_race_level.csv")
    sen = b[b.type_simple == "Sen-G"]
    g = pd.read_csv(I / "governor_dataset.csv")
    g = g[g.contested.astype(bool) & ~g.multi_candidate.astype(bool) & ~g.recall.astype(bool) & g.lean_prev.notna()]
    s_sen = within_slope(sen.rename(columns={"cycle": "year"}), "lean", "act", "year")
    s_gov = within_slope(g, "lean_prev", "margin_2p", "year")
    a1, b1, _ = fit(sen.lean, sen.act)
    a2, b2, _ = fit(g.lean_prev, g.margin_2p)
    pts_s = [pt(r.lean, r.act, f"<b>{NAME.get(r.location, r.location)} Senate {r.cycle}</b><br>lean {dr(r.lean)}, result {dr(r.act)}", color="tint", r=2.4, opacity=0.75) for r in sen.itertuples()]
    pts_g = [pt(r.lean_prev, r.margin_2p, f"<b>{NAME[r.state]} governor {r.year}</b><br>lean {dr(r.lean_prev)}, result {dr(r.margin_2p)}", color="ochre", r=2.4, opacity=0.75) for r in g.itertuples()]
    csv = pd.concat([pd.DataFrame({"office": "Senate", "year": sen.cycle, "state": sen.location, "lean": sen.lean, "result": sen.act}),
                     pd.DataFrame({"office": "Governor", "year": g.year, "state": g.state, "lean": g.lean_prev, "result": g.margin_2p})]).round(2)
    pg.add(pg.fig("lean_offices", "Governors run apart from their states' partisanship",
                  {"type": "xy", "height": 340, "series": [{"name": "Senate", "pts": pts_s}, {"name": "Governor", "pts": pts_g}],
                   "fits": [{"a": a1, "b": b1, "color": "tint", "label": f"Senate {b1:.2f}"}, {"a": a2, "b": b2, "color": "ochre", "label": f"Governor {b2:.2f}"}],
                   "x": {"fmt": "dr0", "label": "State's presidential lean (last election before the race)"}, "y": {"fmt": "dr0", "label": "Result (two-party)"},
                   "refs": [{"y": 0}], "legend": [{"name": "Senate (polled races, 2002-2022)", "color": "tint", "dot": True}, {"name": "Governor (1998-2025)", "color": "ochre", "dot": True}]},
                  csv, [SRC["538"], SRC["wiki"], SRC["model"]],
                  f"Senate results follow presidential lean almost point for point ({s_sen:.2f} per point within a year); governors far less "
                  f"({s_gov:.2f}). Furthest from their state's lean: " + "; ".join(
                      f"{NAME[x.state]} {x.year} ({dr(x.margin_2p)} in a {dr(x.lean_prev, 0)} state)" for x in
                      g.assign(res=(g.margin_2p - (a2 + b2 * g.lean_prev)).abs()).nlargest(4, "res").itertuples()) + "."))

    yrs_s = sen.groupby("cycle").apply(lambda x: fit(x.lean, x.act)[1] if len(x) >= 8 else np.nan, include_groups=False).dropna()
    gg = g[g.year % 2 == 0]
    yrs_g = gg.groupby("year").apply(lambda x: fit(x.lean_prev, x.margin_2p)[1] if len(x) >= 20 else np.nan, include_groups=False).dropna()
    ser = [{"name": "Senate", "line": True, "color": "tint", "pts": [pt(y, v, f"<b>{y}</b> Senate: {v:.2f}") for y, v in yrs_s.items()]},
           {"name": "Governor", "line": True, "color": "ochre", "pts": [pt(y, v, f"<b>{y}</b> governor: {v:.2f}") for y, v in yrs_g.items()]}]
    pg.add(pg.fig("lean_slope_by_year", "How closely results track lean, by year",
                  {"type": "xy", "height": 250, "series": ser, "x": {"fmt": "year", "ticks": list(range(1998, 2026, 4))},
                   "y": {"fmt": "dec1", "label": "Points of margin per point of lean"}, "refs": [{"y": 1, "label": "one for one"}],
                   "legend": [{"name": s["name"], "color": s["color"], "line": True} for s in ser]},
                  pd.DataFrame({"year": sorted(set(yrs_s.index) | set(yrs_g.index))}).assign(
                      senate=lambda d: d.year.map(yrs_s), governor=lambda d: d.year.map(yrs_g)).round(3), [SRC["538"], SRC["wiki"], SRC["model"]],
                  f"Slope of results on presidential lean in each election year (Senate: polled races, years with 8 or more; governors: midterm "
                  f"years, 20 or more races). The Senate has averaged {yrs_s[yrs_s.index >= 2008].mean():.2f} since 2008 (against "
                  f"{yrs_s[yrs_s.index < 2008].mean():.2f} in 2002-2006); governors {yrs_g.mean():.2f}, ranging from {yrs_g.min():.2f} to {yrs_g.max():.2f}."))

    pairs = b.pivot_table(index=["cycle", "location"], columns="type_simple", values="err").dropna()
    pairs = pairs - pairs.groupby(level=0).transform("mean")
    r_gs = float(np.corrcoef(pairs["Gov-G"], pairs["Sen-G"])[0, 1])
    to = se["test_offices"]
    pg.h2("How surprises travel within a state")
    pg.stats([(f"{r_gs:.2f}", f"Governor and Senate polling misses, same state and year ({len(pairs)} pairs, after national misses)"),
              (f"{to['Sen-G']['corr_house_shock_vs_result_resid']:.2f}", "House state shock vs the same state's Senate result"),
              (f"{to['Gov-G']['corr_house_shock_vs_result_resid']:.2f}", "House state shock vs the governor's result"),
              (f"{se['test_persist']['corr_all']:.2f}", "A state's House shock vs its shock the next cycle")])
    pg.p("Statewide polls of the same state miss together moderately; the House districts' shared surprise barely shows in the statewide "
         "races, so a state's Senate polls say little about its House seats. The House shock does carry partly into the next election.")
    return pg


# ---------------- D. polling accuracy ----------------
def page_polling(D):
    pg = Page("polling", "Polling accuracy", "How far final polls have missed, whether the misses share a direction, and what "
              "makes a poll average more or less reliable.",
              "Final-poll misses 1998-2022 for the generic ballot, Senate and governor; error by number of polls; house effects; 2026 poll coverage.")
    cal = J(F / "calibration.json")
    cy = {k: {c["cycle"]: c["mean"] for c in cal[k]["cycles"]} for k in ("House-G-US", "Sen-G", "Gov-G")}
    yrs = sorted(cy["House-G-US"])
    lab = {"House-G-US": ("Generic ballot", "ochre"), "Sen-G": ("Senate", "tint"), "Gov-G": ("Governor", "teal")}
    ser = [{"name": lab[k][0], "line": True, "color": lab[k][1], "pts": [pt(y, cy[k][y], f"<b>{y}</b> {lab[k][0]}: result {dr(cy[k][y])} vs polls") for y in yrs if y in cy[k]]}
           for k in cy]
    csv = pd.DataFrame({"year": yrs, **{lab[k][0].lower().replace(" ", "_"): [cy[k].get(y) for y in yrs] for k in cy}}).round(3)
    over = sum(cy["House-G-US"][y] < 0 for y in yrs)
    pg.add(pg.fig("cycle_misses", "Final polls vs results, 1998-2022",
                  {"type": "xy", "height": 290, "series": ser, "x": {"fmt": "year", "ticks": yrs[::2]}, "y": {"fmt": "dr0", "label": "Result minus final polls"},
                   "refs": [{"y": 0, "label": "polls exactly right"}], "legend": [{"name": s["name"], "color": s["color"], "line": True} for s in ser]},
                  csv, [SRC["538"], SRC["model"]],
                  f"Average miss of the final three weeks' polls in each election; below zero, the result was more Republican than the polls. "
                  f"The generic ballot overstated Democrats in {over} of {len(yrs)} elections."))

    S = np.array([cy["Sen-G"][y] for y in yrs]); G = np.array([cy["Gov-G"][y] for y in yrs]); H = np.array([cy["House-G-US"][y] for y in yrs])
    a, b, r = fit(S, G)
    r_sh, r_gh = float(np.corrcoef(S, H)[0, 1]), float(np.corrcoef(G, H)[0, 1])
    f1 = pg.fig("miss_correlation", "Senate and governor polls miss together",
                {"type": "xy", "width": 420, "height": 320, "series": [{"pts": [pt(s, g_, f"<b>{y}</b>: Senate {dr(s)}, governor {dr(g_)}", label=str(y), color="tint") for y, s, g_ in zip(yrs, S, G)]}],
                 "fits": [{"a": a, "b": b, "color": "ochre", "label": f"r = {r:.2f}"}], "refs": [{"y": 0}], "vrefs": [{"x": 0}],
                 "x": {"fmt": "dr0", "label": "Senate polling miss"}, "y": {"fmt": "dr0", "label": "Governor polling miss"}},
                csv, [SRC["538"], SRC["model"]],
                f"Each election's average Senate and governor misses correlate {r:.2f}: statewide polls tend to err together. Against the generic "
                f"ballot's miss, the correlation is weaker ({r_sh:.2f} Senate, {r_gh:.2f} governor).")
    bins = cal["pollavg_sd_by_n"]["bins"]
    f2 = pg.fig("error_by_polls", "More polls, smaller misses",
                {"type": "bars", "cats": [f"{k} polls" for k in bins], "series": [{"name": "SD", "values": [round(v["sd"], 2) for v in bins.values()], "color": "tint",
                                                                                     "tips": [f"{k} polls ({v['n_races']} races): SD {v['sd']:.1f}" for k, v in bins.items()]}],
                 "y": {"fmt": "int", "label": "Race-level SD of the miss (pts)"}, "width": 420, "height": 320, "values": True},
                pd.DataFrame([{"polls": k, **v} for k, v in bins.items()]).round(3), [SRC["538"], SRC["model"]],
                f"Error of a race's final-three-week average beyond the election's shared miss, by how many polls it holds "
                f"({cal['pollavg_sd_by_n']['n_races']} Senate and governor races). A floor of about {cal['pollavg_sd_by_n']['a']:.1f} points remains however many polls there are.")
    pg.grid(f1, f2)

    b = pd.read_csv(F / "bias_race_level.csv")
    b10 = b[b.cycle >= 2010]
    a, bb, r = fit(b10.lean, b10.resid)
    pts = [pt(x.lean, x.resid, f"<b>{NAME.get(x.location, x.location)} {'Senate' if x.type_simple == 'Sen-G' else 'governor'} {x.cycle}</b><br>lean {dr(x.lean)}; result vs polls {sg(x.resid)} (after the year's average miss)",
              color="tint" if x.type_simple == "Sen-G" else "teal", r=2.4, opacity=0.75) for x in b10.itertuples()]
    pg.add(pg.fig("lean_miss", "Results land further toward a state's lean than its polls",
                  {"type": "xy", "height": 300, "series": [{"pts": pts}], "fits": [{"a": a, "b": bb, "color": "ochre", "label": f"{bb:.2f} per point of lean"}],
                   "x": {"fmt": "dr0", "label": "State's presidential lean"}, "y": {"fmt": "signed0", "label": "Result minus polls, after the year's average miss"},
                   "refs": [{"y": 0}], "legend": [{"name": "Senate", "color": "tint", "dot": True}, {"name": "Governor", "color": "teal", "dot": True}]},
                  b10[["cycle", "type_simple", "location", "lean", "poll", "act", "resid"]].round(3), [SRC["538"], SRC["model"]],
                  f"Senate and governor races 2010-2022: in Republican-leaning states results ran more Republican than the polls, in Democratic-leaning "
                  f"states more Democratic, about {bb:.2f} points per point of lean (correlation {r:.2f})."))

    pe = J(F / "pollster_effects.json")
    t = pd.DataFrame({"pollster": [pe["display"][k] for k in pe["alpha"]], "house_effect": list(pe["alpha"].values()),
                      "polls": [pe["n"][k] for k in pe["alpha"]]})
    t = t[t.pollster.str.strip() != ""]
    show = t[t.polls >= 60].sort_values("house_effect")
    pg.add(pg.fig("house_effects", "Pollster house effects",
                  {"type": "bars", "horizontal": True, "cats": show.pollster.tolist(),
                   "series": [{"values": show.house_effect.round(2).tolist(), "colors": ["dem" if v > 0 else "rep" for v in show.house_effect],
                               "tips": [f"<b>{html.escape(p)}</b>: {sg(v, 2)} pts vs other polls of the same race ({n} polls)" for p, v, n in zip(show.pollster, show.house_effect, show.polls)]}],
                   "x": {"fmt": "signed1", "label": "vs other polls of the race (+ = more Democratic)"}},
                  t.sort_values("polls", ascending=False).round(3), [SRC["538"], SRC["model"]],
                  f"Each pollster's average lean against other polls of the same races, 2010-2022, shrunk toward zero for thin records. Pollsters with 60 "
                  f"or more polls shown ({len(show)}); all {len(t)} in the download. Polls paid for by a party or campaign lean about "
                  f"{pe['beta']:.1f} points toward their sponsor beyond the pollster's own effect."))

    pa = D["sc"]["poll_audit"]
    cats = ["Matched", "Gaps", "VoteHub's choice", "Possible lag", "VoteHub only"]
    keys = ["matched_wikipedia_polls", "missing_probable_gaps", "missing_votehub_choice", "missing_possible_lag", "votehub_only"]
    ser = [{"name": ch.title(), "values": [pa[ch]["totals"][k] for k in keys], "color": c} for ch, c in (("senate", "tint"), ("house", "teal"))]
    pg.add(pg.fig("poll_audit_2026", "2026: VoteHub's polls against Wikipedia's tables",
                  {"type": "bars", "cats": cats, "series": ser, "y": {"fmt": "int", "label": "Polls"}, "height": 260, "values": True,
                   "legend": [{"name": "Senate", "color": "tint"}, {"name": "House", "color": "teal"}]},
                  pd.DataFrame({"category": cats, "senate": ser[0]["values"], "house": ser[1]["values"]}), [SRC["vh"], SRC["wiki"], SRC["model"]],
                  "Every general-election poll in the races' Wikipedia tables as of the final forecast, matched against the polls the forecast used "
                  "(VoteHub). Matched: in both. Gaps: on Wikipedia, probably missing from VoteHub. VoteHub's choice: VoteHub listed the poll under "
                  "another question or version. Possible lag: released too close to the snapshot to tell. VoteHub only: not in Wikipedia's tables."))
    return pg


# ---------------- E. off-cycle ----------------
def page_offcycle(D):
    pg = Page("offcycle", "Off-cycle elections", "Governor races in odd years and House special elections: how they relate to the "
              "national mood, and how the special-election electorate has changed.",
              "Off-year governor races 1999-2025 and House special elections 2007-2026 against the national environment.")
    eo = pd.DataFrame(J(P / "environment_offcycle.json")["by_year"])
    eo["group"] = np.where(eo.year % 4 == 1, "year after a presidential election (NJ, VA)", "year before (KY, LA, MS)")
    ser = [{"name": "Implied by the results", "pts": [pt(r.year, r.implied_env, f"<b>{r.year}</b> ({r.states}; president {r.president})<br>results implied {dr(r.implied_env)}",
                                                          color="tint", r=4.5) for r in eo.itertuples()]},
           {"name": "Estimate (midterm-like)", "pts": [pt(r.year, r["fund_m1"] if isinstance(r, dict) else getattr(r, "fund_m1"), f"<b>{r.year}</b> estimate {dr(getattr(r, 'fund_m1'))}",
                                                           color="text-3", hollow=True) for r in eo.itertuples()]}]
    pg.add(pg.fig("offyear_governors", "Odd-year governor races and the national mood",
                  {"type": "xy", "height": 290, "series": ser, "x": {"fmt": "year", "ticks": list(range(1999, 2026, 2))}, "y": {"fmt": "dr0", "label": "National environment"},
                   "refs": [{"y": 0}], "legend": [{"name": "Environment the results imply", "color": "tint", "dot": True}, {"name": "Estimate from approval and the last House vote", "color": "text-3", "hollow": True}]},
                  eo[["year", "states", "president", "approval", "implied_env", "fund_m1", "prev_vote"]].round(2), [SRC["wiki"], SRC["gallup"], SRC["model"]],
                  "Each odd year's governor results converted to the national environment they imply, against an estimate from approval and the last "
                  "House vote. New Jersey and Virginia, a year after each presidential election, went against the new president all 7 times, usually "
                  "by more than a midterm would. Two to four races a year: each point is noisy."))

    spec = pd.DataFrame(J(P / "specials_environment.json")["specials"])
    spec["date"] = pd.to_datetime(spec.date)
    spec["dyear"] = spec.date.dt.year + (spec.date.dt.dayofyear - 1) / 365.25
    spec["resid"] = spec.implied_env - (spec.e0 + spec.slope)
    spec = spec.sort_values("date")
    roll = [float(spec[(spec.date <= d) & (spec.date > d - pd.Timedelta(days=365))].resid.mean()) for d in spec.date]
    months = pd.date_range(spec.date.min() + pd.Timedelta(days=180), spec.date.max(), freq="MS")
    mgrid = []
    for d in months:
        w = spec[(spec.date <= d) & (spec.date > d - pd.Timedelta(days=365))]
        if len(w) >= 2:
            mgrid.append((d.year + (d.dayofyear - 1) / 365.25, float(w.resid.mean()), len(w), d))
    pts = [pt(r.dyear, r.resid, f"<b>{r.state}-{int(r.district)}</b> {r.date.date()}<br>result {dr(r.margin_2p)} in a {dr(r.pvi * 2)} seat<br>"
              f"Democrats {sg(r.resid)} vs a midterm-like environment", color="dem" if r.president == "D" else "rep", r=3.2, opacity=0.85) for r in spec.itertuples()]
    trail = [pt(x, y, f"{d:%b %Y}: 12-month average {sg(y)} ({n} specials)") for x, y, n, d in mgrid]
    post = spec[spec.date >= "2017-01-20"].resid.mean(); pre = spec[spec.date < "2017-01-20"].resid.mean()
    pg.add(pg.fig("specials", "House special elections against the national mood, 2007-2026",
                  {"type": "xy", "height": 300, "series": [{"pts": pts}, {"name": "12-month average", "line": True, "markers": False, "color": "ochre", "pts": trail}],
                   "x": {"fmt": "year", "ticks": list(range(2008, 2027, 2))}, "y": {"fmt": "signed1", "label": "Democrats vs expectation (environment pts)"},
                   "refs": [{"y": 0}], "vrefs": [{"x": 2017.05, "label": "2017"}],
                   "legend": [{"name": "Democratic president", "color": "dem", "dot": True}, {"name": "Republican president", "color": "rep", "dot": True}, {"name": "12-month average", "color": "ochre", "line": True}]},
                  spec.assign(date=spec.date.dt.date.astype(str))[["date", "state", "district", "president", "pvi", "margin_2p", "implied_env", "resid"]].assign(trailing_12m=roll).round(2),
                  [SRC["wiki"], SRC["cook"], SRC["gallup"], SRC["model"]],
                  f"How much better Democrats did in each House special than a midterm-like environment and the district's lean predicted. Before 2017 "
                  f"they averaged {sg(pre)}; since, {sg(post)}, under both parties' presidents: special-election electorates now lean Democratic."))
    sr = J(P / "single_race_backtest.json")
    cov = sr["interval_coverage"]
    pg.stats([(f"{sr['model']['rmse']:.1f} pts", f"Forecast error, {sr['n']} specials forecast from earlier data only"),
              (f"{sr['naive_last_house_vote']['rmse']:.1f} pts", "Same, using the last House vote as the environment"),
              (f"{cov['50%']:.0%} / {cov['80%']:.0%}", "Results inside the 50% / 80% intervals")])
    return pg


# ---------------- index ----------------
def page_index(D, pages):
    pg = Page("index", "Overview", "The historical record behind the 2026 forecast: eighty years of House votes, three decades of "
              "state results and polls, every governor race since 1998 and every House special since 2007, with downloads.",
              "Historical election data: vote shares, approval and incumbency, state and regional patterns, polling accuracy, off-cycle elections.")
    blurbs = {
        "votes": "The national House vote since 1946, the midterm penalty, and how far apart the states have pulled.",
        "approval": "Approval and midterm losses, when in a term the president's party pays, and the collapse of House incumbency.",
        "states": "Which states swing together, the error a state's districts share, and how governors run apart from partisanship.",
        "polling": "How far final polls have missed since 1998, which misses travel together, house effects, and 2026's poll coverage.",
        "offcycle": "Odd-year governor races and House special elections against the national mood.",
    }
    pg.add('<div class="sections">' + "".join(f'<a class="sec" href="{k}.html"><h3>{t}</h3><p>{blurbs[k]}</p></a>' for k, t in PAGES[1:]) + "</div>")
    if D["prov"]:
        pg.add('<p class="note">2026 counts are still being finalized. Charts that use them are marked <span class="prov">provisional</span> '
               "and will be updated when the results are certified.</p>")
    pg.h2("Sources and licences", "sources")
    pg.p("Everything here is derived from public sources. Derived data is licensed CC BY-SA 4.0 (share-alike follows from the Wikipedia "
         "tables it adapts); please credit the original sources too. The full catalogue, with where each raw file lives, is in "
         "<a href='https://github.com/vrraiv/polling2026/blob/main/DATA.md'>DATA.md</a>.")
    pg.table(["Source", "What it provides", "Terms"], [
        ["Wikipedia", "House, Senate, governor and presidential results; candidates; incumbents; specials; 2026 race tables", "CC BY-SA 4.0"],
        ["Cook Political Report (via Wikipedia)", "District and state lean (PVI); expert ratings with other raters", "Their figures; credit by name"],
        ["FiveThirtyEight (GitHub and archived poll files)", "Final-three-week polls with results 1998-2023; poll files 2016-2024; pollster ratings", "CC BY 4.0"],
        ["VoteHub", "2025-26 polls: Senate, House, governor, generic ballot, approval", "CC BY 4.0"],
        ["American Presidency Project", "Gallup presidential approval, 1941-2021", "Not openly licensed; Gallup's data, credited"],
        ["FRED (St. Louis Fed)", "Inflation, gas prices, income, unemployment (BLS, BEA, EIA)", "Public domain"],
        ["Federal Election Commission", "Candidate fundraising totals", "Public domain"],
        ["State election offices", "2026 official results", "Public records"],
    ])
    pg.h2("Downloads", "downloads")
    rows = [[f"<a href='{d['file']}' download>{d['file'].split('/')[-1]}</a>", d["title"], f"<a href='{d['page']}.html'>{dict(PAGES)[d['page']]}</a>",
             "; ".join(d["sources"])] for d in DOWNLOADS]
    pg.table(["File", "Contents", "Page", "Sources"], rows)
    return pg


def main():
    D = load()
    built = dt.date.today().isoformat()
    OUT.mkdir(parents=True, exist_ok=True)
    pages = [page_votes(D), page_approval(D), page_states(D), page_polling(D), page_offcycle(D)]
    pages.insert(0, page_index(D, pages))
    for pg in pages:
        (OUT / ("index.html" if pg.key == "index" else f"{pg.key}.html")).write_text(pg.html(built), encoding="utf-8")
    sizes = {p.name: f"{p.stat().st_size / 1024:.0f} KB" for p in sorted(OUT.glob("*.html"))}
    print(f"site/history/: {len(pages)} pages, {len(DOWNLOADS)} downloads", sizes)


if __name__ == "__main__":
    main()
