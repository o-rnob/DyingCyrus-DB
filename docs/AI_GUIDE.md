# Using DyingCyrus-DB with AI

This dataset works well with ChatGPT, Claude, Gemini, Copilot, Cursor and
notebook assistants — but only if you give the model the facts it cannot guess:
the percentage-scale trap, the negative-equity ROE trap, and the fact that some
of the numbers are known to be wrong.

Everything below is copy-paste ready.

---

## 1. The fastest path: upload a CSV and paste the primer

Most chat assistants accept file uploads and can run Python on them.

1. Upload **`data/csv/cb/cb_bank_year.csv`** and/or
   **`data/csv/socb/socb_bank_year.csv`** (one row per bank-year, percentages
   already comparable) — upload only the segment you are asking about — and, if
   you plan to cite anything, **`data/csv/data_quality_log.csv`**.
2. Paste the primer in section 3 as your first message.
3. Ask your question.

The two `*_bank_year.csv` files are small and fit comfortably in any modern
context window. The `*_long.csv` files are much larger — upload one only if you
specifically need cell-level provenance. The `raw/` CSVs mirror the original
sheets; upload one only to audit a specific bank against its source.

---

## 2. Letting an AI write code against the database

If your assistant can run code (Claude with code execution, ChatGPT Advanced
Data Analysis, Cursor, a notebook copilot), upload `dyingcyrus.db` and
`dyingcyrus.py` together and paste the primer. The model then has a typed API
instead of guessing at column names:

```python
from dyingcyrus import DyingCyrus
db = DyingCyrus("dyingcyrus.db")
db.panel("SOCB")
```

For coding agents working in the repo, point them at `docs/SCHEMA.md` first.
It is written to be read by a model as well as a person.

---

## 3. The primer — paste this first

> You are working with **DyingCyrus-DB**, an open financial dataset of 17
> Bangladeshi banks in two separate segments: 11 DSE-listed commercial banks
> (`CB`, fiscal years 2015–2025) and 6 state-owned or specialised banks (`SOCB`,
> coverage back to 1972 for Sonali, Janata and Rupali). They come from different
> source workbooks; do not pool them unless I ask. All money figures are in
> **Tk mn** (millions of Bangladeshi Taka); EPS is in BDT.
>
> Six rules you must follow:
>
> 1. **Percentages.** The source sheets disagree on convention: some write ROE
>    as `17.3`, others as `0.173`. The column `value_numeric` preserves the
>    source figure untouched. Use **`value_pct_points`** for any percentage, or
>    use the **`v_cb_year` / `v_socb_year`** views (or the `*_bank_year.csv`
>    files), where the conversion is already applied. Never compare `value_numeric` across banks
>    for a `%` metric.
> 2. **Known-bad data.** Eastern Bank PLC and Mutual Trust Bank PLC carry
>    byte-identical figures for 2015 and 2017–2020 across nine metrics — almost
>    certainly a copy/paste error in the source workbook. Treat Mutual Trust
>    Bank's figures for those years as unverified, say so in your answer, and
>    exclude them from any average, ranking or regression unless I ask
>    otherwise.
> 3. **Nulls are not zeros.** Missing cells are NULL. Many year columns exist
>    but are empty (Krishi Bank has no data before 2010; Eastern Bank has no
>    2016; Rupali has only deposits, loans and pre-tax profit in 1972–1996 and nothing for 1997–2007). Check
>    `bank_coverage` for how complete a bank is. Never fill a gap with zero, and
>    never interpolate without telling me.
> 4. **ROE on negative equity is meaningless.** ROE = profit ÷ equity, so where
>    equity is negative a *loss* prints as a *positive* ROE. This affects Krishi
>    Bank (2010–2025) and single years at Sonali, Janata, Rupali and BASIC
>    (2021–2023). Never rank, average or chart those ROE values as if higher were
>    better; use net profit and equity instead, and say so.
> 5. **Extreme values are often real.** Bangladesh Krishi Bank's capital
>    adequacy ratio near −133% and cost-to-income ratios in the hundreds of
>    percent are genuine, and the `source_notes` table explains why. Check
>    `source_notes` for a bank before calling any figure an error.
> 6. **Cite provenance.** Every figure carries `source_file`, `source_row` and
>    `source_col`, and the untouched source cell is in `raw_cb` / `raw_socb`.
>    When I ask where a number came from, give me those, not a guess.
>
> Before answering any question about a specific bank, check
> `data_quality_log` for that `bank_id` and mention anything critical.

---

## 4. Prompts that work well

**Exploration**

> Using v_all_year, chart average gross NPL % for CB versus SOCB banks from
> 2015 to 2025. Exclude any bank-year that appears in v_flagged, and tell me
> which ones you dropped.

**Screening**

> List every bank-year where the capital adequacy ratio is below the 10%
> regulatory minimum. Give bank, year, CAR, and whether the bank is state-owned.

**Provenance**

> What is Rupali Bank's 2024 NPL amount, and exactly which cell of which
> workbook did it come from? Quote the raw_value too.

**Data quality**

> Using bank_coverage, tell me which banks I can trust for a 1990–2020 study of
> deposits and equity, and which have gaps. Explain each gap from source_notes.

**Narrative from the notes**

> Summarise the source_notes for Bangladesh Krishi Bank in plain English. What
> do they say about the audit opinions and the capital shortfall?

**Modelling**

> Build a fixed-effects panel regression of ROE on NPL %, CAR and the
> cost-to-income ratio, using only bank-years with no critical flag. Report the
> sample size and which observations were excluded and why.

---

## 5. What AI gets wrong on this dataset

Watch for these; they are the recurring failure modes.

| Failure | What it looks like | Fix |
|---|---|---|
| **Scale confusion** | "Sonali Bank's 2015 ROE was 0.82%" when the sheet stores a fraction | insist on `value_pct_points` or the `v_*_year` views |
| **Zero-filling** | a chart where Krishi Bank's assets are 0 from 1973 to 2009 | NULL ≠ 0; the years are simply absent |
| **Quoting the duplicates** | Mutual Trust Bank's 2018 total assets reported confidently | check `data_quality_log` first |
| **ROE on negative equity** | "Krishi Bank's ROE rose to 34% in 2024" — in a year of a Tk 65 bn loss | rule 4: ROE is meaningless when equity < 0; use NPAT and equity |
| **Pooling the segments** | one average across CB and SOCB banks presented as "the sector" | the segments come from different workbooks and eras; compare, don't pool |
| **Double-counting Eastern Bank** | its figures appearing twice in a sum | filter `table_instance = 1`, or use the views |
| **Mixing solo and group** | comparing a "CRAR % (Group)" to a solo CRAR | check `metric_catalog.raw_labels` |
| **Inventing a metric** | using a ratio the dataset does not contain | `SELECT metric_std FROM metric_catalog` is the complete list |
| **Treating 2026 as a forecast** | it is a placeholder column, mostly empty | ignore unless populated |

---

## 6. If you are building an AI product on this

* Ship `docs/SCHEMA.md` and the section-3 primer as part of your system prompt.
  They are written to be machine-readable.
* Expose `data_quality_log` to the model rather than filtering it out. A model
  that can say "this figure is disputed, here is why" is more useful than one
  that quietly returns a wrong number.
* Prefer the `v_cb_year` / `v_socb_year` views for retrieval. They are small, comparable
  across banks, and remove the mistakes models make most often.
* The database is read-only by design. `dyingcyrus.py` opens it with
  `mode=ro`, so an agent cannot corrupt it.
