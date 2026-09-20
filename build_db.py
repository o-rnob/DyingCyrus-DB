#!/usr/bin/env python3
"""
build_db.py — DyingCyrus-DB ETL
================================

Reads the two source workbooks in data/raw/ and writes:

  * dyingcyrus.db          SQLite database (the deliverable)
  * data/csv/*.csv         shared reference tables (banks, notes, log, coverage)
  * data/csv/cb/           commercial-bank segment: long, bank_year, per_bank/, raw/
  * data/csv/socb/         state-owned-bank segment: long, bank_year, per_bank/, raw/
  * data/json/*.json       JSON exports (for JS / notebooks / LLM tooling)

The two segments (CB = commercial banks, SOCB = state-owned & specialised banks)
are kept physically separate: financials_cb / financials_socb, raw_cb / raw_socb,
v_cb_year / v_socb_year. v_all_year exists only for deliberately stacking them.

Every non-empty source cell is also stored untouched in raw_cb / raw_socb (and as
a cell-for-cell CSV per bank), so nothing is lossy: the harmonised layer sits on
top of a verbatim copy of the workbooks.

Design rule (unchanged since KnightBase-DB):

    Every skip, every conflict, every rename and every known data-quality
    issue is LOGGED and QUERYABLE. Nothing is silently fixed, rescaled or
    guessed at. `raw_value` always preserves the original cell exactly.

Run:  python3 build_db.py
"""

from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone

try:
    import openpyxl
except ImportError:  # pragma: no cover
    sys.exit("openpyxl is required:  pip install -r requirements.txt")

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

BUILD_VERSION = "3.0.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "data", "raw")
CSV_DIR = os.path.join(ROOT, "data", "csv")
SEGMENTS = {"CB": "cb", "SOCB": "socb"}      # bank_type -> table/folder suffix
CORE_METRICS = ["total_assets", "loans_advances_gross", "total_deposits",
                "shareholders_equity", "net_profit_after_tax"]
JSON_DIR = os.path.join(ROOT, "data", "json")
DB_PATH = os.path.join(ROOT, "dyingcyrus.db")

SOURCES = [
    {
        "file": "DATASET_11_BANKS_2025-2015_.xlsx",
        "bank_type": "CB",
        "ownership": "Commercial bank (private, DSE-listed)",
    },
    {
        "file": "Dying_Cyrus_-_SOCB_V7__furnished_.xlsx",
        "bank_type": "SOCB",
        "ownership": "State-owned commercial / specialised bank",
    },
]

# Metric label harmonisation. The raw label is ALWAYS kept in `metric`;
# `metric_std` is the machine-friendly key you should join and filter on.
METRIC_STD = {
    "total assets": ("total_assets", "Tk mn", False),
    "loans & advances": ("loans_advances_gross", "Tk mn", False),
    "loans & advances, gross": ("loans_advances_gross", "Tk mn", False),
    "total deposits": ("total_deposits", "Tk mn", False),
    "shareholders' equity": ("shareholders_equity", "Tk mn", False),
    "net interest income": ("net_interest_income", "Tk mn", False),
    "non-interest income": ("non_interest_income", "Tk mn", False),
    "net profit after tax": ("net_profit_after_tax", "Tk mn", False),
    "profit before tax": ("profit_before_tax", "Tk mn", False),
    "provision maintained (loans & advances)": ("provision_maintained", "Tk mn", False),
    "eps": ("eps", "BDT", False),
    "eps (taka)": ("eps", "BDT", False),
    "roa %": ("roa_pct", "%", False),
    "roe %": ("roe_pct", "%", False),
    "npl % (gross)": ("npl_pct_gross", "%", False),
    "npl amount": ("npl_amount", "Tk mn", False),
    "estimated npl amount": ("npl_amount", "Tk mn", True),
    "estimated npl amount (npl% x loans)": ("npl_amount", "Tk mn", True),
    "provision coverage %": ("provision_coverage_pct", "%", False),
    "loan-deposit ratio %": ("loan_deposit_ratio_pct", "%", False),
    "capital adequacy ratio %": ("car_pct", "%", False),
    "crar %": ("car_pct", "%", False),
    "crar % (group)": ("car_pct", "%", False),
    "cost-to-income ratio %": ("cost_income_pct", "%", False),
    "cost-to-income ratio % (group)": ("cost_income_pct", "%", False),
    "npl / total assets %": ("npl_to_assets_pct", "%", False),
    "npl / total assets % (estimated)": ("npl_to_assets_pct", "%", True),
    "yoy npat growth %": ("yoy_npat_growth_pct", "%", False),
    "yoy total assets growth %": ("yoy_total_assets_growth_pct", "%", False),
    "yoy equity growth %": ("yoy_equity_growth_pct", "%", False),
}

# Metrics whose sensible range is roughly -100..100 percentage points, used to
# decide whether a "%" cell was stored as 0.173 or as 17.3. Growth metrics are
# excluded: a 700% growth year is real, so their scale cannot be inferred.
RATIO_METRICS = {
    "roa_pct", "roe_pct", "npl_pct_gross", "provision_coverage_pct",
    "loan_deposit_ratio_pct", "car_pct", "cost_income_pct", "npl_to_assets_pct",
}
GROWTH_METRICS = {
    "yoy_npat_growth_pct", "yoy_total_assets_growth_pct", "yoy_equity_growth_pct",
}

# Plausibility bounds (percentage points) used only to RAISE A FLAG, never to
# alter a value. A breach usually means a real distressed bank, not a typo.
PLAUSIBLE_BOUNDS = {
    "roa_pct": (-25, 25),
    "roe_pct": (-300, 300),
    "npl_pct_gross": (0, 100),
    "provision_coverage_pct": (0, 400),
    "loan_deposit_ratio_pct": (0, 200),
    "car_pct": (-200, 100),
    "cost_income_pct": (-500, 500),
    "npl_to_assets_pct": (0, 100),
}

YEAR_MIN, YEAR_MAX = 1900, 2100

# The source sheets spell a few names loosely or with typos. The workbook's own
# text is kept in banks.sheet_title; display_name uses the corrected legal name
# and every correction is written to the quality log.
DISPLAY_NAME_FIXES = {
    "brac bank ltd": "BRAC Bank PLC",
    "dutch banlga bank ltd": "Dutch-Bangla Bank PLC",
    "mtb-": "Mutual Trust Bank PLC",
    "south east bank plc": "Southeast Bank PLC",
    "eastern bank plc": "Eastern Bank PLC",
    "bank asia plc": "Bank Asia PLC",
}

