[![DyingCyrus-DB logo](logo.jpg)](logo.jpg)

# DyingCyrus-DB

**Bangladesh Bank Financial Database — by Ow1nomics**

A single SQLite file (`dyingcyrus.db`) consolidating annual balance sheet, income statement,
profitability, asset-quality, and capital-adequacy data for **11 DSE-listed commercial banks
in Bangladesh**, fiscal years **2015–2025**, built from the source workbook
`data/raw/DATASET_11_BANKS_2025-2015_.xlsx`.

This is the SQLite/Python-build companion to the CSV-based
[`o-rnob/Datanest`](https://github.com/o-rnob/Datanest) repo, built with the same rule as
[`KnightBase-DB`](https://github.com/o-rnob/Knightbase-DB):

> **Every skip, every conflict, every rename, and every known data-quality issue is logged
> and queryable — nothing is silently fixed, rescaled, or guessed at.**

If a number looks wrong, query `data_quality_log` and find out exactly why it's there, or why
it isn't.

---

## Quick stats

|                          |                                                          |
| ------------------------ | -------------------------------------------------------- |
| Banks                    | 11                                                        |
| Financial line-item rows | 2,541 (`financials` table, tidy/long format)              |
| Distinct metrics         | 28                                                        |
| Year coverage            | 2015–2025 (per-bank gaps documented, see below)           |
| Missing cells            | 156 (stored as `NULL`, never silently zero-filled)        |
| Data quality log entries | 95 (84 critical, 6 warning, 5 info)                       |

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

| column       | type | notes                                  |
| ------------ | ---- | --------------------------------------- |
| bank_id      | TEXT | slug primary key, e.g. `city_bank`      |
| sheet_name   | TEXT | exact source worksheet name             |
| display_name | TEXT | full legal/display name, e.g. `City Bank PLC` |

### `financials`

The unified tidy/long table. One row per (bank, table_instance, metric, year).

| column         | type    | notes                                                                                   |
| -------------- | ------- | ----------------------------------------------------------------------------------------- |
| bank_id        | TEXT    | FK → `banks`                                                                               |
| table_instance | INTEGER | 1 = primary table on the sheet. >1 = a duplicate table found further down the same sheet (only Eastern Bank Ltd has this — see Known Issues) |
| category       | TEXT    | section header from the sheet, e.g. `BALANCE SHEET`, `ASSET QUALITY`, `DERIVED METRICS`   |
| metric         | TEXT    | raw metric label, e.g. `Total Assets`, `ROE %`, `NPL % (gross)`                           |
| unit           | TEXT    | raw unit label from the sheet's Unit column, e.g. `Tk mn`, `%`, `BDT`                      |
| year           | INTEGER | 2015–2025                                                                                   |
| raw_value      | TEXT    | the **exact original cell content**, stringified — always preserved                        |
| value_numeric  | REAL    | parsed numeric value, or `NULL` if the cell was blank/unparseable                           |
| value_source   | TEXT    | `native_numeric` (cell was already a number) / `recovered_from_text` (text cell like `'165,370†'` was cleaned) / `missing` |
| source_row     | INTEGER | 1-indexed row in the original Excel sheet, for traceability                                 |
| source_col     | TEXT    | Excel column letter                                                                          |

**`value_numeric` is a best-effort recovery, never a correction.** `raw_value` always keeps
what was actually in the cell (including footnote markers, `N/A`, `n/a*`, `N/M`, and stray
unicode minus signs) so you can decide for yourself whether to trust a recovered figure.

### `bank_summary_stats`

The per-bank "Summary" block at the top of each sheet (Mean ROE, Sharpe-like ratio, CAGR,
max drawdown, Newey-West HAC trend slope, etc.), long format: `bank_id, stat_name, value,
source_row`.

### `data_quality_log`

| column   | type | notes                                                                 |
| -------- | ---- | ----------------------------------------------------------------------- |
| bank_id  | TEXT | nullable — some issues are dataset-wide                                 |
| metric   | TEXT | nullable                                                                 |
| year     | INTEGER | nullable                                                              |
| issue    | TEXT | short machine-readable tag (see below)                                  |
| detail   | TEXT | full human-readable explanation                                         |
| severity | TEXT | `info` / `warning` / `critical`                                         |

---

## Known issues (read this before trusting a number)

Full detail for all 95 entries is in `data_quality_log` / `data/csv/data_quality_log.csv`.
The five issue types found by the build script:

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

Figures are compiled from published annual reports and financial statements of each bank.
Always cross-check against a bank's official disclosures before using this data for investment
or research decisions — especially given the Mutual Trust Bank / Eastern Bank overlap noted
above.

This repository's **code and schema** are MIT licensed (see `LICENSE`). The underlying
**data** follows the same terms as the source `o-rnob/Datanest` repository (CC0 1.0 Universal).

## Citation

See `CITATION.cff`.

## Disclaimer

Provided for informational and research purposes only. Not financial advice. No guarantee is
made as to completeness or accuracy — that's the entire point of `data_quality_log`.
