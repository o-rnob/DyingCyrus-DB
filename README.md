<p align="center">
  <img src="logo.jpg" alt="DyingCyrus-DB" width="420">
</p>

<h1 align="center">DyingCyrus-DB</h1>

<p align="center">
  <b>Bangladeshi State Owned Commercial Bank & 11 Commercial Bank Financial Database — by Ow1nomics</b><br>
  17 banks · 1972–2026 · two segments kept apart · a raw layer under everything · every known problem logged
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/USER_MANUAL.md">User manual</a> ·
  <a href="docs/SCHEMA.md">Schema</a> ·
  <a href="docs/DATA_QUALITY.md">Data quality</a> ·
  <a href="docs/AI_GUIDE.md">Using it with AI</a>
</p>

---

A single SQLite file, `dyingcyrus.db`, holding annual balance-sheet,
income-statement, profitability, asset-quality and capital-adequacy data for
Bangladeshi banks, in **two segments that are never mixed unless you ask**:

| Segment | Code | Banks | Years | Tables |
|---|---|---|---|---|
| **Commercial banks** — private, DSE-listed | `CB` | 11 | 2015–2025 | `financials_cb` · `raw_cb` · `v_cb_year` |
| **State-owned & specialised banks** | `SOCB` | 6 (Sonali, Janata, Rupali, BASIC, BDBL, Krishi) | **1972**–2026 | `financials_socb` · `raw_socb` · `v_socb_year` |

Two layers, both in the database and both exported:

* **Harmonised layer** (`financials_*`, `v_*_year`) — 22 metric keys behind 30+
  raw labels, percentages restated so they are comparable, every cell traceable.
* **Raw layer** (`raw_*`, `data/csv/*/raw/`) — every non-empty cell of every
  source sheet, **exactly as read**. No metric mapping, no unit correction, no
  percent detection. The harmonised layer is built on top of it, so nothing is
  lossy: if you disagree with a harmonisation choice, go to the raw layer.

