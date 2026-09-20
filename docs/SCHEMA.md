# Schema reference

`dyingcyrus.db` is a plain SQLite 3 file: 11 tables, 6 views, no extensions, no
stored procedures. Everything below is queryable with any SQL client written in
the last twenty years.

There are **two segments**, kept in physically separate tables so they can never
be mixed by accident:

| Segment (`banks.bank_type`) | Harmonised | Raw | View |
|---|---|---|---|
| `CB` — commercial banks (private, DSE-listed) | `financials_cb` | `raw_cb` | `v_cb_year`, `v_cb_financials` |
| `SOCB` — state-owned & specialised banks | `financials_socb` | `raw_socb` | `v_socb_year`, `v_socb_financials` |

`v_all_year` stacks the two, for the times you deliberately want that.

```
banks ──┬── financials_cb / financials_socb   harmonised layer (the data)
        ├── raw_cb / raw_socb                 raw layer: every source cell, as read
        ├── bank_coverage                     completeness of the core series
        ├── bank_summary_stats                per-bank stats printed on the source sheet
        ├── source_notes                      the compiler's own sourcing notes
        └── data_quality_log                  every known problem
metric_catalog                                metric dictionary, per segment
build_metadata                                provenance of this build
```

> Version 2 called the commercial segment `PCB` and kept everything in a single
> `financials` table. Version 3 renames it `CB` and splits the tables. See the
> [changelog](CHANGELOG.md#300--2026-09-20) for the migration.

---

## `banks`

One row per source worksheet.

| column | type | notes |
|---|---|---|
| `bank_id` | TEXT PK | slug, e.g. `city_bank_plc`, `bangladesh_krishi_bank_bkb` |
| `display_name` | TEXT | corrected legal name, e.g. `BRAC Bank PLC` |
| `sheet_name` | TEXT | exact worksheet name in the source workbook |
| `bank_type` | TEXT | segment: `CB` (commercial, private DSE-listed) or `SOCB` (state-owned / specialised) |
| `ownership` | TEXT | plain-English ownership description |
| `source_file` | TEXT | which workbook this sheet came from |
| `sheet_title` | TEXT | the sheet's own title string, typos and all |
| `year_min`, `year_max` | INTEGER | first and last year with any numeric value |
| `n_tables` | INTEGER | `> 1` means the sheet repeats its data table (see `table_instance`) |

Where `display_name` differs from `sheet_title`, the correction is recorded in
`data_quality_log` under `bank_name_normalised`.

---

## `financials_cb` and `financials_socb`

The harmonised layer, in tidy/long format, one table per segment with identical
columns. One row per (bank, table instance, metric, source row, year). A bank's
rows live only in its own segment's table.

| column | type | notes |
|---|---|---|
| `bank_id` | TEXT | FK → `banks` |
| `table_instance` | INTEGER | `1` = the authoritative table on the sheet. `>1` = a repeated copy found further down the same sheet. The `v_*` views expose instance 1 only. |
| `category` | TEXT | section header above the row: `BALANCE SHEET`, `ASSET QUALITY`, `DERIVED METRICS (formulas)`, … |
| `metric` | TEXT | the raw label exactly as printed on the sheet |
| `metric_std` | TEXT | **harmonised key — join and filter on this**, e.g. `total_assets`, `car_pct` |
| `unit` | TEXT | raw unit label: `Tk mn`, `%`, `BDT` |
| `year` | INTEGER | 1972–2026 |
| `raw_value` | TEXT | **the original cell content, stringified, always preserved** — footnote markers and all |
| `value_numeric` | REAL | parsed number **exactly as the sheet held it**, or NULL |
| `value_pct_points` | REAL | for `%` metrics: the same figure restated in percentage points |
| `pct_scale` | TEXT | how that restatement was decided (see below) |
| `value_source` | TEXT | `native_numeric` · `recovered_from_text` · `missing_marker` · `missing` · `unrecoverable_text` |
| `is_estimated` | INTEGER | `1` where the source sheet labelled the figure an estimate (e.g. "Estimated NPL amount (NPL% × Loans)") |
| `source_file` | TEXT | which workbook |
| `source_row` | INTEGER | 1-indexed row in the original sheet |
| `source_col` | TEXT | Excel column letter |

### `value_numeric` vs `value_pct_points`

This is the single most important thing in the database.

The source sheets do not agree on how to write a percentage. Some banks write
ROE as `17.3`; others write `0.173` for the same quantity, even though both
sheets label the unit `%`. Comparing them raw gives an answer wrong by 100×.

* **`value_numeric` is never altered.** It is whatever the cell held.
* **`value_pct_points` is the derived, comparable column.** For every `%` metric
  it holds the figure in percentage points, so `17.3` means 17.3%.
* **`pct_scale`** records how that was decided:
  * `percent_points` / `fraction` — verified. The ratio was rebuilt from its
    own inputs on the same sheet (ROA from NPAT ÷ assets, ROE from NPAT ÷
    equity, loan-deposit from loans ÷ deposits, NPL% from NPL amount ÷ loans)
    and scored against both conventions over at least three years. The better
    fit won, and the arithmetic is written into the quality-log entry.
  * `percent_points_inferred` / `fraction_inferred` — the metric cannot be
    rebuilt from other rows (CAR, provision coverage, cost-to-income), so it
    inherits the convention the rest of that bank's sheet demonstrably uses.
  * `assumed_percent_points` / `unknown` — no evidence either way. Verify
    against the annual report before comparing across banks.

Rule of thumb: **`value_numeric` for money and per-share figures,
`value_pct_points` for anything ending in `_pct`.** The `v_cb_year` and
`v_socb_year` views have already applied this rule for you.

### Ratios on negative equity

`roe_pct` = profit ÷ equity. Where equity is negative, a loss prints as a
positive ROE. `value_pct_points` faithfully restates what the sheet printed, but
the ratio is uninformative in those years. They are logged as
`roe_on_negative_equity` (see [DATA_QUALITY.md](DATA_QUALITY.md)); find them with
`equity_tk_mn < 0 AND roe_pct IS NOT NULL` on `v_all_year`.

---

## `raw_cb` and `raw_socb`

The raw layer. Every **non-empty** cell of every source worksheet, exactly as the
workbook held it. Nothing is mapped, converted, scaled or interpreted — this is
what the harmonised layer was built from.

| column | type | notes |
|---|---|---|
| `bank_id` | TEXT | FK → `banks` |
| `sheet_name` | TEXT | worksheet name |
| `source_row` | INTEGER | 1-indexed row |
| `col_index` | INTEGER | 1 = column A |
| `source_col` | TEXT | Excel column letter |
| `cell_text` | TEXT | the value, stringified without alteration (floats keep full precision) |
| `cell_type` | TEXT | the Python type read from the workbook: `str`, `int`, `float`, … |

Primary key `(bank_id, source_row, col_index)`. A cell's `source_row` /
`source_col` here matches the same columns in `financials_*`, so any harmonised
number can be traced to its raw cell:

```sql
SELECT f.metric, f.year, f.value_numeric, r.cell_text, r.cell_type
FROM financials_socb f
JOIN raw_socb r ON r.bank_id = f.bank_id AND r.source_row = f.source_row
                AND r.source_col = f.source_col
WHERE f.bank_id = 'sonali_bank' AND f.metric_std = 'total_assets' AND f.year = 2024
  AND f.table_instance = 1;
```

The same data is exported as one CSV per bank that mirrors the workbook tab
cell-for-cell: `data/csv/cb/raw/<bank_id>_raw_sheet.csv` and
`data/csv/socb/raw/<bank_id>_raw_sheet.csv`.

---

## `bank_coverage`

One row per bank: how complete are the five core series (total assets, gross
loans, deposits, shareholders' equity, net profit after tax)?

| column | notes |
|---|---|
| `segment` | `CB` or `SOCB` |
| `year_first`, `year_last`, `years_on_sheet` | the year columns printed on the sheet |
| `compiled_first`, `compiled_last`, `compiled_years` | first to last year with any core-5 figure |
| `core5_expected`, `core5_filled` | 5 × `compiled_years`, and how many exist |
| `core5_pct` | **headline** — completeness inside the compiled range |
| `core5_pct_sheet` | same numerator, over every year column on the sheet |
| `all_cells`, `all_filled`, `all_pct` | the same idea across every metric |
| `core5_years_full` | years in which all five core series exist |
| `first_core5_full`, `last_core5_full` | first / last such year |

Use `core5_pct` to judge data quality. `core5_pct_sheet` is lower for banks whose
sheet has empty year columns before the data begins (Krishi Bank: 29.6% vs 100%).

---

## `bank_summary_stats`

The per-bank summary block printed above the data table on the private-bank
sheets — mean ROE, standard deviation, Sharpe-like ratio, equity CAGR, max
drawdown in NPAT, Newey-West (HAC) trend slope of NPL% against year, and the
rolling-window versions of those.

| column | type | notes |
|---|---|---|
| `bank_id` | TEXT | FK → `banks` |
| `stat_name` | TEXT | label as printed |
| `value` | REAL | |
| `source_row` | INTEGER | |

These are the *compiler's* calculations, reproduced as found. They were not
recomputed during the build and are not guaranteed to agree with what you would
get from `financials`.

---

## `source_notes`

The state-owned-bank sheets carry long prose notes on sourcing, restatements,
definitional choices and audit qualifications. They are extracted verbatim.

| column | type | notes |
|---|---|---|
| `bank_id` | TEXT | FK → `banks` |
| `note_index` | INTEGER | order on the sheet |
| `note_text` | TEXT | verbatim |
| `source_row` | INTEGER | |

Read these. For the state-owned banks they explain nearly every figure that
looks impossible — for example, why Bangladesh Krishi Bank's cost-to-income
ratio goes to several hundred percent (deeply negative net interest income), and
why its capital adequacy ratio is around −133%.

---

## `data_quality_log`

| column | type | notes |
|---|---|---|
| `log_id` | INTEGER PK | |
| `bank_id` | TEXT | nullable — some entries are dataset-wide |
| `metric` | TEXT | nullable |
| `year` | INTEGER | nullable |
| `issue` | TEXT | machine-readable tag |
| `detail` | TEXT | full human-readable explanation, including the evidence |
| `severity` | TEXT | `info` · `warning` · `critical` |

Issue tags are documented in [DATA_QUALITY.md](DATA_QUALITY.md).

---

## `metric_catalog`

| column | notes |
|---|---|
| `segment` | `CB` or `SOCB` — the key is `(segment, metric_std)` |
| `metric_std` | the harmonised key |
| `canonical_unit` | |
| `n_banks` | how many banks report it |
| `n_values` | how many non-null cells exist |
| `raw_labels` | every source label that maps to this key, `\|`-separated |

Useful when you want to know whether `car_pct` came from a sheet that printed
"Capital Adequacy Ratio %" or "CRAR % (Group)" — a solo-versus-group difference
the source workbooks do not resolve.

---

## `build_metadata`

Key/value: build version, UTC build timestamp, Python version, source filenames,
row counts, licences. Cite `built_at_utc` when you cite the dataset.

---

## Views

### `v_cb_financials` · `v_socb_financials`
Instance-1 rows with a numeric value, joined to bank names, per segment. The
general-purpose starting point for long-format work.

### `v_cb_year` · `v_socb_year`
One row per bank-year, core metrics as columns, **percentages already in
percentage points**, per segment. Columns: `total_assets_tk_mn`, `loans_tk_mn`,
`deposits_tk_mn`, `equity_tk_mn`, `nii_tk_mn`, `non_interest_income_tk_mn`,
`npat_tk_mn`, `npl_amount_tk_mn`, `eps_bdt`, `roa_pct`, `roe_pct`, `npl_pct`,
`provision_coverage_pct`, `loan_deposit_pct`, `car_pct`, `cost_income_pct`.

These are the views you want for regressions, charts and panels.

### `v_all_year`
`v_cb_year` and `v_socb_year` stacked, with a leading `segment` column. Use it
only when you deliberately want both segments together (e.g. a cross-segment
NPL comparison) — they are compiled from different source workbooks.

### `v_flagged`
Every (bank, year, issue) carrying a critical flag. Anti-join against it to get
a conservative research subset (some log entries are bank-wide with no year,
so also check `data_quality_log` for the bank):

```sql
SELECT v.* FROM v_cb_year v
WHERE NOT EXISTS (SELECT 1 FROM v_flagged f
                  WHERE f.bank_id = v.bank_id AND f.year = v.year);
```
