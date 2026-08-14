[![DyingCyrus-DB logo](logo.jpg)](logo.jpg)

# DyingCyrus-DB

**Bangladesh Bank Financial Database — SQLite Edition — by Ow1nomics**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Banks](https://img.shields.io/badge/Banks-11-blue)](#banks-covered)
[![Years](https://img.shields.io/badge/Coverage-2015--2025-blue)](#schema)
[![Format](https://img.shields.io/badge/Format-SQLite%20%7C%20CSV-green)](#repository-structure)
[![Data Quality Log](https://img.shields.io/badge/Data%20Quality%20Log-95%20entries-orange)](#known-gaps-read-this-before-trusting-a-number)
[![Open Source](https://img.shields.io/badge/Open%20Source-Yes-brightgreen)](#license)

> **Open-source SQLite database** of annual balance sheet, income statement, profitability,
> asset-quality, and capital-adequacy data for **11 publicly listed commercial banks in
> Bangladesh**, covering fiscal years **2015–2025**. Built for **finance research, banking-sector
> analysis, SQL/pandas workflows, Power BI/Tableau dashboards, and academic teaching material**
> on the **Dhaka Stock Exchange (DSE)** banking sector — with every data-quality issue found
> during the build logged and queryable, not silently patched.

**Maintainer:** K. M. Miad Hasan Ornob (Ow1nomics)

---

## Table of Contents

- [What this is](#what-this-is)
- [Quick stats](#quick-stats)
- [Banks covered](#banks-covered)
- [Quick start (Python)](#quick-start-python)
- [Schema](#schema)
- [Known gaps (read this before trusting a number)](#known-gaps-read-this-before-trusting-a-number)
- [Repository structure](#repository-structure)
- [Sources & attribution](#sources--attribution)
- [Citation](#citation)
- [A note on the name](#a-note-on-the-name)

---

## What this is

`dyingcyrus.db` is a single SQLite file consolidating the annual financial statements of 11
Dhaka Stock Exchange-listed commercial banks into one queryable schema, built from the source
workbook `data/raw/DATASET_11_BANKS_2025-2015_.xlsx`. It is the SQLite/Python-build companion
to the CSV-based [`o-rnob/Datanest`](https://github.com/o-rnob/Datanest) repo, built with the
same rule as [`KnightBase-DB`](https://github.com/o-rnob/Knightbase-DB):

> **Every skip, every conflict, every rename, and every known data-quality issue is logged
> and queryable — nothing is silently fixed, rescaled, or guessed at.**

If a number looks wrong, query `data_quality_log` and find out exactly why it's there, or why
it isn't.

---

## Quick stats

|                            |                                                          |
| -------------------------- | -------------------------------------------------------- |
| Banks                       | 11 (DSE-listed commercial banks, Bangladesh)              |
| Financial line-item rows    | 2,541 (`financials` table, tidy/long format)              |
| Distinct metrics tracked    | 28 (balance sheet, income statement, profitability, asset quality, capital & efficiency, derived) |
| Year coverage                | 2015–2025 (per-bank gaps documented, see [Known gaps](#known-gaps-read-this-before-trusting-a-number)) |
| Missing cells                | 156 (stored as `NULL`, never silently zero-filled)        |
| Data quality log entries    | 95 (84 critical · 6 warning · 5 info)                      |
| Pre-computed summary stats  | 9 per bank (mean/rolling ROE, Sharpe-like ratio, CAGR, drawdown, Newey-West HAC trend) |

---

## Banks covered

| #  | Bank                        |
| --- | --------------------------- |
| 1  | City Bank PLC                |
| 2  | IFIC Bank PLC                |
| 3  | Bank Asia PLC                |
| 4  | BRAC Bank PLC                |
| 5  | Dutch-Bangla Bank PLC        |
| 6  | Eastern Bank PLC             |
| 7  | Mutual Trust Bank PLC (MTB)  |
| 8  | Prime Bank PLC                |
| 9  | Mercantile Bank PLC           |
| 10 | Southeast Bank PLC            |
| 11 | Pubali Bank PLC                |

**Keywords:** Bangladesh banking sector data, DSE-listed banks financial statements, Bangladesh
bank ROE ROA dataset, NPL ratio Bangladesh banks, Bangladesh bank annual report SQLite,
commercial bank financial database 2015–2025, banking data quality log.

---

## Quick start (Python)

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("dyingcyrus.db")

# ROE trend for one bank (table_instance=1 = the primary/authoritative copy of the sheet)
roe = pd.read_sql("""
    SELECT year, value_numeric FROM financials
    WHERE bank_id = 'city_bank' AND metric = 'ROE %' AND table_instance = 1
    ORDER BY year
""", conn)

# Compare Total Assets across all banks for 2025
assets_2025 = pd.read_sql("""
    SELECT b.display_name, f.value_numeric FROM financials f
    JOIN banks b ON b.bank_id = f.bank_id
    WHERE f.metric = 'Total Assets' AND f.year = 2025 AND f.table_instance = 1
    ORDER BY f.value_numeric DESC
""", conn)

# See every known issue for a bank before trusting its numbers
issues = pd.read_sql("SELECT * FROM data_quality_log WHERE bank_id = 'mutual_trust_bank'", conn)
```

CSV exports (long format, per-bank wide format, summary stats, and the quality log itself) are
also written to `data/csv/` — see [Repository structure](#repository-structure).

---

## Schema

### `banks`

| column       | type | notes                                    |
| ------------ | ---- | ----------------------------------------- |
| bank_id      | TEXT | slug primary key, e.g. `city_bank`        |
| sheet_name   | TEXT | exact source worksheet name                |
| display_name | TEXT | full legal/display name, e.g. `City Bank PLC` |

### `financials`

The unified tidy/long table. One row per (bank, table_instance, metric, year) — nothing is
merged or overwritten across duplicate tables on a sheet.

| column         | type    | notes                                                                                   |
| -------------- | ------- | ----------------------------------------------------------------------------------------- |
| bank_id        | TEXT    | FK → `banks`                                                                               |
| table_instance | INTEGER | 1 = primary table on the sheet. >1 = a duplicate table found further down the same sheet (only Eastern Bank Ltd has this — see Known Gaps) |
| category       | TEXT    | section header from the sheet, e.g. `BALANCE SHEET`, `ASSET QUALITY`, `DERIVED METRICS`   |
| metric         | TEXT    | raw metric label, e.g. `Total Assets`, `ROE %`, `NPL % (gross)`                           |
| unit           | TEXT    | raw unit label from the sheet's Unit column, e.g. `Tk mn`, `%`, `BDT`                      |
| year           | INTEGER | 2015–2025                                                                                   |
| raw_value      | TEXT    | the **exact original cell content**, stringified — always preserved                        |
| value_numeric  | REAL    | parsed numeric value, or `NULL` if the cell was blank/unparseable                           |
| value_source   | TEXT    | `native_numeric` / `recovered_from_text` (e.g. `'165,370†'` cleaned) / `missing`           |
| source_row     | INTEGER | 1-indexed row in the original Excel sheet, for traceability                                 |
| source_col     | TEXT    | Excel column letter                                                                          |

**`value_numeric` is a best-effort recovery, never a correction.** `raw_value` always keeps
what was actually in the cell (including footnote markers, `N/A`, `n/a*`, `N/M`, and stray
unicode minus signs) so you can decide for yourself whether to trust a recovered figure.

### `bank_summary_stats`

The per-bank "Summary" block at the top of each sheet — Mean ROE %, Std Dev ROE %, Sharpe-like
ratio (rf=3%), rolling-window ROE mean/std/Sharpe (2019–2024), Equity CAGR %, max NPAT
drawdown, and the Newey-West (HAC) NPL%-vs-year trend slope. Long format:
`bank_id, stat_name, value, source_row`.

### `data_quality_log`

| column   | type    | notes                                   |
| -------- | ------- | ----------------------------------------- |
| bank_id  | TEXT    | nullable — some issues are dataset-wide   |
| metric   | TEXT    | nullable                                   |
| year     | INTEGER | nullable                                   |
| issue    | TEXT    | short machine-readable tag (see below)     |
| detail   | TEXT    | full human-readable explanation            |
| severity | TEXT    | `info` / `warning` / `critical`            |

---

## Known gaps (read this before trusting a number)

Full detail for all 95 entries is in `data_quality_log` / `data/csv/data_quality_log.csv`.
Five issue types were found by the build script:

**`cross_bank_identical_value` (70 entries, critical) — Mutual Trust Bank vs. Eastern Bank Ltd.**
For 2015, 2017, 2018, 2019, and 2020, Mutual Trust Bank's `Total Assets`, `Loans & Advances`,
`Total Deposits`, `Net Interest Income`, `Non-Interest Income`, `EPS`, `Loan-Deposit Ratio %`,
`NPL % (gross)`, `Provision Coverage %`, `CRAR %`, and `Cost-to-Income Ratio %` figures are
**byte-identical** to Eastern Bank Ltd's figures for the same years. This is not a plausible
coincidence for raw Tk-mn balance sheet numbers — it is almost certainly a copy/paste error in
the source workbook (Mutual Trust Bank's own 2021–2025 figures, and its Shareholders' Equity
and Net Profit After Tax series, are NOT affected and look distinct/plausible). **Treat Mutual
Trust Bank's 2015, 2017–2020 balance-sheet and income-statement figures as unverified** until
checked against MTB's actual annual reports.

**`percent_stored_as_fraction` (13 entries, critical).** ROA %/ROE % for Bank Asia, Dutch-Bangla
Bank, IFIC Bank, Mercantile Bank, Mutual Trust Bank, Prime Bank, Pubali Bank, and Southeast Bank
are stored as decimal fractions (e.g. `0.173`) even though the sheet's Unit column says `%`,
while City Bank, BRAC Bank, and Eastern Bank report the same metrics in percentage-point form
(e.g. `17.3`). **Do not compare ROA/ROE across banks without first checking `value_numeric`'s
scale** — this database does not silently rescale either convention, it only logs which banks
use which.

**`duplicate_table_on_sheet` (1 entry, critical) — Eastern Bank Ltd.** The sheet contains the
full Metric/Unit data table twice (rows 15–40 and again at 48–75), and a third partial/rescaled
duplicate at rows 74–75 (the same YoY growth metrics, but divided by 100, with a footnote marker
`N/A⁴`). All instances are loaded (`table_instance` 1 and 2); `table_instance = 1` is the
authoritative copy used by default in the quick-start queries above.

**`text_cell_with_recoverable_number` (5 entries, info).** Cells like `'165,370†'` (Mutual Trust
Bank Total Assets 2016) or `'80.31%*'` (Bank Asia CRAR 2015) held a footnote-marked number.
`value_numeric` recovers the number; `raw_value` keeps the footnote so you know the figure was
flagged as unusual by whoever compiled the source workbook.

**`unrecoverable_text_cell` (6 entries, warning).** Text like `'n/a*'`, `'N/M'` that couldn't be
parsed as a number at all — stored as `NULL` in `value_numeric`, original text kept in
`raw_value`.

**Not logged as an issue, but worth knowing:** 156 cells across the dataset are genuinely blank
(`N/A` in the source) — mostly Eastern Bank Ltd 2016 (an entire year missing for most metrics)
and scattered early-year gaps for Bank Asia, Dutch-Bangla Bank, and Pubali Bank. These are
`NULL` in `value_numeric`, not zero.

---

## Repository structure

```
DyingCyrus-DB/
├── logo.jpg                              # repo cover image
├── build_db.py                           # the ETL script — run this to rebuild dyingcyrus.db from scratch
├── dyingcyrus.db                         # the SQLite database (output of build_db.py)
├── requirements.txt
├── data/
│   ├── raw/
│   │   └── DATASET_11_BANKS_2025-2015_.xlsx   # original workbook, untouched
│   └── csv/
│       ├── all_banks_long.csv           # tidy/long export of `financials`
│       ├── all_banks_summary_stats.csv  # export of `bank_summary_stats`
│       ├── data_quality_log.csv         # export of `data_quality_log`
│       └── per_bank/                    # one wide-format CSV per bank (table_instance=1 only)
├── CITATION.cff
├── LICENSE
└── README.md
```

Rebuild anytime with:

```bash
pip install -r requirements.txt
python3 build_db.py
```

---

## Sources & attribution

| Source                                                    | What it provided                                                                          | License / terms                              |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `DATASET_11_BANKS_2025-2015_.xlsx` (own compiled work)         | Annual balance sheet, income statement, and ratio data for 11 DSE-listed banks, 2015–2025      | Compiled from published bank annual reports      |
| [`o-rnob/Datanest`](https://github.com/o-rnob/Datanest)          | Original CSV release of this dataset                                                          | CC0 1.0 Universal                                |

Figures are compiled from published annual reports and financial statements of each bank.
Always cross-check against a bank's official disclosures before using this data for investment
or research decisions — especially given the Mutual Trust Bank / Eastern Bank overlap noted
above.

This repository's **code and schema** are MIT licensed (see `LICENSE`). The underlying **data**
follows the same terms as the source `o-rnob/Datanest` repository (CC0 1.0 Universal) — verify
before redistributing the data itself at scale.

## Citation

See `CITATION.cff`. In short:

```
Ornob, K. M. Miad Hasan (Ow1nomics). (2026). DyingCyrus-DB: A SQLite Financial Database
for 11 DSE-Listed Bangladeshi Banks (2015-2025).
https://github.com/o-rnob/DyingCyrus-DB
```

## A note on the name

DyingCyrus-DB is the SQLite-native counterpart to [`o-rnob/Datanest`](https://github.com/o-rnob/Datanest),
built to the same auditability standard as [`KnightBase-DB`](https://github.com/o-rnob/Knightbase-DB):
raw values are never silently altered, and every anomaly the build script finds — duplicate
tables, cross-bank copy/paste artifacts, inconsistent percentage scaling — is written to
`data_quality_log` instead of being quietly cleaned away.

## Disclaimer

Provided for informational and research purposes only. Not financial advice. No guarantee is
made as to completeness or accuracy — that's the entire point of `data_quality_log`.