The house rule, inherited from [`KnightBase-DB`](https://github.com/o-rnob/Knightbase-DB)
and its CSV sibling [`o-rnob/Datanest`](https://github.com/o-rnob/Datanest):

> **Every skip, conflict, rename and known data-quality issue is logged and
> queryable — nothing is silently fixed, rescaled or guessed at.**

---

## How complete is it?

The headline is **coverage of the five core series** — total assets, gross loans,
deposits, shareholders' equity and net profit after tax — measured inside each
bank's compiled range (first to last year with any core figure).

### State-owned & specialised banks (`SOCB`)

| Bank | Compiled range | Years | Core-5 complete | Years with all five |
|---|---|---|---|---|
| Janata Bank PLC | 1972–2024 | 53 | **100.0%** | 53 |
| BASIC Bank PLC | 1989–2023 | 35 | **100.0%** | 35 |
| Bangladesh Krishi Bank (BKB) | 2010–2025 | 16 | **100.0%** | 16 |
| Bangladesh Development Bank PLC (BDBL) | 2010–2024 | 15 | **100.0%** | 15 |
| Sonali Bank | 1972–2025 | 54 | **99.3%** | 52 |
| Rupali Bank PLC | 1972–2025 | 54 | **50.7%** | 17 |

Five of the six are **effectively complete** for their whole span — Sonali,
Janata and Rupali reach back to **1972**, giving 50+ years of fundamentals.
**Rupali is the honest exception** (about half), and its own `source_notes`
say why: 1972–1996 carry only deposits, loans and pre-tax profit; 1997–2007 are
missing from the supplied annual reports; and net profit after tax exists only
from 2009. Its full core-five series runs 2009–2025. Krishi Bank's sheet has year columns back to 1973, but its data starts
in **2010**; the earlier columns are empty by design.

### Commercial banks (`CB`)

| Bank | Compiled range | Years | Core-5 complete | Years with all five |
|---|---|---|---|---|
| BRAC Bank PLC | 2015–2025 | 11 | **100.0%** | 11 |
| City Bank PLC | 2015–2025 | 11 | **100.0%** | 11 |
| Dutch-Bangla Bank PLC | 2015–2025 | 11 | **100.0%** | 11 |
| IFIC Bank PLC | 2015–2025 | 11 | **100.0%** | 11 |
| Mercantile Bank PLC | 2015–2025 | 11 | **100.0%** | 11 |
| Prime Bank PLC | 2015–2025 | 11 | **100.0%** | 11 |
| Southeast Bank PLC | 2015–2025 | 11 | **100.0%** | 11 |
| Pubali Bank PLC | 2016–2025 | 10 | **100.0%** | 10 |
| Mutual Trust Bank PLC | 2015–2025 | 11 | **98.2%** | 10 |
| Bank Asia PLC | 2015–2025 | 11 | **96.4%** | 10 |
| Eastern Bank PLC | 2015–2025 | 11 | **90.9%** | 10 |

The `bank_coverage` table has these figures plus a second measure
(`core5_pct_sheet`) that counts every year column on the sheet, including empty
ones before a bank's data begins.

> **About the 2,497 empty cells.** Of 7,846 harmonised cells, 2,497 carry
> no figure. Most are year columns *before* a bank's data begins, or metrics a
> sheet simply does not report. They are `NULL`, never zero. That number
> describes the size of the grid, not the quality of the data — use the coverage
> tables above.

---

## Quick start

### I don't code

Download `dyingcyrus.db`, install the free
[DB Browser for SQLite](https://sqlitebrowser.org), open the file, click
**Browse Data**, and pick **`v_cb_year`** (commercial banks) or **`v_socb_year`**
(state-owned banks). One row per bank per year, every headline figure in
comparable units.
→ [step-by-step](docs/USER_MANUAL.md#a-no-code)

### I use Excel or Google Sheets

Open `data/csv/cb/cb_bank_year.csv` or `data/csv/socb/socb_bank_year.csv`.
Nothing else required.
→ [step-by-step](docs/USER_MANUAL.md#b-excel-and-google-sheets)

### I use SQL

```sql
sqlite3 dyingcyrus.db

SELECT display_name, total_assets_tk_mn, roe_pct, npl_pct
FROM v_cb_year WHERE year = 2025
ORDER BY total_assets_tk_mn DESC;
```
→ [cookbook](examples/queries.sql)

### I use Python

```python
from dyingcyrus import DyingCyrus          # ships in the repo, no install needed

db = DyingCyrus("dyingcyrus.db")

db.series("city bank", "roe_pct")          # one metric over time
db.compare("total_assets", 2025, "CB")     # ranked league table, one segment
db.panel("SOCB")                           # tidy panel for analysis
db.coverage()                              # how complete is each bank?
db.issues("mutual trust")                  # known problems with this bank
db.raw("sonali", row=6)                    # the untouched source cells
db.provenance("sonali", "total_assets", 2024)   # trace a number to its cell
```

The API resolves a bank name to its segment and reads the right tables for you.
Or straight pandas:

```python
import sqlite3, pandas as pd
df = pd.read_sql("SELECT * FROM v_socb_year", sqlite3.connect("dyingcyrus.db"))
```

Run `python3 examples/quickstart.py` for a guided tour.
→ [step-by-step](docs/USER_MANUAL.md#d-python)

### I want to ask an AI about it

Upload `data/csv/cb/cb_bank_year.csv`, `data/csv/socb/socb_bank_year.csv` and
`data/csv/data_quality_log.csv`, then paste the
[ready-made primer](docs/AI_GUIDE.md#3-the-primer--paste-this-first) as your
first message. It tells the model what it cannot guess: the percentage-scale
trap, the negative-equity ROE trap, and which figures are known to be unreliable.
→ [full AI guide](docs/AI_GUIDE.md)

R, JavaScript, Stata, Power BI and Tableau are covered in the
[user manual](docs/USER_MANUAL.md).

---

## Two traps you must know about

### 1. The source sheets do not agree on how to write a percentage

Some banks publish ROE as `17.3`. Others publish `0.173` for the same quantity,
with the unit column saying `%` in both cases. Compared raw, they are wrong by 100×.

* **`value_numeric`** holds the source figure exactly as the cell had it.
* **`value_pct_points`** holds the same figure restated in percentage points.
* **`pct_scale`** records how that was decided — evidence, not a magnitude guess.
  Where a ratio can be rebuilt from its own inputs on the same sheet (ROA from
  profit ÷ assets, ROE from profit ÷ equity, loan-deposit from loans ÷ deposits,
  NPL% from NPL ÷ loans), both conventions are scored over at least three years
  and the better fit wins. Ratios that cannot be rebuilt inherit the convention
  the rest of that bank's sheet demonstrably uses, tagged `_inferred`.

**Use `value_pct_points`, or just use the `v_*_year` views, which apply the rule.**

### 2. ROE on negative equity is meaningless

ROE = profit ÷ equity. When equity is **negative**, a *loss* divided by negative
equity prints as a **positive** ROE. Bangladesh Krishi Bank has reported negative
equity every year since 2010 (about −Tk 275 bn by 2025) and a net loss in every
year since 2011 — yet its printed ROE is a positive 5% to 65% while the bank is
deeply insolvent. Sonali, Janata, Rupali (one year each) and BASIC (2021–2023) have the
same effect in a few years. These are logged as `roe_on_negative_equity`
(critical); `db.series(..., "roe_pct")` adds a `negative_equity` flag to each
year. **Never rank, average or chart these ROE values as if higher were better.**
Use net profit and equity in Tk mn.

---

## Known issues — read before trusting a number

Full detail for all 248 log entries is in `data_quality_log` and
[docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).

**`cross_bank_identical_value` (90, critical).** Eastern Bank PLC and Mutual
Trust Bank PLC report **byte-identical figures for 2015 and 2017–2020** across
nine metrics: total assets, gross loans, deposits, equity, net interest income,
non-interest income, NPAT, EPS and NPL amount. Not plausible for raw Tk-mn
balance-sheet numbers; almost certainly a copy/paste error in the source
workbook. MTB's 2021–2025 figures are distinct and look fine. **Treat Mutual
Trust Bank's 2015 and 2017–2020 figures as unverified** until checked against its
annual reports.

**`percent_stored_as_fraction` (107, critical).** Thirteen banks store at least
one `%` metric as a decimal fraction. Handled as above — logged, never silently
rescaled.

**`roe_on_negative_equity` (5, critical).** See trap 2.

**`duplicate_table_on_sheet` + `misaligned_duplicate_row` (3, critical).** The
Eastern Bank sheet contains its whole data table twice (rows 14 and 48), and
rows 74–75 are shifted one column left and appear divided by 100. All copies are
loaded; `table_instance = 1` is authoritative and is the only one the views use.

**`reported_ratio_not_reproducible` (1, warning).** IFIC Bank's 2025 ROE of
−139.59% does not reproduce from its own net profit and closing equity, which
rebuild to −452.73% — equity collapsed during the year and the reported figure
appears to use average equity. That only one such case exists across 17 banks is
a fair sign the rest is internally consistent.

**`value_outside_plausible_range` (9, warning).** Ratios outside a generous
sanity band. Most are **real**: Krishi Bank's capital adequacy ratio really does
run to about −133% and its cost-to-income ratio really does exceed several
hundred percent, because its net interest income is deeply negative. The bank's
own `source_notes` say so. Check them before calling anything a mistake.

---

## Schema at a glance

```
banks ──┬── financials_cb / financials_socb   harmonised cells, tidy/long, with provenance
        ├── raw_cb / raw_socb                 every source cell, exactly as read
        ├── bank_coverage                     completeness of the core series, per bank
        ├── bank_summary_stats                the summary block printed on each sheet
        ├── source_notes                      the compiler's sourcing notes, verbatim
        └── data_quality_log                  every known problem, with severity + evidence
metric_catalog                                metric dictionary, per segment
build_metadata                                version, timestamp, row counts, licences
```

Views do the thinking for you:

| View | Use it for |
|---|---|
| `v_cb_year` · `v_socb_year` | one row per bank-year, percentages already comparable — **start here** |
| `v_cb_financials` · `v_socb_financials` | authoritative rows only, joined to bank names |
| `v_all_year` | **both segments stacked** — only when you deliberately want that |
| `v_flagged` | anti-join to drop every bank-year carrying a critical flag |

Column-by-column reference: [docs/SCHEMA.md](docs/SCHEMA.md).

---

## Repository structure

```
DyingCyrus-DB/
├── dyingcyrus.db                  the database (also on the Releases page)
├── dyingcyrus.py                  zero-dependency Python API
├── build_db.py                    the ETL — rebuilds everything from data/raw/
├── requirements.txt
├── logo.jpg
├── data/
│   ├── raw/                       the two source workbooks, untouched
│   ├── csv/
│   │   ├── banks.csv  bank_coverage.csv  bank_summary_stats.csv
│   │   ├── source_notes.csv  metric_catalog.csv  data_quality_log.csv
│   │   ├── cb/                    commercial banks
│   │   │   ├── cb_bank_year.csv       one row per bank-year — start here
│   │   │   ├── cb_long.csv            every harmonised cell, with provenance
│   │   │   ├── per_bank/              one wide CSV per bank
│   │   │   └── raw/                   one CSV per bank mirroring the sheet cell-for-cell
│   │   └── socb/                  state-owned & specialised banks (same layout)
│   └── json/                      banks, coverage, cb/socb bank_year, quality log, notes
├── docs/
│   ├── USER_MANUAL.md             step-by-step for every kind of user
│   ├── SCHEMA.md                  full column reference
│   ├── DATA_QUALITY.md            every issue tag explained
│   ├── AI_GUIDE.md                prompts, primer, and what AI gets wrong
│   └── CHANGELOG.md
├── examples/
│   ├── quickstart.py              runnable tour, standard library only
│   └── queries.sql                copy-paste SQL cookbook
├── CITATION.cff
└── LICENSE
```

---

## Rebuilding from source

```bash
pip install -r requirements.txt
python3 build_db.py
```

This rewrites the database and every CSV and JSON export from the workbooks in
`data/raw/`, then prints row and issue counts. It is deterministic apart from the
build timestamp.

To add a bank: drop its workbook into `data/raw/`, add an entry to `SOURCES` at
the top of `build_db.py` with `"bank_type": "CB"` or `"SOCB"`, re-run. The parser
finds the `Metric | Unit` header row itself and reads the years from the header,
so any sheet laid out like the existing ones needs no further code.

---

## Sources and attribution

Figures are compiled from the published annual reports and audited financial
statements of each bank. The state-owned-bank sheets carry detailed per-bank
sourcing notes — which annual report each year came from, where a later report
restated an earlier one, and which version was used. Those notes are in the
`source_notes` table and `data/csv/source_notes.csv`; **read them before building
anything on the SOCB figures**.

Always cross-check against a bank's official disclosures before using this data
for investment or research decisions — especially the Mutual Trust / Eastern
overlap noted above.

The **code and schema** in this repository are MIT licensed (see `LICENSE`).
The **underlying data** follows the same terms as the source
[`o-rnob/Datanest`](https://github.com/o-rnob/Datanest) repository: CC0 1.0 Universal.

## Citation

See `CITATION.cff`, or cite the build timestamp from `build_metadata` alongside
the release tag.

## Disclaimer

Provided for informational and research purposes only. Not financial advice. No
guarantee is made as to completeness or accuracy — that is the entire point of
`data_quality_log`.