log_rows: list[dict] = []
marker_counts: dict = defaultdict(int)


def log(issue, detail, severity, bank_id=None, metric=None, year=None):
    log_rows.append({
        "bank_id": bank_id, "metric": metric, "year": year,
        "issue": issue, "detail": detail, "severity": severity,
    })


# --------------------------------------------------------------------------
# Cell parsing
# --------------------------------------------------------------------------

# Tokens the compiler used to mean "no figure here". They are recorded as
# missing_marker (not as parse failures) and are never zero-filled.
MISSING_MARKER_RE = re.compile(
    r"^(n\.?/?a\.?|na|n/?m|nil|not available|not applicable|[-–—]{1,2})[\s*†⁴‡0-9]*$",
    re.IGNORECASE)
NUM_RE = re.compile(r"-?[\d,]*\.?\d+")


def parse_cell(value):
    """Return (value_numeric, value_source). Never raises, never guesses."""
    if value is None:
        return None, "missing"
    if isinstance(value, bool):
        return None, "unrecoverable_text"
    if isinstance(value, (int, float)):
        return float(value), "native_numeric"

    text = str(value).strip()
    if not text:
        return None, "missing"
    if MISSING_MARKER_RE.match(text):
        return None, "missing_marker"

    # Normalise unicode minus / parenthesised negatives before matching.
    cleaned = text.replace("\u2212", "-").replace("\u2013", "-")
    negative = cleaned.startswith("(") and cleaned.rstrip("*†⁴ ").endswith(")")
    match = NUM_RE.search(cleaned)
    if not match:
        return None, "unrecoverable_text"
    try:
        num = float(match.group(0).replace(",", ""))
    except ValueError:
        return None, "unrecoverable_text"
    if negative:
        num = -num
    return num, "recovered_from_text"


def col_letter(idx):
    return openpyxl.utils.get_column_letter(idx)


def is_year(value):
    try:
        year = int(float(value))
    except (TypeError, ValueError):
        return None
    return year if YEAR_MIN <= year <= YEAR_MAX else None


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return re.sub(r"_+", "_", slug)


# --------------------------------------------------------------------------
# Sheet parsing
# --------------------------------------------------------------------------

def sheet_rows(ws):
    """Materialise the used range once; openpyxl max_row over-reports badly."""
    grid = {}
    last_row = 0
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None and str(cell.value).strip() != "":
                grid[(cell.row, cell.column)] = cell.value
                last_row = max(last_row, cell.row)
    return grid, last_row


def find_display_name(grid, last_row):
    for r in range(1, min(6, last_row) + 1):
        for c in (1, 2, 3):
            v = grid.get((r, c))
            if isinstance(v, str) and "—" in v and "Dataset" in v:
                return v.split("—")[0].strip(), v.strip()
    for r in range(1, min(6, last_row) + 1):
        for c in (1, 2):
            v = grid.get((r, c))
            if isinstance(v, str) and len(v) > 4:
                return v.strip(), v.strip()
    return None, None


def parse_sheet(ws, bank_id, source_file):
    """Return (financial rows, summary stats, notes, table count)."""
    grid, last_row = sheet_rows(ws)
    max_col = max((c for (_, c) in grid), default=1)

    # --- locate every "Metric | Unit" header row on the sheet ---------------
    headers = []
    for r in range(1, last_row + 1):
        a = grid.get((r, 1))
        if isinstance(a, str) and a.strip().lower() == "metric":
            years = {}
            for c in range(2, max_col + 1):
                y = is_year(grid.get((r, c)))
                if y is not None:
                    years[c] = y
            if years:
                headers.append((r, years))
    if not headers:
        log("sheet_not_parsed", f"No 'Metric' header row found on sheet '{ws.title}'.",
            "critical", bank_id)
        return [], [], [], 0

    # --- summary block: labelled rows above the first header ---------------
    summary = []
    for r in range(1, headers[0][0]):
        label = grid.get((r, 2)) or grid.get((r, 1))
        if not isinstance(label, str) or len(label) < 4:
            continue
        if "dataset" in label.lower() or label.strip().lower().startswith("summ"):
            continue
        val = None
        for c in range(3, max_col + 1):
            if (r, c) in grid:
                val = grid[(r, c)]
                break
        num, src = parse_cell(val)
        if num is None and src != "native_numeric":
            continue
        summary.append({"bank_id": bank_id, "stat_name": label.strip(),
                        "value": num, "source_row": r})

    financials, notes = [], []
    first_year_col = min(headers[0][1])

    for instance, (hrow, years) in enumerate(headers, start=1):
        end = headers[instance][0] - 1 if instance < len(headers) else last_row
        category = None
        for r in range(hrow + 1, end + 1):
            label = grid.get((r, 1))
            if not isinstance(label, str):
                continue
            label = label.strip()
            if not label:
                continue

            unit_cell = grid.get((r, 2))
            row_year_cells = {c: grid.get((r, c)) for c in years if (r, c) in grid}

            # (a) free-text source note: long prose, nothing in the year columns
            if not row_year_cells and (len(label) > 60 or label.lower().startswith("source")):
                notes.append({"bank_id": bank_id, "note_index": len(notes) + 1,
                              "note_text": label, "source_row": r})
                continue

            # (b) section header: no unit and not one parseable number on the row
            if unit_cell is None and not any(
                    parse_cell(v)[0] is not None for v in row_year_cells.values()):
                category = label
                continue

            # (c) shifted/rescaled duplicate: the Unit column holds a number
            shift = 0
            if isinstance(unit_cell, (int, float)):
                shift = 1
                log("misaligned_duplicate_row",
                    f"Row {r} on sheet '{ws.title}' carries data in the Unit column "
                    f"(B{r}={unit_cell!r}), i.e. the whole row is shifted one column "
                    f"left relative to the header. Loaded with the shift corrected and "
                    f"marked table_instance={instance}; values also appear rescaled "
                    f"(divided by 100) versus the aligned copy of the same metric.",
                    "critical", bank_id, label)
                unit = None
            else:
                unit = str(unit_cell).strip() if unit_cell is not None else None

            std, std_unit, estimated = METRIC_STD.get(
                label.lower(), (slugify(label), unit, False))
            if label.lower() not in METRIC_STD:
                log("unmapped_metric_label",
                    f"Metric '{label}' (row {r}, sheet '{ws.title}') has no entry in "
                    f"METRIC_STD; metric_std was auto-slugged to '{std}'. Cross-bank "
                    f"comparison on this metric is not guaranteed.",
                    "warning", bank_id, label)

            for col, year in years.items():
                src_col = col - shift
                raw = grid.get((r, src_col)) if shift else grid.get((r, col))
                num, vsrc = parse_cell(raw)

                if vsrc == "missing_marker":
                    marker_counts[(bank_id, str(raw).strip())] += 1
                elif vsrc == "recovered_from_text":
                    log("text_cell_with_recoverable_number",
                        f"{col_letter(src_col)}{r} held {raw!r}; a number was recovered "
                        f"({num}) but the original text is kept in raw_value.",
                        "info", bank_id, label, year)
                elif vsrc == "unrecoverable_text":
                    log("unrecoverable_text_cell",
                        f"{col_letter(src_col)}{r} held {raw!r}, which could not be parsed "
                        f"as a number. Stored as NULL; original text kept in raw_value.",
                        "warning", bank_id, label, year)

                financials.append({
                    "bank_id": bank_id, "table_instance": instance,
                    "category": category, "metric": label, "metric_std": std,
                    "unit": unit, "year": year,
                    "raw_value": None if raw is None else str(raw),
                    "value_numeric": num, "value_pct_points": None,
                    "pct_scale": None, "value_source": vsrc,
                    "is_estimated": int(estimated),
                    "source_file": source_file, "source_row": r,
                    "source_col": col_letter(src_col),
                })

    if len(headers) > 1:
        log("duplicate_table_on_sheet",
            f"Sheet '{ws.title}' contains the Metric/Unit table {len(headers)} times "
            f"(header rows {', '.join(str(h[0]) for h in headers)}). All copies are "
            f"loaded; table_instance = 1 is the authoritative one and is the only "
            f"instance exposed by the v_* views.",
            "critical", bank_id)

    _ = first_year_col
    return financials, summary, notes, len(headers)


