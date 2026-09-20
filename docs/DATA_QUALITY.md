# Data quality — read this before trusting a number

The whole point of this repository is that problems are **logged, not fixed**.
`data_quality_log` holds 248 entries: 205 critical, 10 warning, 33 info. Nothing
in `financials_cb.value_numeric` or `financials_socb.value_numeric` has been
rescaled, corrected or guessed at — and the raw layer (`raw_cb` / `raw_socb`)
holds every source cell exactly as read, so you can always go back to the
original.

Start here:

```sql
SELECT severity, issue, COUNT(*) FROM data_quality_log GROUP BY 1, 2 ORDER BY 3 DESC;
SELECT * FROM data_quality_log WHERE bank_id = 'the_bank_you_care_about';
```

---

## Critical

### `percent_stored_as_fraction` — 107 entries, 13 banks

The two source workbooks do not share a convention for percentages. Some sheets
write ROE as `17.3`; others write `0.173` for the same quantity, with the Unit
column saying `%` in both cases.

Affected banks (for at least one metric): BDBL, Bangladesh Krishi Bank, BASIC
Bank, City Bank, Dutch-Bangla Bank, IFIC Bank, Janata Bank, Mercantile Bank,
Mutual Trust Bank, Pubali Bank, Rupali Bank, Sonali Bank, Southeast Bank.

The build does **not** rewrite `value_numeric`. It adds `value_pct_points`,
which always holds percentage points, and records in `pct_scale` how that was
decided. Where possible the decision is evidence-based: the ratio is rebuilt
from its own inputs on the same sheet (ROA from net profit ÷ total assets, ROE
from net profit ÷ equity, loan-deposit from loans ÷ deposits, NPL% from NPL
amount ÷ loans), scored against both conventions across at least three years,
and the better fit wins. The mean error under each convention is written into
the log entry so you can check the call yourself.

This matters more than it sounds. A naive magnitude rule ("anything under 1.5
must be a fraction") gets Bank Asia's genuine 0.79% ROA wrong by a factor of
100, and gets Sonali Bank's 1982 ROE of 3.79 — which really is a fraction,
meaning 379% — wrong in the other direction.

**What to do:** use `value_pct_points`, or just use the `v_cb_year` / `v_socb_year`
views, which have applied the rule already.

### `roe_on_negative_equity` — 5 entries (one per bank)

ROE = profit ÷ equity. When equity is **negative**, a *loss* divided by negative
equity prints as a **positive** ROE, and a profit prints as a negative one. The
figures are arithmetically valid and economically meaningless.

| Bank | Years with negative equity **and** a printed ROE |
|---|---|
| Bangladesh Krishi Bank | 2010–2025 (16 years; equity reaches about −Tk 275 bn) |
| BASIC Bank | 2021–2023 |
| Janata Bank | 2006 |
| Sonali Bank | 2006 |
| Rupali Bank | 2009 |

Krishi Bank is the extreme case: net loss in every year since 2011, negative
equity throughout, and yet a printed ROE between roughly +5% and +65%.

The build does not alter these values. `value_pct_points` is still the correct
restatement of what the sheet printed — the problem is that the *ratio itself* is
uninformative here.

**What to do:** never rank, average or chart these ROE values as if higher were
better. Use net profit and equity in Tk mn (`npat_tk_mn`, `equity_tk_mn`).
`DyingCyrus.series(bank, "roe_pct")` adds a `negative_equity` flag to every year.
To find them all:

```sql
SELECT segment, display_name, year, equity_tk_mn, roe_pct
FROM v_all_year WHERE equity_tk_mn < 0 AND roe_pct IS NOT NULL;
```

### `cross_bank_identical_value` — 90 entries (45 cells, logged under both banks)

**Eastern Bank PLC and Mutual Trust Bank PLC.** For 2015 and 2017–2020, nine
metrics — total assets, gross loans and advances, total deposits, shareholders'
equity, net interest income, non-interest income, net profit after tax, EPS and
NPL amount — are byte-identical between the two banks.

That is not a coincidence for raw Taka-million balance-sheet figures. It is
almost certainly a copy/paste error in the source workbook. Mutual Trust Bank's
2021–2025 figures are distinct and plausible.

**What to do:** treat Mutual Trust Bank's 2015 and 2017–2020 balance-sheet and
income-statement figures as **unverified** until you have checked them against
MTB's published annual reports. If you are running a panel regression, drop
those bank-years or use the `v_flagged` anti-join shown in
[SCHEMA.md](SCHEMA.md).

### `duplicate_table_on_sheet` — 1 entry

The `Eastern Bank Ltd` worksheet contains its full Metric/Unit table twice
(header rows 14 and 48). Both copies are loaded. `table_instance = 1` is
authoritative and is the only one the `v_*` views expose. Query
`table_instance = 2` only if you want to compare the copies.

### `misaligned_duplicate_row` — 2 entries

Rows 74 and 75 of the same Eastern Bank sheet carry their data starting in the
Unit column — the whole row is shifted one column left relative to the header,
and the values also appear divided by 100 versus the aligned copy of the same
metric. The build corrects the column alignment so the years line up, marks the
rows `table_instance = 2`, and logs both facts. It does **not** undo the
apparent ÷100.

---

## Warning

### `value_outside_plausible_range` — 9 entries

A ratio outside a generous sanity band. Nothing is altered; this is a prompt to
look, not a verdict.

Most of these are **real**, not errors, and the state-owned banks' own source
notes explain them:

* Bangladesh Krishi Bank's cost-to-income ratio reaches several hundred percent
  (and −1,239% in 2024) because its net interest income is deeply negative —
  interest paid exceeds interest earned — so the denominator collapses and flips
  sign. The bank's sheet says exactly this.
* BKB's capital adequacy ratio runs from roughly −37% to −133%. Also real; every
  year from FY2014 onward carries a qualified audit opinion.
* BDBL's loan-deposit ratio exceeds 300% in 2010 on a very small deposit base.
* BASIC Bank's 2021 ROE of 691% and Sonali Bank's 1982 ROE of 379% both come
  from tiny equity denominators.

Always read `source_notes` for the bank before calling one of these a mistake.

### `reported_ratio_not_reproducible` — 1 entry

A reported ratio that its own inputs on the same sheet do not reproduce, once
the percentage convention is settled. Only one case exists in this build:

* **IFIC Bank PLC, ROE 2025.** The sheet reports −139.59%. Net profit after tax
  divided by closing shareholders' equity rebuilds to −452.73%, because IFIC's
  equity collapsed from Tk 31,045 mn to Tk 5,658 mn during the year. The
  reported figure is almost certainly computed on average equity. Neither
  version is altered; decide which basis you want and say which you used.

That only one such case exists across 17 banks and five decades is a reasonable
sign the rest of the dataset is internally consistent.

### `percent_scale_undetermined`

Raised when a `%` series cannot be rebuilt from other rows *and* the rest of the
sheet gives no usable convention. `value_pct_points` is left equal to
`value_numeric`. Verify against the annual report before comparing that series
across banks. (No entries in the current build.)

### `unrecoverable_text_cell`

A cell holding text that is neither a number nor a recognised
"no-figure" placeholder. Stored as NULL, original text kept in `raw_value`.
(No entries in the current build.)

---

## Info

### `missing_marker_cell` — 14 entries

Aggregated per bank and per placeholder token. Cells holding `N/A`, `n/a*`,
`N/M`, `N/A⁴`, `nil` and similar are recorded as NULL in `value_numeric` with
the placeholder preserved in `raw_value`. **Never zero-filled.** 2,497 of the
7,846 loaded cells carry no numeric value (see `bank_coverage` for completeness measured properly) — most of them are the years before a
bank's data begins (Sonali, Janata and Rupali have year columns back to 1972
that are only partly populated; Krishi Bank's 1973–2009 columns are empty by
design).

