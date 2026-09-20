# User manual

Pick the section that matches you. Every path leads to the same numbers.

| If you are… | Go to |
|---|---|
| Not a programmer, want to click around | [A. No code](#a-no-code) |
| An Excel / Google Sheets person | [B. Excel and Google Sheets](#b-excel-and-google-sheets) |
| Comfortable with SQL | [C. SQL](#c-sql) |
| A Python user | [D. Python](#d-python) |
| An R user | [E. R](#e-r) |
| Building a website or app | [F. JavaScript](#f-javascript) |
| A Stata / SPSS / Power BI user | [G. Stata, SPSS, Power BI, Tableau](#g-stata-spss-power-bi-tableau) |
| Planning to ask an AI about it | [H. Using this with AI](AI_GUIDE.md) |

**How the data is organised.** There are two segments, kept in separate tables:
**CB** (11 commercial banks, 2015–2025) and **SOCB** (6 state-owned and
specialised banks, back to 1972). Each has its own start-here table:
`v_cb_year` and `v_socb_year`. A third view, `v_all_year`, stacks them for when
you deliberately want both. Under everything sits a **raw layer** (`raw_cb`,
`raw_socb`) holding every source cell exactly as read.

Before any of them, three rules that apply to everyone:

1. **Use `value_pct_points` (or the `v_*_year` views) for percentages.**
   Different banks write ROE as `17.3` and `0.173`. `value_numeric` preserves
   whatever the sheet held; `value_pct_points` is the comparable column.
2. **Don't rank on ROE where equity is negative.** Krishi Bank (2010–2025) and a
   few single years elsewhere print a *positive* ROE for a *loss*. Use net profit
   and equity in Tk mn instead. They are logged as `roe_on_negative_equity`.
3. **Check `data_quality_log` for a bank before you publish its numbers.**
   Mutual Trust Bank's 2015 and 2017–2020 figures, in particular, are
   duplicates of Eastern Bank's and should be treated as unverified.

---

## A. No code

**What you need:** [DB Browser for SQLite](https://sqlitebrowser.org) — free,
runs on Windows, macOS and Linux. Install it like any other program.

1. Download `dyingcyrus.db` from the repository's
   [Releases](https://github.com/o-rnob/DyingCyrus-DB/releases) page (or from
   the repo root).
2. Open DB Browser → **Open Database** → choose `dyingcyrus.db`.
3. Click the **Browse Data** tab. The dropdown at the top lists every table and
   view. Start with **`v_cb_year`** (commercial banks) or
   **`v_socb_year`** (state-owned banks) — one row per bank per year with the
   main figures already in comparable units.
4. Use the filter boxes under each column heading to narrow things down. Typing
   `2025` under `year` gives you every bank's 2025 figures. To see how complete
   each bank is, open the **`bank_coverage`** table.
5. To export what you are looking at: **File → Export → Table(s) as CSV**.

**To run a ready-made question**, click the **Execute SQL** tab, paste anything
from [`examples/queries.sql`](../examples/queries.sql), and press the ▶ button
(or Ctrl+Return).

**Before you quote a number**, switch to Browse Data → `data_quality_log`,
filter `bank_id` to your bank, and read the `detail` column.

---

## B. Excel and Google Sheets

You do not need the database file at all — the repository ships CSVs.

**Excel**

1. Download the `data/csv/` folder from the repo (or the release zip).
2. Open `cb/cb_bank_year.csv` (commercial banks) or `socb/socb_bank_year.csv`
   (state-owned banks) — one row per bank-year, percentages already comparable.
   These are the ones you want 90% of the time.
3. Excel may read it as text. If so: **Data → From Text/CSV**, pick the file,
   set the encoding to **UTF-8**, and load.
4. Insert → PivotTable to slice by bank or year.

**Google Sheets**

File → Import → Upload → `cb_bank_year.csv` (or `socb_bank_year.csv`) → *Replace spreadsheet*.

**Which CSV is which**

In `data/csv/`:

| File | Contents |
|---|---|
| `cb/cb_bank_year.csv` · `socb/socb_bank_year.csv` | one row per bank-year, core metrics as columns — **start here** |
| `cb/cb_long.csv` · `socb/socb_long.csv` | every harmonised cell, tidy/long, with full provenance |
| `cb/per_bank/<bank_id>.csv` · `socb/per_bank/…` | one wide sheet per bank, metrics down, years across |
| `cb/raw/<bank_id>_raw_sheet.csv` · `socb/raw/…` | **the raw layer** — mirrors the original workbook tab cell-for-cell, nothing altered |
| `banks.csv` | the bank list |
| `bank_coverage.csv` | how complete each bank is |
| `metric_catalog.csv` | metric dictionary, per segment |
| `data_quality_log.csv` | every known problem |
| `source_notes.csv` | the compiler's sourcing notes |
| `bank_summary_stats.csv` | the summary block from each source sheet |

---

## C. SQL

Any SQLite client works: `sqlite3` on the command line, DB Browser, DBeaver,
DataGrip, TablePlus, Beekeeper Studio.

```bash
sqlite3 dyingcyrus.db
```

```sql
.headers on
.mode column
.tables

SELECT * FROM build_metadata;                    -- what build is this
SELECT bank_id, display_name, bank_type, year_min, year_max FROM banks;
SELECT * FROM v_cb_year WHERE year = 2025 ORDER BY total_assets_tk_mn DESC;
SELECT * FROM bank_coverage;                     -- how complete is each bank
```

Views keep you out of trouble:

* **`v_cb_year`** · **`v_socb_year`** — one row per bank-year, percentages in
  percentage points, one per segment.
* **`v_cb_financials`** · **`v_socb_financials`** — instance-1 rows with a value,
  joined to bank names.
* **`v_all_year`** — both segments stacked. Use only when you mean to.
* **`v_flagged`** — every bank-year carrying a critical flag, for anti-joins.

And the raw layer: `raw_cb` / `raw_socb` hold every source cell untouched —
see [SCHEMA.md](SCHEMA.md#raw_cb-and-raw_socb) for a query that traces any
harmonised number back to its raw cell.

The full cookbook is [`examples/queries.sql`](../examples/queries.sql). The
column-by-column reference is [SCHEMA.md](SCHEMA.md).

---

## D. Python

### The 30-second version

```python
import sqlite3, pandas as pd

conn = sqlite3.connect("dyingcyrus.db")
df = pd.read_sql("SELECT * FROM v_socb_year", conn)   # or v_cb_year
df.head()
```

### The nicer version

`dyingcyrus.py` sits in the repo root and needs nothing installed.

```python
from dyingcyrus import DyingCyrus

db = DyingCyrus("dyingcyrus.db")

db.banks()                                  # every bank
db.banks("SOCB")                            # one segment: "CB" or "SOCB"
db.series("city bank", "roe_pct")           # one metric over time
db.compare("total_assets", 2025, "CB")      # ranked league table, one segment
db.panel("CB", year_from=2015)              # tidy panel (None = both, stacked)
db.coverage()                               # how complete is each bank?
db.issues("mutual trust")                   # known problems
db.notes("krishi")                          # the compiler's notes
db.provenance("sonali", "total_assets", 2024)   # trace one harmonised cell
db.raw("sonali", row=6)                     # the untouched source cells of a row
db.sql("SELECT ...")                        # anything else
db.df("SELECT * FROM v_cb_year")            # as a DataFrame
```

Bank names are fuzzy-matched, so `"city bank"` finds `city_bank_plc`, and the
API reads the right segment's tables for you. `series(bank, "roe_pct")` adds a
`negative_equity` flag to each year — see rule 2 above.

### A real example — NPL trends, state-owned vs commercial

```python
import pandas as pd
from dyingcyrus import DyingCyrus

db = DyingCyrus("dyingcyrus.db")
panel = pd.DataFrame(db.panel(None, year_from=2015, year_to=2025))   # both segments, on purpose

trend = panel.groupby(["year", "segment"])["npl_pct"].mean().unstack()
trend.plot(title="Average gross NPL %, 2015–2025")
```

### Dropping the flagged bank-years first

```python
flagged = {(r["bank_id"], r["year"]) for r in db.sql("SELECT * FROM v_flagged")}
clean = panel[~panel.apply(lambda r: (r.bank_id, r.year) in flagged, axis=1)]
```

Run [`examples/quickstart.py`](../examples/quickstart.py) for a guided tour.

---

## E. R

```r
install.packages(c("RSQLite", "DBI", "dplyr"))

library(DBI); library(dplyr)

con <- dbConnect(RSQLite::SQLite(), "dyingcyrus.db")
dbListTables(con)

panel <- dbGetQuery(con, "SELECT * FROM v_all_year")   # both segments; use v_cb_year / v_socb_year for one

panel |>
  filter(!is.na(npl_pct), year >= 2015) |>
  group_by(year, segment) |>
  summarise(avg_npl = mean(npl_pct), .groups = "drop")

# known problems for one bank
dbGetQuery(con, "SELECT severity, issue, detail FROM data_quality_log
                 WHERE bank_id = 'mutual_trust_bank_plc'")

dbDisconnect(con)
```

Or skip SQLite entirely: `read.csv("data/csv/cb/cb_bank_year.csv")`.

---

## F. JavaScript

For a browser app, use the JSON exports — no database engine required.

```js
const banks = await fetch("data/json/banks.json").then(r => r.json());
const panel = await fetch("data/json/cb_bank_year.json").then(r => r.json());   // or socb_bank_year.json

const top2025 = panel
  .filter(r => r.year === 2025 && r.total_assets_tk_mn)
  .sort((a, b) => b.total_assets_tk_mn - a.total_assets_tk_mn);
```

Available: `banks.json`, `bank_coverage.json`, `cb_bank_year.json`,
`socb_bank_year.json`, `data_quality_log.json`, `source_notes.json`.

For the full database in the browser, load `dyingcyrus.db` with
[sql.js](https://github.com/sql-js/sql.js). In Node, use `better-sqlite3`:

```js
const db = require("better-sqlite3")("dyingcyrus.db", { readonly: true });
const rows = db.prepare("SELECT * FROM v_cb_year WHERE year = ?").all(2025);
```

---

## G. Stata, SPSS, Power BI, Tableau

All four read CSV directly. Point them at `data/csv/cb/cb_bank_year.csv` and/or
`data/csv/socb/socb_bank_year.csv`.

**Stata**

```stata
import delimited "data/csv/cb/cb_bank_year.csv", clear varnames(1)
encode bank_id, gen(bank)
xtset bank year
xtreg roe_pct npl_pct car_pct, fe
```

**Power BI / Tableau** — *Get Data → Text/CSV*. Load
the two `*_bank_year.csv` files as fact tables (append them if you want both
segments) and `banks.csv` as a dimension,
related on `bank_id`. Load `data_quality_log.csv` too and put a flag on your
dashboard; a chart that silently includes Mutual Trust Bank's duplicated years
is a chart that misleads.

---

## Rebuilding from source

The two source workbooks live in `data/raw/`. To rebuild everything:

```bash
pip install -r requirements.txt
python3 build_db.py
```

The script rewrites `dyingcyrus.db`, every CSV (including the raw-sheet
mirrors) and every JSON export from scratch, and prints the row and issue counts at the end. It is deterministic:
the same inputs give the same outputs, apart from the build timestamp.

To add a bank, drop its workbook into `data/raw/`, add an entry to `SOURCES` at
the top of `build_db.py` (`"bank_type": "CB"` or `"SOCB"`), and re-run. The parser locates the `Metric | Unit`
header row itself and reads the year columns from the header, so any sheet
laid out like the existing ones is picked up without further changes.