# --------------------------------------------------------------------------
# Post-load quality checks
# --------------------------------------------------------------------------

def detect_percent_scale(financials, banks):
    """Decide, per bank and metric, whether a "%" cell holds 17.3 or 0.173.

    Magnitude alone cannot answer this: a real ROA of 0.79% and a fractional ROE
    of 0.79 (= 79%) look identical. So wherever the ratio can be rebuilt from
    two other rows on the same sheet (ROA from NPAT/assets, ROE from
    NPAT/equity, LDR from loans/deposits, NPL% from NPL amount/loans, NPL/assets
    from NPL amount/assets), the stored figure is scored against both
    conventions and the better-fitting one wins. Metrics with no rebuildable
    definition (CAR, provision coverage, cost-to-income) inherit the convention
    the rest of that bank's sheet uses, and that inheritance is logged.

    `value_numeric` is never touched. The verdict lands in `pct_scale`, and
    `value_pct_points` restates the figure in percentage points so cross-bank
    queries are safe.
    """
    # index: (bank, instance, metric_std, year) -> value
    idx = {}
    for r in financials:
        if r["value_numeric"] is not None:
            idx[(r["bank_id"], r["table_instance"], r["metric_std"], r["year"])] = \
                r["value_numeric"]

    DERIVABLE = {
        "roa_pct": ("net_profit_after_tax", "total_assets"),
        "roe_pct": ("net_profit_after_tax", "shareholders_equity"),
        "loan_deposit_ratio_pct": ("loans_advances_gross", "total_deposits"),
        "npl_pct_gross": ("npl_amount", "loans_advances_gross"),
        "npl_to_assets_pct": ("npl_amount", "total_assets"),
    }

    series = defaultdict(list)
    for r in financials:
        if r["metric_std"] in RATIO_METRICS or r["metric_std"] in GROWTH_METRICS:
            series[(r["bank_id"], r["table_instance"], r["metric_std"])].append(r)

    verdicts = {}   # (bank, instance, metric_std) -> (scale, evidence)

    def score(rows, bank, inst, std):
        """Return (scale, evidence) from rebuilt values, or (None, reason)."""
        if std in DERIVABLE:
            num_std, den_std = DERIVABLE[std]
            err_frac = err_pts = 0.0
            n = 0
            for r in rows:
                v = r["value_numeric"]
                num = idx.get((bank, inst, num_std, r["year"]))
                den = idx.get((bank, inst, den_std, r["year"]))
                if v is None or num is None or not den:
                    continue
                truth = num / den                      # a pure fraction
                if abs(truth) < 1e-9:
                    continue
                err_frac += abs(v - truth) / abs(truth)
                err_pts += abs(v - truth * 100.0) / abs(truth * 100.0)
                n += 1
            if n >= 3:
                if err_frac < err_pts:
                    return "fraction", (f"rebuilt {num_std}/{den_std} over {n} years: "
                                        f"mean error {err_frac/n:.1%} as a fraction vs "
                                        f"{err_pts/n:.1%} as percentage points")
                return "percent_points", (f"rebuilt {num_std}/{den_std} over {n} years: "
                                          f"mean error {err_pts/n:.1%} as percentage "
                                          f"points vs {err_frac/n:.1%} as a fraction")
        if std in GROWTH_METRICS:
            vals = [abs(r["value_numeric"]) for r in rows if r["value_numeric"]]
            if vals:
                return ("fraction" if max(vals) <= 1.5 else "percent_points",
                        f"growth series peaks at {max(vals):.4g}")
        return None, "no rebuildable definition on this sheet"

    # pass 1 — metrics we can verify
    for key, rows in series.items():
        bank, inst, std = key
        scale, evidence = score(rows, bank, inst, std)
        if scale:
            verdicts[key] = (scale, evidence, "verified")

    # pass 2 — everything else inherits the bank's majority convention
    majority = defaultdict(lambda: defaultdict(int))
    for (bank, inst, std), (scale, _e, _k) in verdicts.items():
        if std in RATIO_METRICS:
            majority[(bank, inst)][scale] += 1
    for key, rows in series.items():
        if key in verdicts:
            continue
        bank, inst, std = key
        votes = majority.get((bank, inst))
        if votes:
            scale = max(votes, key=votes.get)
            verdicts[key] = (scale, f"inherited from this sheet's verified metrics "
                                    f"({dict(votes)})", "inferred")
        else:
            verdicts[key] = ("unknown", "no evidence available on this sheet", "unknown")

    # apply
    for key, rows in series.items():
        scale, evidence, kind = verdicts[key]
        bank, _inst, std = key
        tag = scale if kind != "inferred" else f"{scale}_inferred"
        for r in rows:
            r["pct_scale"] = tag
            if r["value_numeric"] is None:
                continue
            r["value_pct_points"] = (r["value_numeric"] * 100.0
                                     if scale == "fraction" else r["value_numeric"])
        if scale == "fraction":
            sample = next((r["value_numeric"] for r in rows
                           if r["value_numeric"] is not None), None)
            log("percent_stored_as_fraction",
                f"{banks[bank]['display_name']} stores '{std}' as a decimal fraction "
                f"(e.g. {sample!r}) although the Unit column says '%'. Evidence: "
                f"{evidence}. value_numeric keeps the source figure untouched; "
                f"value_pct_points holds the same number x100 so it lines up with banks "
                f"that publish percentage points. Use value_pct_points, or the v_bank_year "
                f"view, for any cross-bank comparison.",
                "critical", bank, std)
        elif scale == "unknown":
            log("percent_scale_undetermined",
                f"{banks[bank]['display_name']} '{std}': the sheet gives no way to tell "
                f"whether these '%' figures are percentage points or fractions. "
                f"value_pct_points is left equal to value_numeric; verify against the "
                f"annual report before comparing this series with another bank.",
                "warning", bank, std)

    # %-unit rows outside the known metric sets still get a documented pass-through
    for row in financials:
        if row["pct_scale"] is None and (row["unit"] or "").strip() == "%":
            row["pct_scale"] = "assumed_percent_points"
            row["value_pct_points"] = row["value_numeric"]


