[![DyingCyrus-DB logo](https://github.com/o-rnob/DyingCyrus-DB/raw/main/logo.jpg)](https://github.com/o-rnob/DyingCyrus-DB/blob/main/logo.jpg)

# DyingCyrus-DB

**Bangladesh Bank Financial Database — by Ow1nomics**

A single SQLite file (`dyingcyrus.db`) consolidating annual balance sheet, income statement,
profitability, asset-quality, and capital-adequacy data for **17 Bangladeshi banks** — 11
DSE-listed commercial banks (2015–2025) and 6 state-owned commercial/specialised banks, several
running back to their 1972 nationalisation — built from two source workbooks and hand-sourced
annual-report notes.

This is the companion database to [`Knightbase-DB`](https://github.com/o-rnob/Knightbase-DB)
(DSE price and macro data) and is built with the same rule:

> **Every skip, every conflict, every rename, and every known data-quality issue is logged and
> queryable — nothing is silently fixed, rescaled, or guessed at.**

If a number looks wrong — or impossibly extreme — query `data_quality_log` and `source_notes`
before assuming it's an error. For the state-owned banks in particular, triple-digit ROE swings
and negative equity are frequently the real, audited picture of a persistently loss-making bank,
not a parsing bug.

---

## What this is

`dyingcyrus.db` merges two segments into one schema:

- **CB (Commercial Banks)** — 11 DSE-listed private commercial banks, fiscal years 2015–2025,
  sourced from a single standardised workbook.
- **SOCB (State-Owned Commercial / Specialised Banks)** — Sonali Bank, Janata Bank PLC, and
  Rupali Bank PLC (all founded 1972, at nationalisation), Bangladesh Krishi Bank (est. 1973),
  BASIC Bank PLC (from 1989), and Bangladesh Development Bank PLC (from 2010) — hand-compiled
  from each bank's own audited annual reports, one bank at a time, with per-bank source notes
  documenting exactly which annual report each figure came from and why.

The SOCB segment is the harder, higher-value half of this dataset: audited annual reports for
Bangladesh's state banks are not standardised, several carry qualified audit opinions for
persistent capital shortfalls, and multiple years had to be cross-checked against a later
report's comparative column because the original year's report wasn't available. All of that
reconciliation work is preserved in `source_notes`, not collapsed into a single clean number.

---

## Quick stats

| | |
|---|---|
| Banks | 17 (11 CB, 6 SOCB) |
| Year span | 1972–2026 (CB: 2015–2025 · SOCB: per-bank, see coverage table below) |
| Financial line-item rows | 7,846 (`financials_cb`: 2,530 · `financials_socb`: 5,316) |
| Distinct standardised metrics | 20 (CB) / 21 (SOCB), catalogued in `metric_catalog` |
| Raw source cells preserved | 6,983 (`raw_cb`: 3,425 · `raw_socb`: 3,558) |
| Missing cells | 2,497 — stored as `NULL`, never zero-filled (143 CB, 2,354 SOCB) |
| Per-bank source notes | 35 entries across 6 SOCB banks, citing the exact annual report per figure |
| Data quality log entries | 248 (205 critical, 10 warning, 33 info) |
| Build version | 3.0.0, built 2026-09-20 |

### Per-bank coverage

**SOCB** — `core5` = the five headline metrics (total assets, gross loans, deposits, equity,
net profit after tax); `all` = every cell on that bank's sheet.

| Bank | Years compiled | Core-5 complete | All-cells complete |
|---|---|---|---|
| Sonali Bank | 1972–2025 (54 yrs) | 99.3% | 74.4% |
| Janata Bank PLC | 1972–2024 (53 yrs) | 100% | 65.3% |
| Rupali Bank PLC | 1972–2025 (54 yrs) | **50.7%** | 37.3% |
| Bangladesh Krishi Bank (BKB) | 2010–2025 (16 yrs) | 100% | 27.4% |
| BASIC Bank PLC | 1989–2023 (35 yrs) | 100% | 70.2% |
| Bangladesh Development Bank PLC (BDBL) | 2010–2024 (15 yrs) | 100% | 87.6% |

Rupali is the one SOCB bank still short on its headline five metrics — see Known Issues below.

**CB** — all 11 banks, 2015–2025 (Pubali from 2016). Core-5 completeness ranges 90.9%–100%;
all-cells completeness ranges 88.5%–99.0%. City Bank, BRAC Bank, Mercantile Bank, and
Southeast Bank are at 100%/99%; Eastern Bank PLC is the lowest at 90.9% core-5 / 89.0% all-cells
(see the duplicate-table and misaligned-row issues below).

---

## Quick start (Python)

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("dyingcyrus.db")

# ROE trend for one SOCB bank across its full audited history
roe = pd.read_sql("""
    SELECT year, value_numeric FROM financials_socb
    WHERE bank_id = 'sonali_bank' AND metric_std = 'roe_pct' AND table_instance = 1
    ORDER BY year
""", conn)

# Compare Total Assets across every bank (CB + SOCB) for 2024, via the pre-built view
assets_2024 = pd.read_sql("""
    SELECT segment, display_name, total_assets_tk_mn FROM v_all_year
    WHERE year = 2024
    ORDER BY total_assets_tk_mn DESC
""", conn)

# See every critical-severity issue logged against a bank before trusting its numbers
issues = pd.read_sql("""
    SELECT * FROM data_quality_log
    WHERE bank_id = 'rupali_bank_plc' AND severity = 'critical'
""", conn)

# Read the actual annual-report source trail for a bank's figures
notes = pd.read_sql("""
    SELECT note_index, note_text FROM source_notes
    WHERE bank_id = 'bangladesh_krishi_bank_bkb' ORDER BY note_index
""", conn)
```

---

## Schema

### `banks`
One row per bank: `bank_id` (slug PK), `display_name`, `sheet_name`, `bank_type` (`CB`/`SOCB`),
`ownership`, `source_file`, `year_min`/`year_max`, `n_tables` (>1 flags a duplicate table on
that bank's sheet — see Eastern Bank PLC below).

### `financials_cb` / `financials_socb`
The two segment-specific tidy/long tables — kept **separate**, not merged, because the two
source workbooks use different conventions (see `pct_scale` below). One row per (bank,
table_instance, metric, year):

| column | notes |
|---|---|
| `table_instance` | 1 = primary table. >1 = a duplicate table further down the same sheet |
| `category` | section header, e.g. `BALANCE SHEET`, `ASSET QUALITY`, `DERIVED METRICS (formulas)` |
| `metric` / `metric_std` | raw label as printed / standardised name used across both segments |
| `raw_value` | the exact original cell content, stringified — always preserved |
| `value_numeric` | parsed numeric value, or `NULL` if blank/unparseable |
| `value_pct_points` | for percentage metrics, normalised to percentage-point scale (see `pct_scale`) |
| `pct_scale` | `percent_points` / `fraction` / `*_inferred` — tags which convention the *raw* cell used |
| `value_source` | `native_numeric` / `recovered_from_text` / `missing_marker` / `missing` |
| `is_estimated` | always 0 in this build — no cell is a Claude/model estimate, only recovered or left null |
| `source_row` / `source_col` | exact Excel location, for traceability back to `raw_cb`/`raw_socb` |

### `raw_cb` / `raw_socb`
Every source cell as originally typed, before any parsing — `cell_text` + `cell_type`
(`float`/`int`/`str`). This is the audit trail underneath `financials_*`: if you don't trust a
parsed value, this is where you check what was actually in the workbook.

### `bank_summary_stats`
Per-bank summary-block figures pulled straight off each sheet (99 rows) — Mean ROE, CAGR, and
similar bank-reported summary statistics, long format.

### `source_notes`
35 free-text notes across the 6 SOCB banks, each citing which specific annual report a figure
came from, restatements between reports, definitional choices, and known gaps in the source
documents. This is the closest thing to a citation trail a hand-compiled dataset like this can
have — read it before disputing a SOCB number.

### `metric_catalog`
41 rows: one per (segment, standardised metric), with `canonical_unit`, `n_banks`, and
`n_values` — the fastest way to see which metrics have full coverage and which are thin
(e.g. `profit_before_tax` and `provision_maintained` are populated for only 1 SOCB bank each).

### `bank_coverage`
Per-bank completeness, computed two ways: `core5_*` (the five headline balance-sheet/income
metrics) and `all_*` (every cell on the sheet). This is the source of the coverage table above.

### `data_quality_log`
248 rows: `bank_id`, `metric`, `year` (all nullable — some issues are dataset-wide),
`issue` (machine-readable tag), `detail` (full explanation), `severity`
(`info`/`warning`/`critical`).

### Views
`v_cb_financials`, `v_socb_financials` — segment financials joined to `banks`, filtered to
`table_instance = 1`. `v_cb_year`, `v_socb_year`, `v_all_year` — one row per bank-year with
headline metrics pivoted into columns. `v_flagged` — every distinct (bank, year, issue) with a
critical-severity data quality flag, for a fast "what should I not trust" query.

---

## Known issues (read this before trusting a number)

Full detail for all 248 entries is in `data_quality_log`. The issue types found by the build:

**`percent_stored_as_fraction` (107 entries, critical).** ROA%/ROE%/CAR% and similar ratios are
stored as decimal fractions (e.g. `0.173`) on some banks' sheets and as percentage-points
(`17.3`) on others — inconsistent both within and across the CB and SOCB segments (13 of 17
banks affected). `value_pct_points` normalises this for you, but `value_numeric`/`raw_value`
keep the original convention — **check `pct_scale` before comparing ratios across banks.**

**`cross_bank_identical_value` (90 entries, critical) — Eastern Bank PLC vs. Mutual Trust Bank
PLC.** For 2015–2020, the two banks report byte-identical figures across 9 metrics and 45
(metric, year) cells — total assets, deposits, loans, EPS, and more. Not a plausible coincidence
for raw balance-sheet numbers; almost certainly a copy/paste error in the source workbook.
**Treat both banks' 2015–2020 balance-sheet and income-statement figures as unverified** until
checked against their own published annual reports.

**`roe_on_negative_equity` (5 entries, critical).** Bangladesh Krishi Bank (16 years,
2010–2025), BASIC Bank PLC (3 years, 2021–2023), and one year each for Janata, Rupali, and
Sonali report negative shareholders' equity in years an ROE is also printed. With negative
equity, ROE = profit/equity flips sign — a loss shows as a *positive* ROE. These figures are
arithmetically correct but economically meaningless; **use net profit and equity in Tk mn
instead of ranking or averaging the printed ROE.**

**`value_outside_plausible_range` (9 entries, warning).** Ratios like Sonali Bank's 1982 ROE
(378.7%) or BASIC Bank's 2021 ROE (690.5%) sit outside a sanity band. Not altered — for the
state-owned banks these extremes are frequently **real**, driven by deeply negative capital or
negative net interest income. Check `source_notes` for that bank before calling it an error.

**`reported_ratio_not_reproducible` (1 entry, warning) — IFIC Bank PLC.** 2025 ROE is printed
as -139.59% but recomputes to -452.73% from the same sheet's own inputs (69% apart) — most
likely a reporting-basis difference (average vs. closing denominator), not an error. Both
figures are preserved; check the annual report before quoting either.

**`misaligned_duplicate_row` (2 entries, critical) — Eastern Bank PLC.** Two rows on the Eastern
Bank sheet are shifted one column left relative to the header, with values also appearing
rescaled (÷100) versus the aligned copy of the same metric. Loaded with the shift corrected,
marked `table_instance = 2`.

**`duplicate_table_on_sheet` (1 entry, critical) — Eastern Bank PLC.** The sheet contains the
full metric/unit table twice (header rows 14 and 48). Both copies are loaded; `table_instance =
1` is the authoritative one and the only instance exposed by the `v_*` views.

**`text_cell_with_recoverable_number` (5 entries, info), `missing_marker_cell` (14, info),
`empty_year_column` (7, info), `bank_name_normalised` (6, info).** Footnote-marked numbers
recovered with the marker kept in `raw_value`; explicit "no data" markers vs. genuinely blank
cells distinguished; a handful of blank year columns (e.g. BDBL 2025–2026, pending an annual
report); minor display-name normalisations logged for traceability.

**Not a logged issue, but worth knowing: `is_estimated` is 0 for all 5,316 SOCB rows and 2,530
CB rows.** No cell in this database is a model-generated estimate — every non-null figure was
either read directly from a source document or recovered from a footnoted/text cell; everything
else is `NULL`.

---

## Repository structure

```
DyingCyrus-DB/
├── logo.jpg                                    # repo cover image
├── build_db.py                                 # ETL script — rebuilds dyingcyrus.db from scratch
├── dyingcyrus.db                               # the SQLite database (output of build_db.py)
├── requirements.txt
├── data/
│   ├── raw/
│   │   ├── DATASET_11_BANKS_2025-2015_.xlsx         # CB source workbook, untouched
│   │   └── Dying_Cyrus_-_SOCB_V7__furnished_.xlsx   # SOCB source workbook, untouched
│   └── csv/                                    # long/wide exports of financials_* and data_quality_log
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

CB figures are compiled from the standardised 11-bank workbook. SOCB figures are hand-compiled,
bank by bank, from each institution's own audited annual reports and auditors' reports — the
specific report and page/table used for every figure is logged in `source_notes`. Always
cross-check against a bank's official disclosures before using this data for investment,
research, or policy analysis — especially given the Eastern Bank / Mutual Trust Bank overlap
and the SOCB qualified-audit-opinion years noted above.

This repository's **code and schema** are MIT licensed (see `LICENSE`). The underlying **data**
follows the same CC0 1.0 Universal terms as the companion [`Datanest`](https://github.com/o-rnob/Datanest)
repository.

## Citation

See `CITATION.cff`.

## Disclaimer

Provided for informational and research purposes only. Not financial advice. No guarantee is
made as to completeness or accuracy — that's the entire point of `data_quality_log`.
