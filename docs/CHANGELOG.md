# Changelog

## 3.0.0 — 2026-09-20

The two bank segments are separated, a raw layer is added, and coverage is
reported honestly.

### Changed — breaking
- **Segments are physically separate.** The single `financials` table is now
  `financials_cb` and `financials_socb`; `v_bank_year` is now `v_cb_year` and
  `v_socb_year`; `v_financials` is now `v_cb_financials` and `v_socb_financials`.
  `v_all_year` stacks them, for the times you deliberately want that.
- **`PCB` is now `CB`** (`banks.bank_type`). The Python API still accepts `"PCB"`
  and maps it to `"CB"`.
- **CSV layout:** `data/csv/all_banks_*.csv` and `data/csv/per_bank/` are replaced
  by `data/csv/cb/` and `data/csv/socb/` (each with `*_bank_year.csv`,
  `*_long.csv`, `per_bank/`, `raw/`). Shared reference tables stay in `data/csv/`.
- `metric_catalog` is keyed by `(segment, metric_std)`.
- `data/json/bank_year.json` is replaced by `cb_bank_year.json` and
  `socb_bank_year.json`.
- API: `panel(bank_type=…)` → `panel(segment, …)`, `compare(…, bank_type=…)` →
  `compare(…, segment)`.

**Migrating a v2 query:** `FROM financials` → `FROM financials_cb` or
`financials_socb`; `FROM v_bank_year` → `FROM v_cb_year`, `v_socb_year` or
`v_all_year`.

### Added
- **Raw layer.** `raw_cb` / `raw_socb` hold every non-empty source cell exactly
  as read (6,983 cells, verified against the workbooks with zero mismatches),
  plus `data/csv/*/raw/<bank>_raw_sheet.csv` mirroring each tab cell-for-cell.
  The harmonised layer is now lossless-by-construction: nothing is discarded.
- **`bank_coverage` table** and the coverage tables in the README. Coverage is
  reported inside each bank's compiled range (`core5_pct`) and across the whole
  sheet (`core5_pct_sheet`). Five of six state-owned banks are 99–100% complete
  on the core five series; Rupali is about 51%.
- **`roe_on_negative_equity`** data-quality check (5 critical entries). ROE = profit
  ÷ equity, so with negative equity a loss prints as a positive ROE. Krishi Bank
  is the extreme case (2010–2025). `series(…, "roe_pct")` adds a
  `negative_equity` flag per year.
- API: `segment_of()`, `coverage()`, `raw()`.

### Changed
- README leads with coverage instead of the count of empty cells. Those cells
  mostly sit in year columns before a bank's data begins, not in the data itself.
- Docs, examples, SQL cookbook and quickstart rewritten for the segmented layout.

### Unchanged
- Every figure. Row counts (7,846 harmonised cells), the 22 metric keys, the
  percentage-scale handling and all 243 original log entries are identical to 2.0.0.

## 2.0.0 — 2026-09-20

The state-owned banks arrive, and the percentage handling is rebuilt.

### Added
- **6 state-owned and specialised banks** from
  `Dying_Cyrus_-_SOCB_V7__furnished_.xlsx`: Sonali, Janata, Rupali, BASIC, BDBL
  and Bangladesh Krishi Bank. Coverage now starts in **1972** rather than 2015.
- `banks.bank_type` (`PCB` / `SOCB`) and `banks.ownership`, so private and
  state-owned banks can be compared or separated in one query.
- **`source_notes` table** — the long sourcing notes printed on the SOCB sheets,
  extracted verbatim. These explain restatements, audit qualifications and
  definitional choices, and are essential context for the SOCB figures.
- **`value_pct_points` and `pct_scale` columns**, so percentages are comparable
  across banks without touching `value_numeric`.
- **`metric_std` column and `metric_catalog` table** — 22 harmonised keys behind
  30+ raw labels, so `CRAR % (Group)` and `Capital Adequacy Ratio %` can be
  queried as one metric.
- **`is_estimated` flag** for figures the source sheets label as estimates.
- **`build_metadata` table** recording build version, timestamp and row counts.
- **Three views**: `v_financials`, `v_bank_year`, `v_flagged`.
- **`dyingcyrus.py`** — a zero-dependency Python API.
- **JSON exports** in `data/json/` for browser and JavaScript use.
- **`docs/`**: user manual, schema reference, data-quality catalogue, AI guide.
- **`examples/`**: a runnable quickstart and a SQL cookbook.

### Changed
- **Percentage-scale detection is now evidence-based, not magnitude-based.**
  Version 1 assumed any `%` figure under ~1.5 was a fraction. That misreads Bank
  Asia's genuine 0.79% ROA as 79%, and misses Sonali Bank's 1982 ROE of 3.79,
  which really is a fraction meaning 379%. The build now rebuilds each ratio
  from its own inputs on the same sheet, scores both conventions over at least
  three years, and writes the arithmetic into the log entry.
- Bank names are normalised to their legal forms (`MTB-` → `Mutual Trust Bank
  PLC`, `Brac Bank LTD` → `BRAC Bank PLC`, `Dutch Banlga Bank Ltd` →
  `Dutch-Bangla Bank PLC`), with the original string kept in `banks.sheet_title`
  and every change logged.
- Placeholder cells (`N/A`, `N/M`, `n/a*`, `N/A⁴`) are recorded as
  `missing_marker` and aggregated per bank, instead of producing one warning per
  cell. They remain `NULL`, never zero.
- The primary key on `financials` now includes `source_row`, so repeated metric
  labels on the same sheet no longer collide.
- `data/raw/` and `build_db.py` are committed. Version 1's README described
  them but the files were never pushed, so the build could not be reproduced.

### Verified as still present
- The **Eastern Bank / Mutual Trust Bank identical-figures problem** persists in
  the updated workbook: 45 cells across 9 metrics for 2015 and 2017–2020. It is
  now logged under both banks, so a query on either finds it.
- The **duplicated table** on the Eastern Bank sheet and the shifted, rescaled
  rows 74–75.

## 1.0.0
Initial release: 11 DSE-listed private commercial banks, 2015–2025, SQLite
build of the CSV-based `o-rnob/Datanest` dataset.