def detect_cross_bank_duplicates(financials, banks):
    """Flag banks whose series are byte-identical to another bank's."""
    by_key = defaultdict(dict)  # (metric_std, year) -> {bank_id: value}
    for r in financials:
        if r["table_instance"] != 1 or r["value_numeric"] is None:
            continue
        by_key[(r["metric_std"], r["year"])][r["bank_id"]] = r["value_numeric"]

    pair_hits = defaultdict(list)
    for (std, year), mapping in by_key.items():
        inverse = defaultdict(list)
        for bank_id, val in mapping.items():
            if abs(val) > 1e-9:          # zeros collide innocently
                inverse[round(val, 6)].append(bank_id)
        for val, ids in inverse.items():
            if len(ids) > 1:
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        pair_hits[tuple(sorted((ids[i], ids[j])))].append((std, year, val))

    for (a, b), hits in pair_hits.items():
        if len(hits) < 5:                # isolated ties are coincidence
            continue
        years = sorted({y for _, y, _ in hits})
        metrics = sorted({m for m, _, _ in hits})
        for std, year, val in hits:
          for primary, other in ((a, b), (b, a)):
            log("cross_bank_identical_value",
                f"{banks[primary]['display_name']} and {banks[other]['display_name']} report the "
                f"identical figure {val!r} for '{std}' in {year}. This pair matches on "
                f"{len(hits)} (metric, year) cells across {len(metrics)} metrics and years "
                f"{years[0]}–{years[-1]} — not plausible for raw balance-sheet numbers, and "
                f"almost certainly a copy/paste error in the source workbook. Treat both "
                f"banks' figures for these years as UNVERIFIED until checked against the "
                f"published annual reports.",
                "critical", primary, std, year)


def detect_outliers(financials, banks):
    for r in financials:
        std = r["metric_std"]
        if std not in PLAUSIBLE_BOUNDS or r["value_pct_points"] is None:
            continue
        lo, hi = PLAUSIBLE_BOUNDS[std]
        v = r["value_pct_points"]
        if v < lo or v > hi:
            log("value_outside_plausible_range",
                f"{banks[r['bank_id']]['display_name']} '{r['metric']}' {r['year']} = "
                f"{v:.2f} percentage points, outside the sanity band [{lo}, {hi}]. Not "
                f"altered. For the state-owned banks these extremes are frequently REAL "
                f"(deeply negative capital, negative net interest income); check the "
                f"source_notes table for that bank before calling it an error.",
                "warning", r["bank_id"], r["metric"], r["year"])


def detect_ratio_mismatch(financials, banks):
    """Flag a reported ratio that its own inputs do not reproduce.

    Once the percentage convention is settled, ROA, ROE, the loan-deposit ratio
    and NPL% can each be rebuilt from two other rows on the same sheet. A large
    gap is usually a reporting-basis difference (average equity rather than
    closing equity, a different denominator, a group-versus-solo figure) rather
    than an error — but it is exactly the kind of thing you want to know about
    before quoting the number.
    """
    idx = {}
    for r in financials:
        if r["table_instance"] == 1 and r["value_numeric"] is not None:
            idx[(r["bank_id"], r["metric_std"], r["year"])] = r["value_numeric"]

    DERIVABLE = {
        "roa_pct": ("net_profit_after_tax", "total_assets"),
        "roe_pct": ("net_profit_after_tax", "shareholders_equity"),
        "loan_deposit_ratio_pct": ("loans_advances_gross", "total_deposits"),
        "npl_pct_gross": ("npl_amount", "loans_advances_gross"),
    }

    for r in financials:
        std = r["metric_std"]
        if (std not in DERIVABLE or r["table_instance"] != 1
                or r["value_pct_points"] is None or r["is_estimated"]):
            continue
        num_std, den_std = DERIVABLE[std]
        num = idx.get((r["bank_id"], num_std, r["year"]))
        den = idx.get((r["bank_id"], den_std, r["year"]))
        if num is None or not den:
            continue
        rebuilt = 100.0 * num / den
        if abs(rebuilt) < 0.5:           # near-zero denominators are noise
            continue
        gap = abs(r["value_pct_points"] - rebuilt) / abs(rebuilt)
        if gap > 0.5:
            log("reported_ratio_not_reproducible",
                f"{banks[r['bank_id']]['display_name']} reports '{r['metric']}' "
                f"{r['year']} as {r['value_pct_points']:.2f} percentage points, but "
                f"{num_std} / {den_std} on the same sheet rebuilds to {rebuilt:.2f} "
                f"({gap:.0%} apart). Nothing altered. Usually a reporting-basis "
                f"difference — average versus closing denominator, or a group figure "
                f"against solo inputs — rather than an error; check the bank's annual "
                f"report before quoting either version.",
                "warning", r["bank_id"], r["metric"], r["year"])