### `empty_year_column` — 7 entries

A year column with no data at all for that bank. Notably Eastern Bank has no
2016 data for any metric.

### `text_cell_with_recoverable_number` — 5 entries

Cells like `'80.31%*'` or `'165,370†'` where the compiler attached a footnote
marker to a figure. The number is recovered into `value_numeric`; the footnote
survives in `raw_value` so you know it was flagged as unusual by whoever
compiled the source workbook.

### `bank_name_normalised` — 6 entries

The source sheets title a few banks loosely or with typos (`MTB-`, `Brac Bank
LTD`, `Dutch Banlga Bank Ltd`, `South East Bank PLC`). `display_name` carries
the corrected legal name; `banks.sheet_title` preserves the original string.

### `dataset_summary` — 1 entry

Row counts for this build.

---

## Things that are *not* logged but you should know

* **Coverage.** `bank_coverage` reports how complete each bank's five core series
  are — inside its compiled range (`core5_pct`) and across every year column on
  the sheet (`core5_pct_sheet`). Rupali Bank is the one state-owned bank well
  below full: its notes say 1972–1996 carry only deposits, loans and pre-tax
  profit, 1997–2007 are missing, and NPAT exists only from 2009.
* **`is_estimated = 1`.** Several private-bank sheets publish "Estimated NPL
  amount (NPL% × Loans)" rather than a reported NPL figure. These map to
  `npl_amount` like any other, but the flag is set. Filter on it if you need
  as-reported figures only.
* **Solo versus group.** Some sheets print "CRAR % (Group)" and
  "Cost-to-Income Ratio % (Group)"; others print the solo equivalents. Both map
  to `car_pct` and `cost_income_pct`. `metric_catalog.raw_labels` tells you
  which labels are in play; the source workbooks do not resolve the difference.
* **Restatements.** The state-owned sheets note where a later annual report
  restated an earlier year and which version was used. The database stores the
  chosen figure; the note explains the choice.
* **2026 columns.** Sonali Bank and Bangladesh Krishi Bank have a 2026 column in
  the source workbook. It is mostly empty and is a placeholder, not a forecast.
