<p align="center">
  <img src="logo.jpg" alt="DyingCyrus-DB" width="420">
</p>

<h1 align="center">DyingCyrus-DB</h1>

<p align="center">
  <b>Bangladesh Bank Financial Database — by Ow1nomics</b><br>
  17 banks · 1972–2026 · 7,846 data cells · every known problem logged and queryable
</p>

<p align="center">
  <a href="#quick-start">Quick start</a> ·
  <a href="docs/USER_MANUAL.md">User manual</a> ·
  <a href="docs/SCHEMA.md">Schema</a> ·
  <a href="docs/DATA_QUALITY.md">Data quality</a> ·
  <a href="docs/AI_GUIDE.md">Using it with AI</a>
</p>

---

A single SQLite file, `dyingcyrus.db`, consolidating annual balance sheet,
income statement, profitability, asset-quality and capital-adequacy data for
Bangladeshi banks:

* **11 DSE-listed private commercial banks** (`PCB`), fiscal years 2015–2025
* **6 state-owned and specialised banks** (`SOCB`) — Sonali, Janata, Rupali,
  BASIC, BDBL and Bangladesh Krishi Bank — with coverage running back to **1972**

Built with the same rule as [`KnightBase-DB`](https://github.com/o-rnob/Knightbase-DB)
and its CSV sibling [`o-rnob/Datanest`](https://github.com/o-rnob/Datanest):

> **Every skip, every conflict, every rename and every known data-quality issue
> is logged and queryable — nothing is silently fixed, rescaled or guessed at.**

If a number looks wrong, query `data_quality_log` and find out exactly why it is
there, or why it isn't.

---

## Quick stats

| | |
|---|---|
| Banks | 17 — 11 private (PCB), 6 state-owned (SOCB) |
| Year coverage | 1972–2026 (per-bank ranges vary; gaps documented) |
| Financial cells | 7,846 in `financials`, tidy/long format |
| Distinct metrics | 22 harmonised keys across 30+ raw labels |
| Cells with no figure | 2,497, stored as `NULL` — **never zero-filled** |
| Compiler source notes | 35, verbatim from the source sheets |
| Per-bank summary stats | 99 |
| Data-quality log entries | 243 — 200 critical, 10 warning, 33 info |

---

## Quick start

### I don't code

Download `dyingcyrus.db`, install the free
[DB Browser for SQLite](https://sqlitebrowser.org), open the file, click
**Browse Data**, and pick the **`v_bank_year`** table. That is one row per bank
per year with every headline figure already in comparable units.
→ [step-by-step](docs/USER_MANUAL.md#a-no-code)

### I use Excel

Open `data/csv/all_banks_bank_year.csv`. Nothing else required.
→ [step-by-step](docs/USER_MANUAL.md#b-excel-and-google-sheets)

### I use SQL

```sql
sqlite3 dyingcyrus.db

SELECT display_name, total_assets_tk_mn, roe_pct, npl_pct
FROM v_bank_year WHERE year = 2025
ORDER BY total_assets_tk_mn DESC;
```
→ [cookbook](examples/queries.sql)

### I use Python

```python
from dyingcyrus import DyingCyrus          # ships in the repo, no install needed

db = DyingCyrus("dyingcyrus.db")

db.series("city bank", "roe_pct")          # one metric over time
db.compare("total_assets", year=2025)      # ranked league table
db.panel(bank_type="SOCB")                 # tidy panel for analysis
db.issues("mutual trust")                  # known problems with this bank
db.provenance("sonali", "total_assets", 2024)   # trace a number to its cell
```

Or straight pandas:

```python
import sqlite3, pandas as pd
df = pd.read_sql("SELECT * FROM v_bank_year", sqlite3.connect("dyingcyrus.db"))
```

Run `python3 examples/quickstart.py` for a guided tour.
→ [step-by-step](docs/USER_MANUAL.md#d-python)

### I want to ask an AI about it

Upload `data/csv/all_banks_bank_year.csv` plus
`data/csv/data_quality_log.csv`, then paste the
[ready-made primer](docs/AI_GUIDE.md#3-the-primer--paste-this-first) as your
first message. It tells the model the two things it cannot guess: the
percentage-scale trap, and which figures are known to be unreliable.
→ [full AI guide](docs/AI_GUIDE.md)

R, JavaScript, Stata, Power BI and Tableau are covered in the
[user manual](docs/USER_MANUAL.md).

---

## The one thing you must know

**The source sheets do not agree on how to write a percentage.** Some banks
publish ROE as `17.3`. Others publish `0.173` for the same quantity, with the
unit column saying `%` in both cases. Comparing them raw is wrong by 100×.

This database does not silently pick a side:

* **`value_numeric`** holds the source figure, exactly as the cell had it.
* **`value_pct_points`** holds the same figure restated in percentage points.
* **`pct_scale`** records how that was decided — and the decision is
  evidence-based, not a magnitude guess. Where a ratio can be rebuilt from its
  own inputs on the same sheet (ROA from net profit ÷ assets, ROE from net
  profit ÷ equity, loan-deposit from loans ÷ deposits, NPL% from NPL amount ÷
  loans), both conventions are scored across at least three years and the better
  fit wins. The mean error under each is written into the log entry.

**Use `value_pct_points`, or just use `v_bank_year`, which applies the rule for
you.**

---

## Known issues — read before trusting a number

Full detail for all 243 entries is in `data_quality_log` and
[docs/DATA_QUALITY.md](docs/DATA_QUALITY.md).

**`cross_bank_identical_value` (90 entries, critical).** Eastern Bank PLC and
Mutual Trust Bank PLC report **byte-identical figures for 2015 and 2017–2020**
across nine metrics: total assets, gross loans, deposits, shareholders' equity,
net interest income, non-interest income, net profit after tax, EPS and NPL
amount. That is not plausible for raw Tk-mn balance-sheet numbers; it is almost
certainly a copy/paste error in the source workbook. MTB's 2021–2025 figures are
distinct and look fine. **Treat Mutual Trust Bank's 2015 and 2017–2020 figures
as unverified** until checked against MTB's annual reports.

**`percent_stored_as_fraction` (107 entries, critical).** Thirteen banks store
at least one `%` metric as a decimal fraction. Handled as described above — and
logged, never silently rescaled.

**`duplicate_table_on_sheet` + `misaligned_duplicate_row` (3 entries,
critical).** The Eastern Bank sheet contains its full data table twice (rows 14
and 48), and rows 74–75 are shifted one column left and appear divided by 100.
All copies are loaded; `table_instance = 1` is authoritative and is the only one
the views expose.

**`reported_ratio_not_reproducible` (1 entry, warning).** IFIC Bank's 2025 ROE
of −139.59% does not reproduce from its own net profit and closing equity, which
rebuild to −452.73% — the bank's equity collapsed during the year and the
reported figure appears to use average equity. That only one such case exists
across 17 banks is a fair sign the rest of the data is internally consistent.

**`value_outside_plausible_range` (9 entries, warning).** Ratios outside a
generous sanity band. Most are **real**, not errors: Bangladesh Krishi Bank's
capital adequacy ratio really does run to about −133%, and its cost-to-income
ratio really does exceed several hundred percent, because its net interest
income is deeply negative. The bank's own `source_notes` say so. Check them
before calling anything a mistake.

**Not an issue, but worth knowing:** 2,497 cells carry no figure. Most are years
before a bank's data begins — Sonali, Janata and Rupali have columns back to
1972 that are only partly populated, and Krishi Bank's 1973–2009 columns are
empty by design. They are `NULL`, not zero.

---

## Schema at a glance

```
banks ──┬── financials          every cell, tidy/long, with full provenance
        ├── bank_summary_stats  the summary block printed on each source sheet
        ├── source_notes        the compiler's sourcing notes, verbatim
        └── data_quality_log    every known problem, with severity and evidence
metric_catalog                  metric dictionary: 22 keys, 30+ raw labels
build_metadata                  build version, timestamp, row counts, licences
```

Three views do the thinking for you:

| View | Use it for |
|---|---|
| `v_financials` | authoritative rows only, joined to bank names |
| `v_bank_year` | one row per bank-year, percentages already comparable — **start here** |
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
│   │   ├── DATASET_11_BANKS_2025-2015_.xlsx
│   │   └── Dying_Cyrus_-_SOCB_V7__furnished_.xlsx
│   ├── csv/
│   │   ├── all_banks_bank_year.csv    one row per bank-year — start here
│   │   ├── all_banks_long.csv         every cell, with provenance
│   │   ├── banks.csv
│   │   ├── metric_catalog.csv
│   │   ├── bank_summary_stats.csv
│   │   ├── source_notes.csv
│   │   ├── data_quality_log.csv
│   │   └── per_bank/                  one wide CSV per bank
│   └── json/                          banks, bank_year, quality log, notes
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
`data/raw/`, then prints the row and issue counts. It is deterministic apart
from the build timestamp.

To add a bank: drop its workbook into `data/raw/`, add an entry to `SOURCES` at
the top of `build_db.py`, re-run. The parser finds the `Metric | Unit` header
row itself and reads the years from the header, so any sheet laid out like the
existing ones needs no further code.

---

## Sources and attribution

Figures are compiled from the published annual reports and audited financial
statements of each bank. The state-owned-bank sheets carry detailed per-bank
sourcing notes — which annual report each year came from, where a later report
restated an earlier one, and which version was used. Those notes are in the
`source_notes` table and in `data/csv/source_notes.csv`; read them before
building anything on the SOCB figures.

Always cross-check against a bank's official disclosures before using this data
for investment or research decisions — especially given the Mutual Trust
Bank / Eastern Bank overlap noted above.

The **code and schema** in this repository are MIT licensed (see `LICENSE`).
The **underlying data** follows the same terms as the source
[`o-rnob/Datanest`](https://github.com/o-rnob/Datanest) repository: CC0 1.0
Universal.

## Citation

See `CITATION.cff`, or cite the build timestamp from `build_metadata` alongside
the release tag.

## Disclaimer

Provided for informational and research purposes only. Not financial advice. No
guarantee is made as to completeness or accuracy — that is the entire point of
`data_quality_log`.
