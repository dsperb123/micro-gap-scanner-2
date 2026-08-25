# Micro Gap Scan — NASDAQ + NYSE

A weekly screen of US large caps that ran hard last week, with a column telling you
whether a **micro gap** formed on the weekly chart, and a two-month trend chart of how
many bull micro gaps are appearing across the market each week.

Runs itself every Saturday morning on GitHub Actions and publishes to GitHub Pages.

---

## What it screens for

Every stock listed on NASDAQ or NYSE that clears all five:

| Filter | Threshold |
|---|---|
| Last completed week's gain | greater than **4%** |
| Price | **$5 – $900** |
| Price vs 20-week EMA | **above** it |
| ADR% | greater than **1.5** |
| Market cap | greater than **$1B** |

**On ADR%** — this is Average Daily *Range*, not volume:
`ADR% = 100 × (mean(high ÷ low over the last 20 daily bars) − 1)`.
It's the Qullamaggie/Stockbee volatility measure. If you actually meant a volume
filter, see [Changing the filters](#changing-the-filters) — it's a two-line edit.

## What the columns tell you

| Column | Meaning |
|---|---|
| W-2·W-1·W0 | The three real weekly candles, with the gap void shaded |
| Gap | Bull, Bear, or None on the last completed week |
| Wk gain % | Close-to-close change over the last completed week |
| ADR % | 20-day average daily range |
| % > 20wEMA | How far the close sits above the 20-week EMA |
| % below 52w / ATH | Distance under each high — 0 means sitting at it |
| Near high | Flags `52w` and/or `ATH` when within 10% |
| Industry | Nasdaq's broad sector group |
| Sub-industry | Nasdaq's detailed industry group |

Sort by Industry or Sub-industry and switch the gap filter to **Bull** to see whether
gaps are clustering in one corner of the market.

## The industry panel

**Where the gaps are** follows the chart's date range. Move the From/To dropdowns and
it re-tallies bull micro gaps by industry across exactly that window, showing both the
count and each industry's share of the total. Set it to a single week for a snapshot,
or to a year to see which sectors have been producing gaps persistently rather than in
one burst.

The share column is the one to read when comparing windows of different lengths — raw
counts scale with the number of weeks selected, shares do not.

Per-week industry tallies are stored in `history.json`, so this needs a scan run with
a version of `run_scan.py` that records them. If the panel says "among this week's
matches", the history predates that field and a fresh scan will fix it.

## The micro gap definition

Three consecutive weekly candles W-2, W-1, W0, where W0 is the week being evaluated.
This is exactly the `microGapBull` / `microGapBear` condition from your
`Open Micro Gaps with Patterns` Pine indicator:

```
Bull:  low[W0]  >  high[W-2]      clean gap up, zero overlap with W-2
       low[W-1] >= low[W-2]       rising staircase of lows
       low[W0]  >= low[W-1]

Bear:  high[W0]  <  low[W-2]      mirror image
       high[W-1] <= high[W-2]
       high[W0]  <= high[W-1]
```

## Why the bear count is always zero

A bear micro gap needs `high[W0] < low[W-2]` — the whole week trading below the low of
two weeks ago. A stock that gained more than 4% over that same week essentially cannot
do this. The two conditions fight each other, so the Bear column is near-permanently
empty by construction, not because anything is broken.

It's kept in place to catch the freak exception. If you want to actually hunt bear
micro gaps, invert the gain filter — set `min_weekly_gain_pct` to a negative number
such as `-4.0` and change the comparison in `run_scan.py` from:

```python
if gain is None or gain <= min_gain:
```

to `gain >= min_gain`. That gives you the mirror screen: stocks that dropped hard,
below their 20-week EMA, which is where bear gaps actually live. Worth running as a
separate repo rather than bolting a mode switch onto this one.

## The trend chart

Green bars count bull micro gaps across the **whole scanned universe** each week.
The blue line counts the subset that also cleared the gain, price and EMA filters
as at that week.

**Choosing the time period.** The **From** and **To** dropdowns above the chart set
any window you like out of the stored history — pick a start week, pick an end week,
and the chart redraws between them. The badge next to them shows the span in weeks
and months. Picking a From later than the To just swaps them rather than erroring.

The **Jump to** buttons are shortcuts, not a separate mode: they resize the window to
9w, 13w, 6mo or 1y ending on whatever **To** week is currently selected. So set To to
February 2026, click 6mo, and you get the six months up to February. **All** shows
everything stored; **Latest** slides the current span forward to the newest week
without changing its length.

Both series are labelled with their counts: the number above each green bar is the
universe-wide bull gap count, and the number on each blue dot is how many of those
also passed the full screen. Hovering adds the percentage and how many stocks were
scanned that week. Labels are budgeted by pixel width and drop out automatically once
a window gets too wide to fit them, so the chart stays readable whether you are
looking at 9 weeks or 104.

Two years of weekly history are stored by default, which is what `history_weeks: 104`
in `config.json` controls. Raise it if you want to go further back — the data is
already downloaded, so a longer history costs nothing extra in run time.

Long windows automatically thin their labels and drop the per-bar numbers so the
chart stays readable at 104 bars.

The history is rebuilt from price data on every run rather than accumulated, so the
chart is full from the very first scan instead of taking two years to fill. One
consequence worth knowing: market cap and ADR% are measured as of today and are not
applied retrospectively, so the counts describe gap activity within the current
universe rather than a true point-in-time screen. The further back you scroll, the
more that matters — a company worth $1B today may have been worth $200M in 2024.

Coverage also drifts: recent listings have no history, so older weeks are measured
across fewer stocks (about 2,490 in Aug 2024 versus 2,698 now). Compare weeks using
the percentage in the hover tooltip rather than the raw bar height when you are
looking across long spans.

One thing the two-year view makes obvious: the biggest bull gap clusters cluster
around market-wide recovery thrusts rather than steady uptrends. The largest readings
in the stored history land on the rebounds off sharp drawdowns, which is worth
knowing before you read a high count as broad strength.

## Appearance

The dashboard is dark by default. If you ever want it light again, the entire palette
is the `:root` block at the top of `docs/index.html` — every colour in the page is
drawn from those variables, so swapping them is the whole job.

---

## Setup

You need a GitHub account. Nothing is installed on your machine unless you want to
run scans locally.

### 1. Create the repository

On GitHub, click **New repository**. Name it `micro-gap-scanner`, set it to **Public**
(GitHub Pages needs public on the free plan), and **do not** tick "Add a README".
Click **Create repository**.

### 2. Upload these files

On the empty repo page, click **uploading an existing file**. Unzip the bundle, then
drag in everything — `screener/`, `docs/`, `.github/`, `README.md`,
`requirements.txt`, `config.json`, `.gitignore`.

Confirm the folder structure survived the upload. It must look like this:

```
micro-gap-scanner/
├─ .github/workflows/weekly_scan.yml
├─ screener/
│  ├─ __init__.py
│  ├─ gaps.py
│  ├─ metrics.py
│  ├─ run_scan.py
│  └─ universe.py
├─ docs/
│  ├─ index.html
│  ├─ results.json
│  └─ history.json
├─ config.json
├─ requirements.txt
├─ .gitignore
└─ README.md
```

If the browser flattened the folders, upload each folder separately — drag `screener`
on its own, commit, then drag `.github`, and so on.

Scroll down and click **Commit changes**.

### 3. Let Actions write to the repo

**Settings** → **Actions** → **General** → scroll to **Workflow permissions** →
select **Read and write permissions** → **Save**.

The scan commits its results back to the repo, so it will fail without this.

### 4. Turn on GitHub Pages

**Settings** → **Pages** → under **Build and deployment**, set Source to
**Deploy from a branch**, branch to **main**, folder to **/docs** → **Save**.

Wait a minute or two, then your dashboard is live at:

```
https://<your-username>.github.io/micro-gap-scanner/
```

Results from the bundled scan are already in place, so it should render immediately.

### 5. Run your first fresh scan

**Actions** tab → **Weekly micro gap scan** in the left sidebar → **Run workflow** →
**Run workflow**.

A full run takes roughly 15–25 minutes, mostly spent downloading price history for
about 2,700 stocks. Watch the live log by clicking into the run. When it finishes,
reload the dashboard — hard-refresh if your browser holds the old JSON.

From then on it runs itself at 08:00 UTC every Saturday, which is Saturday evening
in Melbourne — ready before your Sunday review.

---

## Changing the filters

Edit `config.json` on GitHub (open the file, click the pencil icon, commit). Then
re-run the workflow.

```json
{
  "min_weekly_gain_pct": 4.0,
  "min_price": 5.0,
  "max_price": 900.0,
  "ema_length": 20,
  "min_adr_pct": 1.5,
  "adr_length": 20,
  "min_market_cap": 1000000000,
  "near_high_threshold_pct": 10.0,
  "history_weeks": 9,
  "chunk_size": 180,
  "chunk_pause_seconds": 1.0
}
```

`history_weeks` sets how far back the trend chart can scroll — 104 is two years.
Raise it for more; it costs nothing extra since the data is already downloaded.

Lower `chunk_size` if Yahoo starts rate-limiting and chunks come back empty.

## Running it locally

```bash
pip install -r requirements.txt
python -m screener.run_scan --limit 400   # fast smoke test
python -m screener.run_scan               # full run
cd docs && python -m http.server 8000     # then open localhost:8000
```

`--limit` caps the universe so you can check the plumbing in about 90 seconds.

## When something breaks

**Dashboard says it couldn't read results.json** — the scan hasn't produced output
yet, or Pages is serving a stale cache. Run the workflow, wait for the green tick,
then hard-refresh.

**Workflow fails on the commit step** — workflow permissions are still read-only.
Go back to step 3.

**A run returns far fewer stocks than usual** — Yahoo throttles bursts. Drop
`chunk_size` to 100 and raise `chunk_pause_seconds` to 2.

**Nasdaq listings call fails** — it retries three times with a backoff. If it still
fails the run aborts rather than publishing a half-universe, which would make the
trend chart lie. Just re-run it.

---

Prices from Yahoo Finance. Listings, market caps and industry groups from Nasdaq.
Weekly bars close Friday. Not investment advice.
