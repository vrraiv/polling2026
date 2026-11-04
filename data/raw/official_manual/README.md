# Official results you downloaded yourself

For close Senate races whose official results sites block scripts (AK, ME, NH, ID, OH, FL; KS refuses this
network's location; MI didn't respond; MS posts only certified PDFs), you can download the state's own results file in
your browser and drop it here. The scorecard then uses it instead of Wikipedia for that race.

**Where:** `data/raw/official_manual/<state code>/<date you downloaded it>/<file, exactly as downloaded>`
for example `data/raw/official_manual/OH/2026-11-07/results.csv`. Only the newest date folder per state is read.

**Then run:** `python src/run_scorecard.py --manual` (add `--build` to preview the site).

**What it reads:** CSV / tab- or semicolon-delimited text / Excel (.xlsx, .xls) / a Clarity `summary.json`:
- long files (one row per candidate, per county or precinct: an office/race/contest column, a candidate column, a
  votes column) - county rows are summed;
- wide files (one column per candidate, one row per town or county) on a sheet or file about the US Senate - a
  totals row, if present, must match.

The file must contain exactly one U.S. Senate contest. If it can't be parsed with certainty, the run says why and
the race stays on Wikipedia's numbers; nothing is guessed. PDFs aren't read. Nothing here is typed by hand: the file is
the state's own download.

A manual count settles like any other: it must hold within 1% between two downloads on different days.
