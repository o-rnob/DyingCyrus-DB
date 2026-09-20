-- =====================================================================
-- DyingCyrus-DB v3 — copy-paste query cookbook
-- Run in DB Browser for SQLite, sqlite3, DBeaver, or any SQL client.
--
-- Two segments, two sets of tables:
--   CB   = commercial banks       -> financials_cb   raw_cb   v_cb_year
--   SOCB = state-owned/specialised-> financials_socb raw_socb v_socb_year
-- v_all_year stacks them; use it only when you mean to.
-- =====================================================================

-- 0. What am I holding?
SELECT * FROM build_metadata;
SELECT bank_id, display_name, bank_type, year_min, year_max FROM banks ORDER BY bank_type, display_name;
SELECT segment, metric_std, canonical_unit, n_banks, n_values FROM metric_catalog ORDER BY segment, metric_std;


-- 1. How complete is each bank? (core 5 = assets, loans, deposits, equity, NPAT)
--    core5_pct is measured inside the bank's compiled range; core5_pct_sheet
--    counts every year column on the sheet, including years before data begins.
SELECT segment, bank_id, compiled_first, compiled_last, core5_pct, core5_pct_sheet, core5_years_full
FROM bank_coverage ORDER BY segment, core5_pct DESC;


-- 2. One commercial bank, one metric, over time.
SELECT year, value_numeric
FROM financials_cb
WHERE bank_id = 'city_bank_plc' AND metric_std = 'total_assets' AND table_instance = 1
ORDER BY year;


-- 3. A ratio over time. Use value_pct_points, NOT value_numeric — banks store
--    17.3 and 0.173 for the same thing.
SELECT year, value_pct_points AS roe_pct
FROM financials_socb
WHERE bank_id = 'sonali_bank' AND metric_std = 'roe_pct' AND table_instance = 1
  AND value_pct_points IS NOT NULL
ORDER BY year;


-- 4. THE TRAP: ROE on negative equity. Krishi Bank's equity has been negative
--    since 2010, so its losses print as POSITIVE ROE. Never rank on these.
SELECT year, equity_tk_mn, npat_tk_mn, roe_pct AS printed_roe_pct
FROM v_socb_year
WHERE bank_id = 'bangladesh_krishi_bank_bkb' AND equity_tk_mn IS NOT NULL
ORDER BY year;

-- ...and every bank-year where it happens, across both segments:
SELECT segment, display_name, year, equity_tk_mn, roe_pct
FROM v_all_year
WHERE equity_tk_mn < 0 AND roe_pct IS NOT NULL
ORDER BY display_name, year;


-- 5. League table, commercial banks, 2025.
SELECT display_name, total_assets_tk_mn
FROM v_cb_year
WHERE year = 2025 AND total_assets_tk_mn IS NOT NULL
ORDER BY total_assets_tk_mn DESC;


-- 6. League table, state-owned banks, 2024.
SELECT display_name, total_assets_tk_mn, deposits_tk_mn, equity_tk_mn
FROM v_socb_year
WHERE year = 2024 AND total_assets_tk_mn IS NOT NULL
ORDER BY total_assets_tk_mn DESC;


-- 7. State-owned vs commercial on asset quality (this is a deliberate stack).
SELECT segment, year, ROUND(AVG(npl_pct), 2) AS avg_npl_pct, COUNT(*) AS n_banks
FROM v_all_year
WHERE npl_pct IS NOT NULL AND year BETWEEN 2015 AND 2025
GROUP BY segment, year
ORDER BY year, segment;


-- 8. Fifty years of one state-owned bank: Sonali deposits since 1972.
SELECT year, deposits_tk_mn, total_assets_tk_mn, equity_tk_mn, npat_tk_mn
FROM v_socb_year
WHERE bank_id = 'sonali_bank'
ORDER BY year;


-- 9. Before you quote anything: what is known to be wrong with this bank?
SELECT severity, issue, metric, year, detail
FROM data_quality_log
WHERE bank_id = 'mutual_trust_bank_plc'
ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, year;


-- 10. The compiler's own sourcing notes (SOCB sheets carry detailed ones).
SELECT note_index, note_text FROM source_notes
WHERE bank_id = 'rupali_bank_plc' ORDER BY note_index;


-- 11. Defensible subset: commercial-bank panel minus every bank-year with a
--     critical flag.
SELECT v.*
FROM v_cb_year v
WHERE NOT EXISTS (
    SELECT 1 FROM data_quality_log q
    WHERE q.bank_id = v.bank_id AND q.year = v.year AND q.severity = 'critical'
);


-- 12. Trace one number back to the exact cell it came from (harmonised layer)...
SELECT source_file, source_row, source_col, raw_value, value_numeric, value_source
FROM financials_socb
WHERE bank_id = 'rupali_bank_plc' AND metric_std = 'npl_amount' AND year = 2024
  AND table_instance = 1;

-- ...and look at that row in the RAW layer, untouched (replace 20 with source_row).
SELECT source_col, cell_text, cell_type
FROM raw_socb
WHERE bank_id = 'rupali_bank_plc' AND source_row = 20
ORDER BY col_index;


-- 13. Everything the raw layer holds for one bank, as it appears on the sheet.
SELECT source_row, source_col, cell_text FROM raw_cb
WHERE bank_id = 'city_bank_plc' ORDER BY source_row, col_index LIMIT 60;


-- 14. Growth: CAGR of deposits 2015 -> 2025, commercial banks.
WITH a AS (SELECT bank_id, deposits_tk_mn d0 FROM v_cb_year WHERE year = 2015),
     b AS (SELECT bank_id, deposits_tk_mn d1 FROM v_cb_year WHERE year = 2025)
SELECT bk.display_name,
       ROUND((POWER(b.d1 / a.d0, 1.0 / 10) - 1) * 100, 2) AS deposit_cagr_pct
FROM a JOIN b USING (bank_id) JOIN banks bk USING (bank_id)
WHERE a.d0 > 0 AND b.d1 > 0
ORDER BY deposit_cagr_pct DESC;
-- (SQLite needs POWER(): if your build lacks it, use EXP(LN(x)/10).)


-- 15. Which figures are estimates rather than as-reported?
SELECT bank_id, metric, metric_std FROM financials_socb WHERE is_estimated = 1
UNION
SELECT bank_id, metric, metric_std FROM financials_cb   WHERE is_estimated = 1;


-- 16. The duplicated table on the Eastern Bank sheet (instance 2 is NOT
--     authoritative; the v_* views hide it on purpose).
SELECT table_instance, metric, year, value_numeric, source_row
FROM financials_cb
WHERE bank_id = 'eastern_bank_plc' AND metric_std = 'yoy_npat_growth_pct'
ORDER BY table_instance, source_row, year;