def detect_negative_equity_ratios(financials, banks):
    """ROE = profit / equity. With NEGATIVE equity a loss prints as a POSITIVE ROE
    (negative / negative), and a profit as a negative one. Flag every bank where
    that happens. Values are never altered."""
    eq, roe = {}, {}
    for r in financials:
        if r["table_instance"] != 1 or r["value_numeric"] is None:
            continue
        key = (r["bank_id"], r["year"])
        if r["metric_std"] == "shareholders_equity":
            eq[key] = r["value_numeric"]
        elif r["metric_std"] == "roe_pct":
            roe[key] = r["value_numeric"]
    by_bank = defaultdict(list)
    for (bank_id, year), e in eq.items():
        if e < 0 and (bank_id, year) in roe:
            by_bank[bank_id].append(year)
    for bank_id, years in sorted(by_bank.items()):
        years.sort()
        log("roe_on_negative_equity",
            f"{banks[bank_id]['display_name']} reports negative shareholders' equity in "
            f"{len(years)} year(s) ({years[0]}-{years[-1]}) for which an ROE is also "
            f"printed. ROE = profit / equity, so with negative equity a LOSS shows as a "
            f"POSITIVE ROE and a profit as a negative one. Those ROE figures are "
            f"arithmetically valid but economically meaningless: do not rank, average or "
            f"chart them as if higher were better. Use net profit and equity in Tk mn "
            f"instead.", "critical", bank_id, "roe_pct")


def detect_gaps(financials, banks):
    by_bank = defaultdict(lambda: defaultdict(int))
    for r in financials:
        if r["table_instance"] != 1:
            continue
        by_bank[r["bank_id"]][r["year"]] += (1 if r["value_numeric"] is None else 0)
    for bank_id, years in by_bank.items():
        total = defaultdict(int)
        for r in financials:
            if r["bank_id"] == bank_id and r["table_instance"] == 1:
                total[r["year"]] += 1
        empty = sorted(y for y, miss in years.items() if miss == total[y])
        if empty:
            log("empty_year_column",
                f"{banks[bank_id]['display_name']} has no data at all for "
                f"{len(empty)} year column(s): {', '.join(map(str, empty))}. These are "
                f"NULL, never zero.",
                "info", bank_id)


# --------------------------------------------------------------------------
# Database writing
# --------------------------------------------------------------------------

BASE_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE banks (
    bank_id       TEXT PRIMARY KEY,
    display_name  TEXT NOT NULL,
    sheet_name    TEXT NOT NULL,
    bank_type     TEXT NOT NULL,   -- 'CB' (commercial) | 'SOCB' (state-owned & specialised)
    ownership     TEXT,
    source_file   TEXT NOT NULL,
    sheet_title   TEXT,
    year_min      INTEGER,         -- first year with a numeric value
    year_max      INTEGER,         -- last year with a numeric value
    n_tables      INTEGER          -- >1 means the sheet repeats its data table
);

CREATE TABLE bank_summary_stats (
    bank_id    TEXT NOT NULL REFERENCES banks(bank_id),
    stat_name  TEXT NOT NULL,
    value      REAL,
    source_row INTEGER,
    PRIMARY KEY (bank_id, stat_name)
);

CREATE TABLE source_notes (
    bank_id    TEXT NOT NULL REFERENCES banks(bank_id),
    note_index INTEGER NOT NULL,
    note_text  TEXT NOT NULL,
    source_row INTEGER,
    PRIMARY KEY (bank_id, note_index)
);

CREATE TABLE data_quality_log (
    log_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_id  TEXT,
    metric   TEXT,
    year     INTEGER,
    issue    TEXT NOT NULL,
    detail   TEXT NOT NULL,
    severity TEXT NOT NULL     -- 'info' | 'warning' | 'critical'
);

-- Harmonised metric keys, per segment. Every raw label behind a key is listed.
CREATE TABLE metric_catalog (
    segment        TEXT NOT NULL,      -- 'CB' | 'SOCB'
    metric_std     TEXT NOT NULL,
    canonical_unit TEXT,
    n_banks        INTEGER,
    n_values       INTEGER,
    raw_labels     TEXT,
    PRIMARY KEY (segment, metric_std)
);

-- How complete is each bank? core5 = total assets, loans, deposits, equity, NPAT.
CREATE TABLE bank_coverage (
    bank_id            TEXT PRIMARY KEY REFERENCES banks(bank_id),
    segment            TEXT NOT NULL,
    year_first         INTEGER,        -- first year column on the sheet
    year_last          INTEGER,        -- last year column on the sheet
    years_on_sheet     INTEGER,
    compiled_first     INTEGER,        -- first year with any core-5 figure
    compiled_last      INTEGER,        -- last year with any core-5 figure
    compiled_years     INTEGER,
    core5_expected     INTEGER,        -- 5 metrics x compiled_years
    core5_filled       INTEGER,
    core5_pct          REAL,           -- HEADLINE: completeness inside the compiled range
    core5_pct_sheet    REAL,           -- same, but over every year column on the sheet
    all_cells          INTEGER,        -- authoritative-table cells (all metrics)
    all_filled         INTEGER,
    all_pct            REAL,
    core5_years_full   INTEGER,        -- years where all five core metrics exist
    first_core5_full   INTEGER,
    last_core5_full    INTEGER
);

CREATE TABLE build_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX idx_log_bank ON data_quality_log(bank_id, severity);
"""

# One copy of these per segment (suffix = cb / socb). Nothing is shared or filtered:
# the two segments live in physically separate tables.
SEGMENT_SCHEMA = """
-- Harmonised layer (metric_std, unit, percent scale...). table_instance = 1 is
-- the authoritative copy of a sheet's data table.
CREATE TABLE financials_{s} (
    bank_id          TEXT NOT NULL REFERENCES banks(bank_id),
    table_instance   INTEGER NOT NULL,
    category         TEXT,
    metric           TEXT NOT NULL,   -- raw label, exactly as printed
    metric_std       TEXT NOT NULL,   -- harmonised key: join/filter on this
    unit             TEXT,
    year             INTEGER NOT NULL,
    raw_value        TEXT,            -- original cell, stringified, always kept
    value_numeric    REAL,            -- parsed number, or NULL
    value_pct_points REAL,            -- % metrics restated in percentage points
    pct_scale        TEXT,            -- 'percent_points' | 'fraction' | ..._inferred
    value_source     TEXT NOT NULL,   -- native_numeric|recovered_from_text|...
    is_estimated     INTEGER NOT NULL DEFAULT 0,
    source_file      TEXT NOT NULL,
    source_row       INTEGER,
    source_col       TEXT,
    PRIMARY KEY (bank_id, table_instance, metric, source_row, year)
);
CREATE INDEX idx_fin_{s}_bank_year ON financials_{s}(bank_id, year);
CREATE INDEX idx_fin_{s}_std       ON financials_{s}(metric_std, year);

-- Raw layer: every NON-EMPTY cell of the source sheet, exactly as read. No metric
-- mapping, no unit fixing, no percent detection, no year parsing.
CREATE TABLE raw_{s} (
    bank_id     TEXT NOT NULL REFERENCES banks(bank_id),
    sheet_name  TEXT NOT NULL,
    source_row  INTEGER NOT NULL,
    col_index   INTEGER NOT NULL,     -- 1 = column A
    source_col  TEXT NOT NULL,        -- 'A', 'B', ...
    cell_text   TEXT NOT NULL,        -- the value, stringified without alteration
    cell_type   TEXT NOT NULL,        -- Python type openpyxl returned: str/int/float/...
    PRIMARY KEY (bank_id, source_row, col_index)
);

-- Authoritative rows only: instance 1, blanks dropped.
CREATE VIEW v_{s}_financials AS
SELECT f.bank_id, b.display_name, b.bank_type, f.category, f.metric, f.metric_std,
       f.unit, f.year, f.value_numeric, f.value_pct_points, f.pct_scale,
       f.is_estimated, f.raw_value
FROM financials_{s} f JOIN banks b ON b.bank_id = f.bank_id
WHERE f.table_instance = 1 AND f.value_numeric IS NOT NULL;

-- One row per bank-year, core metrics as columns. Ratios are in percentage points.
CREATE VIEW v_{s}_year AS
SELECT b.bank_id, b.display_name, b.bank_type, f.year,
  MAX(CASE WHEN f.metric_std='total_assets'           THEN f.value_numeric END) AS total_assets_tk_mn,
  MAX(CASE WHEN f.metric_std='loans_advances_gross'   THEN f.value_numeric END) AS loans_tk_mn,
  MAX(CASE WHEN f.metric_std='total_deposits'         THEN f.value_numeric END) AS deposits_tk_mn,
  MAX(CASE WHEN f.metric_std='shareholders_equity'    THEN f.value_numeric END) AS equity_tk_mn,
  MAX(CASE WHEN f.metric_std='net_interest_income'    THEN f.value_numeric END) AS nii_tk_mn,
  MAX(CASE WHEN f.metric_std='non_interest_income'    THEN f.value_numeric END) AS non_interest_income_tk_mn,
  MAX(CASE WHEN f.metric_std='net_profit_after_tax'   THEN f.value_numeric END) AS npat_tk_mn,
  MAX(CASE WHEN f.metric_std='npl_amount'             THEN f.value_numeric END) AS npl_amount_tk_mn,
  MAX(CASE WHEN f.metric_std='eps'                    THEN f.value_numeric END) AS eps_bdt,
  MAX(CASE WHEN f.metric_std='roa_pct'                THEN f.value_pct_points END) AS roa_pct,
  MAX(CASE WHEN f.metric_std='roe_pct'                THEN f.value_pct_points END) AS roe_pct,
  MAX(CASE WHEN f.metric_std='npl_pct_gross'          THEN f.value_pct_points END) AS npl_pct,
  MAX(CASE WHEN f.metric_std='provision_coverage_pct' THEN f.value_pct_points END) AS provision_coverage_pct,
  MAX(CASE WHEN f.metric_std='loan_deposit_ratio_pct' THEN f.value_pct_points END) AS loan_deposit_pct,
  MAX(CASE WHEN f.metric_std='car_pct'                THEN f.value_pct_points END) AS car_pct,
  MAX(CASE WHEN f.metric_std='cost_income_pct'        THEN f.value_pct_points END) AS cost_income_pct
FROM financials_{s} f JOIN banks b ON b.bank_id = f.bank_id
WHERE f.table_instance = 1
GROUP BY b.bank_id, f.year;
"""

CROSS_SCHEMA = """
-- Deliberate stacking of both segments. Use only when you WANT them together
-- (and remember the segments are compiled from different sources).
CREATE VIEW v_all_year AS
SELECT 'CB' AS segment, * FROM v_cb_year
UNION ALL
SELECT 'SOCB' AS segment, * FROM v_socb_year;

-- Every bank-year that carries at least one critical warning.
CREATE VIEW v_flagged AS
SELECT DISTINCT bank_id, year, issue FROM data_quality_log
WHERE severity = 'critical' AND bank_id IS NOT NULL;
"""


def _cell_text(value):
    """Stringify a raw cell without altering it (repr keeps full float precision)."""
    return repr(value) if isinstance(value, float) else str(value)


def compute_coverage(banks, financials):
    """Per-bank completeness, measured on the authoritative table only."""
    by_bank = defaultdict(list)
    for r in financials:
        if r["table_instance"] == 1:
            by_bank[r["bank_id"]].append(r)
    out = []
    for bank_id, rows in by_bank.items():
        years = sorted({r["year"] for r in rows})
        yfirst, ylast = years[0], years[-1]
        span = ylast - yfirst + 1
        core = defaultdict(set)
        for r in rows:
            if r["metric_std"] in CORE_METRICS and r["value_numeric"] is not None:
                core[r["metric_std"]].add(r["year"])
        filled = sum(len(v) for v in core.values())
        core_years = sorted(set().union(*core.values())) if core else []
        cfirst, clast = (core_years[0], core_years[-1]) if core_years else (yfirst, ylast)
        cspan = clast - cfirst + 1
        full_years = sorted(y for y in years
                            if all(y in core[m] for m in CORE_METRICS))
        allf = sum(1 for r in rows if r["value_numeric"] is not None)
        expected = len(CORE_METRICS) * cspan
        out.append({
            "bank_id": bank_id, "segment": banks[bank_id]["bank_type"],
            "year_first": yfirst, "year_last": ylast, "years_on_sheet": span,
            "compiled_first": cfirst, "compiled_last": clast, "compiled_years": cspan,
            "core5_expected": expected, "core5_filled": filled,
            "core5_pct": round(100.0 * filled / expected, 1),
            "core5_pct_sheet": round(100.0 * filled / (len(CORE_METRICS) * span), 1),
            "all_cells": len(rows), "all_filled": allf,
            "all_pct": round(100.0 * allf / len(rows), 1),
            "core5_years_full": len(full_years),
            "first_core5_full": full_years[0] if full_years else None,
            "last_core5_full": full_years[-1] if full_years else None,
        })
    return out


def write_db(banks, financials, summaries, notes, raw_cells):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    script = BASE_SCHEMA
    for seg in SEGMENTS.values():
        script += SEGMENT_SCHEMA.format(s=seg)
    script += CROSS_SCHEMA
    conn.executescript(script)

    conn.executemany(
        "INSERT INTO banks VALUES (:bank_id,:display_name,:sheet_name,:bank_type,"
        ":ownership,:source_file,:sheet_title,:year_min,:year_max,:n_tables)",
        list(banks.values()))

    for btype, seg in SEGMENTS.items():
        rows = [r for r in financials if banks[r["bank_id"]]["bank_type"] == btype]
        conn.executemany(
            f"INSERT INTO financials_{seg} VALUES (:bank_id,:table_instance,:category,"
            ":metric,:metric_std,:unit,:year,:raw_value,:value_numeric,"
            ":value_pct_points,:pct_scale,:value_source,:is_estimated,:source_file,"
            ":source_row,:source_col)", rows)
        conn.executemany(
            f"INSERT INTO raw_{seg} VALUES (:bank_id,:sheet_name,:source_row,"
            ":col_index,:source_col,:cell_text,:cell_type)",
            [c for c in raw_cells if banks[c["bank_id"]]["bank_type"] == btype])

        catalog = defaultdict(lambda: {"banks": set(), "n": 0, "labels": set(), "unit": None})
        for r in rows:
            e = catalog[r["metric_std"]]
            e["banks"].add(r["bank_id"])
            e["labels"].add(r["metric"])
            e["unit"] = e["unit"] or r["unit"]
            if r["value_numeric"] is not None:
                e["n"] += 1
        conn.executemany("INSERT INTO metric_catalog VALUES (?,?,?,?,?,?)", [
            (btype, std, e["unit"], len(e["banks"]), e["n"], " | ".join(sorted(e["labels"])))
            for std, e in sorted(catalog.items())])

    conn.executemany(
        "INSERT OR IGNORE INTO bank_summary_stats VALUES (:bank_id,:stat_name,:value,:source_row)",
        summaries)
    conn.executemany(
        "INSERT INTO source_notes VALUES (:bank_id,:note_index,:note_text,:source_row)", notes)
    conn.executemany(
        "INSERT INTO data_quality_log (bank_id,metric,year,issue,detail,severity) "
        "VALUES (:bank_id,:metric,:year,:issue,:detail,:severity)", log_rows)
    conn.executemany(
        "INSERT INTO bank_coverage VALUES (:bank_id,:segment,:year_first,:year_last,"
        ":years_on_sheet,:compiled_first,:compiled_last,:compiled_years,:core5_expected,"
        ":core5_filled,:core5_pct,:core5_pct_sheet,:all_cells,:all_filled,"
        ":all_pct,:core5_years_full,:first_core5_full,:last_core5_full)",
        compute_coverage(banks, financials))

    n_cb = sum(1 for b in banks.values() if b["bank_type"] == "CB")
    conn.executemany("INSERT INTO build_metadata VALUES (?,?)", [
        ("build_version", BUILD_VERSION),
        ("built_at_utc", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        ("python", sys.version.split()[0]),
        ("source_files", "; ".join(s["file"] for s in SOURCES)),
        ("n_banks", str(len(banks))),
        ("n_banks_cb", str(n_cb)),
        ("n_banks_socb", str(len(banks) - n_cb)),
        ("n_financial_rows", str(len(financials))),
        ("n_raw_cells", str(len(raw_cells))),
        ("n_log_entries", str(len(log_rows))),
        ("license_code", "MIT"),
        ("license_data", "CC0-1.0"),
    ])
    conn.commit()
    return conn


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------

def dump_csv(conn, query, path, params=()):
    cur = conn.execute(query, params)
    cols = [d[0] for d in cur.description]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(cols)
        writer.writerows(cur.fetchall())


def export_all(conn):
    os.makedirs(CSV_DIR, exist_ok=True)
    os.makedirs(JSON_DIR, exist_ok=True)

    # shared reference tables
    for name, order in [("banks", "bank_type, bank_id"),
                        ("bank_coverage", "segment, bank_id"),
                        ("bank_summary_stats", "bank_id, source_row"),
                        ("source_notes", "bank_id, note_index"),
                        ("metric_catalog", "segment, metric_std"),
                        ("data_quality_log", "severity, bank_id, year")]:
        dump_csv(conn, f"SELECT * FROM {name} ORDER BY {order}",
                 os.path.join(CSV_DIR, f"{name}.csv"))

    # per-segment exports
    for btype, seg in SEGMENTS.items():
        sdir = os.path.join(CSV_DIR, seg)
        for sub in ("per_bank", "raw"):
            os.makedirs(os.path.join(sdir, sub), exist_ok=True)

        dump_csv(conn, f"SELECT * FROM financials_{seg} "
                       "ORDER BY bank_id, table_instance, source_row, year",
                 os.path.join(sdir, f"{seg}_long.csv"))
        dump_csv(conn, f"SELECT * FROM v_{seg}_year ORDER BY bank_id, year",
                 os.path.join(sdir, f"{seg}_bank_year.csv"))

        for (bank_id,) in conn.execute(
                "SELECT bank_id FROM banks WHERE bank_type=? ORDER BY bank_id", (btype,)):
            # wide, harmonised-layer view of the authoritative table
            years = [y for (y,) in conn.execute(
                f"SELECT DISTINCT year FROM financials_{seg} WHERE bank_id=? "
                "AND table_instance=1 ORDER BY year", (bank_id,))]
            wide, order = {}, []
            for metric, unit, year, val, raw in conn.execute(
                    f"SELECT metric, unit, year, value_numeric, raw_value FROM financials_{seg} "
                    "WHERE bank_id=? AND table_instance=1 ORDER BY source_row, year", (bank_id,)):
                if metric not in wide:
                    wide[metric] = {"unit": unit}
                    order.append(metric)
                wide[metric][year] = val if val is not None else raw
            with open(os.path.join(sdir, "per_bank", f"{bank_id}.csv"), "w",
                      newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["metric", "unit"] + years)
                for metric in order:
                    w.writerow([metric, wide[metric]["unit"]] +
                               [wide[metric].get(y, "") for y in years])

            # raw layer: mirrors the workbook tab cell-for-cell (no header row added)
            cells = conn.execute(
                f"SELECT source_row, col_index, cell_text FROM raw_{seg} WHERE bank_id=?",
                (bank_id,)).fetchall()
            if cells:
                nr = max(c[0] for c in cells)
                nc = max(c[1] for c in cells)
                grid = [[""] * nc for _ in range(nr)]
                for r, c, t in cells:
                    grid[r - 1][c - 1] = t
                with open(os.path.join(sdir, "raw", f"{bank_id}_raw_sheet.csv"), "w",
                          newline="", encoding="utf-8") as fh:
                    csv.writer(fh).writerows(grid)

    def as_json(query, name):
        cur = conn.execute(query)
        cols = [d[0] for d in cur.description]
        data = [dict(zip(cols, row)) for row in cur.fetchall()]
        with open(os.path.join(JSON_DIR, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, ensure_ascii=False)

    as_json("SELECT * FROM banks", "banks.json")
    as_json("SELECT * FROM bank_coverage", "bank_coverage.json")
    as_json("SELECT * FROM v_cb_year", "cb_bank_year.json")
    as_json("SELECT * FROM v_socb_year", "socb_bank_year.json")
    as_json("SELECT * FROM data_quality_log", "data_quality_log.json")
    as_json("SELECT * FROM source_notes", "source_notes.json")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    banks, financials, summaries, notes, raw_cells = {}, [], [], [], []

    for source in SOURCES:
        path = os.path.join(RAW, source["file"])
        if not os.path.exists(path):
            sys.exit(f"Missing source workbook: {path}")
        wb = openpyxl.load_workbook(path, data_only=True)
        print(f"reading {source['file']} ({len(wb.worksheets)} sheets)")

        for ws in wb.worksheets:
            grid, last_row = sheet_rows(ws)
            if not grid:
                log("empty_sheet", f"Sheet '{ws.title}' is empty; skipped.", "info")
                continue
            display, title = find_display_name(grid, last_row)
            display = (display or ws.title).strip()
            fixed = DISPLAY_NAME_FIXES.get(display.lower())
            if fixed:
                log("bank_name_normalised",
                    f"Sheet '{ws.title}' titles this bank '{display}'; display_name was "
                    f"normalised to '{fixed}'. The original string is preserved in "
                    f"banks.sheet_title.", "info", slugify(fixed))
                display = fixed
            bank_id = slugify(display)
            if bank_id in banks:
                log("duplicate_bank_sheet",
                    f"Sheet '{ws.title}' resolves to an existing bank_id '{bank_id}'; "
                    f"suffixed to keep both.", "warning", bank_id)
                bank_id = f"{bank_id}_{slugify(ws.title)}"

            banks[bank_id] = {
                "bank_id": bank_id, "display_name": display,
                "sheet_name": ws.title, "bank_type": source["bank_type"],
                "ownership": source["ownership"], "source_file": source["file"],
                "sheet_title": title, "year_min": None, "year_max": None, "n_tables": 0,
            }
            for (r_, c_), v_ in sorted(grid.items()):
                raw_cells.append({
                    "bank_id": bank_id, "sheet_name": ws.title, "source_row": r_,
                    "col_index": c_, "source_col": col_letter(c_),
                    "cell_text": _cell_text(v_), "cell_type": type(v_).__name__})
            rows, stats, sheet_notes, n_tables = parse_sheet(ws, bank_id, source["file"])
            banks[bank_id]["n_tables"] = n_tables
            years = [r["year"] for r in rows if r["value_numeric"] is not None]
            if years:
                banks[bank_id]["year_min"] = min(years)
                banks[bank_id]["year_max"] = max(years)
            financials += rows
            summaries += stats
            notes += sheet_notes
            print(f"  {display:<42} {len(rows):>5} cells  "
                  f"{banks[bank_id]['year_min']}-{banks[bank_id]['year_max']}")

    print("\nrunning quality checks ...")
    detect_percent_scale(financials, banks)
    detect_cross_bank_duplicates(financials, banks)
    detect_outliers(financials, banks)
    detect_ratio_mismatch(financials, banks)
    detect_negative_equity_ratios(financials, banks)
    detect_gaps(financials, banks)

    for (bank_id, token), n in sorted(marker_counts.items()):
        log("missing_marker_cell",
            f"{banks[bank_id]['display_name']}: {n} cell(s) contain the placeholder "
            f"{token!r} rather than a figure. Stored as NULL in value_numeric with the "
            f"placeholder kept in raw_value — never zero-filled.",
            "info", bank_id)

    missing = sum(1 for r in financials if r["value_numeric"] is None)
    log("dataset_summary",
        f"{len(financials)} cells loaded across {len(banks)} banks; {missing} carry no "
        f"numeric value and are stored as NULL (never zero-filled).", "info")

    conn = write_db(banks, financials, summaries, notes, raw_cells)
    export_all(conn)

    sev = dict(conn.execute(
        "SELECT severity, COUNT(*) FROM data_quality_log GROUP BY severity").fetchall())
    print(f"\nwrote {DB_PATH}")
    print(f"  banks              {len(banks)}")
    print(f"  financial rows     {len(financials)}  ({missing} NULL)")
    print(f"  raw cells          {len(raw_cells)}")
    print(f"  distinct metrics   {len({r['metric_std'] for r in financials})}")
    print(f"  source notes       {len(notes)}")
    print(f"  quality log        {len(log_rows)} "
          f"({sev.get('critical',0)} critical, {sev.get('warning',0)} warning, "
          f"{sev.get('info',0)} info)")
    conn.close()


if __name__ == "__main__":
    main()
