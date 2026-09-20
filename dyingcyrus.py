"""
dyingcyrus.py — a zero-dependency Python API for DyingCyrus-DB.
===============================================================

Copy this file next to dyingcyrus.db and you have a working client. Nothing to
install; pandas is used only if you ask for a DataFrame.

    from dyingcyrus import DyingCyrus

    db = DyingCyrus("dyingcyrus.db")
    db.banks()                                  # every bank
    db.banks("SOCB")                            # one segment: "CB" or "SOCB"
    db.series("city bank", "roe_pct")           # one metric over time
    db.compare("total_assets", 2025, "CB")      # one segment, one year, ranked
    db.panel("SOCB")                            # tidy panel of core metrics
    db.coverage()                               # how complete is each bank?
    db.issues("mutual trust")                   # what's wrong with this bank
    db.notes("rupali")                          # the compiler's source notes
    db.raw("sonali", row=20)                    # untouched source cells
    db.sql("SELECT ...")                        # anything else

Two segments, kept apart: "CB" (commercial banks) and "SOCB" (state-owned and
specialised banks). Each has its own tables; the API picks the right one from
the bank you name. Pass segment=None to compare() / panel() only when you
deliberately want both stacked.

Two rules worth remembering:

1. Percentages. `value_numeric` is whatever the source sheet held; some banks
   write 17.3 and others write 0.173. `value_pct_points` always holds
   percentage points. This API returns percentage points for ratio metrics.
2. Nothing is silently clean. Call `.issues()` for a bank before you quote its
   numbers anywhere that matters.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Iterable, Optional

__all__ = ["DyingCyrus", "RATIO_METRICS"]
__version__ = "3.0.0"
SEGMENTS = {"CB": "cb", "SOCB": "socb"}
_LEGACY = {"PCB": "CB"}     # v2 called the commercial-bank segment "PCB"

RATIO_METRICS = {
    "roa_pct", "roe_pct", "npl_pct_gross", "provision_coverage_pct",
    "loan_deposit_ratio_pct", "car_pct", "cost_income_pct", "npl_to_assets_pct",
    "yoy_npat_growth_pct", "yoy_total_assets_growth_pct", "yoy_equity_growth_pct",
}


class DyingCyrus:
    """A read-only connection to dyingcyrus.db."""

    def __init__(self, path: str = "dyingcyrus.db"):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} not found. Download it from the GitHub release, or run "
                f"`python3 build_db.py` to rebuild it from data/raw/.")
        self.path = path
        self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row

    # -- plumbing ---------------------------------------------------------
    def sql(self, query: str, params: Iterable = ()) -> list[dict]:
        """Run any SELECT and get a list of dicts back."""
        return [dict(r) for r in self.conn.execute(query, tuple(params))]

    def df(self, query: str, params: Iterable = ()):
        """Same, as a pandas DataFrame (requires pandas)."""
        import pandas as pd
        return pd.read_sql(query, self.conn, params=tuple(params))

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- reference --------------------------------------------------------
    @staticmethod
    def _seg(segment: Optional[str]) -> Optional[str]:
        if segment is None:
            return None
        seg = _LEGACY.get(segment.upper(), segment.upper())
        if seg not in SEGMENTS:
            raise ValueError(f"segment must be 'CB' or 'SOCB', got {segment!r}")
        return seg

    def banks(self, segment: Optional[str] = None) -> list[dict]:
        """Every bank, optionally filtered to 'CB' or 'SOCB'."""
        q = "SELECT * FROM banks"
        p: tuple = ()
        seg = self._seg(segment)
        if seg:
            q += " WHERE bank_type = ?"
            p = (seg,)
        return self.sql(q + " ORDER BY bank_type, display_name", p)

    def segment_of(self, bank: str) -> str:
        """'CB' or 'SOCB' for a bank name / id."""
        return self.sql("SELECT bank_type FROM banks WHERE bank_id = ?",
                        (self.resolve(bank),))[0]["bank_type"]

    def coverage(self, segment: Optional[str] = None) -> list[dict]:
        """Completeness of the five core series (assets, loans, deposits, equity,
        NPAT) inside each bank's compiled range, and over the whole sheet."""
        seg = self._seg(segment)
        q = "SELECT * FROM bank_coverage"
        p: tuple = ()
        if seg:
            q += " WHERE segment = ?"
            p = (seg,)
        return self.sql(q + " ORDER BY segment, bank_id", p)

    def metrics(self, segment: Optional[str] = None) -> list[dict]:
        """Every metric_std key, its unit, and the raw labels behind it."""
        seg = self._seg(segment)
        if seg:
            return self.sql("SELECT * FROM metric_catalog WHERE segment = ? "
                            "ORDER BY metric_std", (seg,))
        return self.sql("SELECT * FROM metric_catalog ORDER BY segment, metric_std")

    def metadata(self) -> dict:
        return {r["key"]: r["value"] for r in self.sql("SELECT * FROM build_metadata")}

    def resolve(self, name: str) -> str:
        """Turn 'city bank' or 'City Bank PLC' into a bank_id."""
        hits = self.sql(
            "SELECT bank_id, display_name FROM banks "
            "WHERE bank_id = ?1 OR LOWER(display_name) LIKE '%'||LOWER(?1)||'%'",
            (name,))
        if not hits:
            raise KeyError(f"No bank matches {name!r}. Try db.banks().")
        if len(hits) > 1:
            raise KeyError(f"{name!r} is ambiguous: "
                           f"{', '.join(h['bank_id'] for h in hits)}")
        return hits[0]["bank_id"]

    # -- data -------------------------------------------------------------
    @staticmethod
    def _value_col(metric_std: str) -> str:
        return "value_pct_points" if metric_std in RATIO_METRICS else "value_numeric"

    def series(self, bank: str, metric_std: str) -> list[dict]:
        """One metric for one bank, oldest year first."""
        bank_id = self.resolve(bank)
        seg = SEGMENTS[self.segment_of(bank_id)]
        col = self._value_col(metric_std)
        rows = self.sql(
            f"SELECT year, {col} AS value, unit, raw_value, is_estimated, pct_scale "
            f"FROM financials_{seg} WHERE bank_id = ? AND metric_std = ? "
            f"AND table_instance = 1 ORDER BY year", (bank_id, metric_std))
        if metric_std == "roe_pct":
            # ROE = profit / equity: with NEGATIVE equity a loss prints as a positive ROE.
            eq = {r["year"]: r["v"] for r in self.sql(
                f"SELECT year, value_numeric AS v FROM financials_{seg} WHERE bank_id = ? "
                f"AND metric_std = 'shareholders_equity' AND table_instance = 1", (bank_id,))}
            for r in rows:
                e = eq.get(r["year"])
                r["negative_equity"] = bool(e is not None and e < 0)
        return rows

    def compare(self, metric_std: str, year: int,
                segment: Optional[str] = None) -> list[dict]:
        """One metric, one year, banks ranked high to low. Give a segment
        ('CB' or 'SOCB'); segment=None stacks both on purpose."""
        col = self._value_col(metric_std)
        seg = self._seg(segment)
        segs = [seg] if seg else list(SEGMENTS)
        out: list[dict] = []
        for sg in segs:
            t = SEGMENTS[sg]
            out += self.sql(
                f"SELECT b.display_name, b.bank_type, f.{col} AS value, f.unit, "
                f"f.is_estimated FROM financials_{t} f JOIN banks b ON b.bank_id = f.bank_id "
                f"WHERE f.metric_std = ? AND f.year = ? AND f.table_instance = 1 "
                f"AND f.{col} IS NOT NULL", (metric_std, year))
        return sorted(out, key=lambda r: r["value"], reverse=True)

    def panel(self, segment: Optional[str] = None,
              year_from: Optional[int] = None,
              year_to: Optional[int] = None) -> list[dict]:
        """The core metrics as one row per bank-year, ready for analysis.
        segment 'CB' or 'SOCB' reads that segment's own view; None stacks both."""
        seg = self._seg(segment)
        q = f"SELECT * FROM {'v_' + SEGMENTS[seg] + '_year' if seg else 'v_all_year'} WHERE 1=1"
        p: tuple = ()
        if year_from:
            q += " AND year >= ?"
            p += (year_from,)
        if year_to:
            q += " AND year <= ?"
            p += (year_to,)
        return self.sql(q + " ORDER BY bank_id, year", p)

    def summary_stats(self, bank: str) -> list[dict]:
        return self.sql(
            "SELECT stat_name, value FROM bank_summary_stats WHERE bank_id = ? "
            "ORDER BY source_row", (self.resolve(bank),))

    # -- provenance -------------------------------------------------------
    def issues(self, bank: Optional[str] = None,
               severity: Optional[str] = None) -> list[dict]:
        """Known data-quality problems. Read this before trusting a number."""
        q = "SELECT severity, issue, metric, year, detail FROM data_quality_log WHERE 1=1"
        p: tuple = ()
        if bank:
            q += " AND bank_id = ?"
            p += (self.resolve(bank),)
        if severity:
            q += " AND severity = ?"
            p += (severity,)
        return self.sql(q + " ORDER BY CASE severity WHEN 'critical' THEN 0 "
                            "WHEN 'warning' THEN 1 ELSE 2 END, year", p)

    def notes(self, bank: str) -> list[str]:
        """The compiler's own sourcing notes for a bank, in sheet order."""
        return [r["note_text"] for r in self.sql(
            "SELECT note_text FROM source_notes WHERE bank_id = ? ORDER BY note_index",
            (self.resolve(bank),))]

    def provenance(self, bank: str, metric_std: str, year: int) -> Optional[dict]:
        """Where exactly did this one number come from?"""
        bank_id = self.resolve(bank)
        seg = SEGMENTS[self.segment_of(bank_id)]
        rows = self.sql(
            f"SELECT f.*, b.display_name, b.source_file AS wb FROM financials_{seg} f "
            "JOIN banks b ON b.bank_id = f.bank_id WHERE f.bank_id = ? "
            "AND f.metric_std = ? AND f.year = ? AND f.table_instance = 1",
            (bank_id, metric_std, year))
        return rows[0] if rows else None

    def raw(self, bank: str, row: Optional[int] = None,
            year_col: Optional[str] = None) -> list[dict]:
        """The untouched source cells for a bank (the raw layer). Optionally one
        sheet row, or one column letter. Values are text exactly as read."""
        bank_id = self.resolve(bank)
        seg = SEGMENTS[self.segment_of(bank_id)]
        q = (f"SELECT source_row, source_col, cell_text, cell_type FROM raw_{seg} "
             "WHERE bank_id = ?")
        p: tuple = (bank_id,)
        if row is not None:
            q += " AND source_row = ?"
            p += (row,)
        if year_col:
            q += " AND source_col = ?"
            p += (year_col.upper(),)
        return self.sql(q + " ORDER BY source_row, col_index", p)


if __name__ == "__main__":
    db = DyingCyrus(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "dyingcyrus.db"))
    meta = db.metadata()
    print(f"DyingCyrus-DB v{meta['build_version']} built {meta['built_at_utc']}")
    print(f"{meta['n_banks']} banks ({meta['n_banks_cb']} CB, {meta['n_banks_socb']} SOCB), "
          f"{meta['n_financial_rows']} cells, {meta['n_raw_cells']} raw cells, "
          f"{meta['n_log_entries']} quality-log entries")
    print("\nTop 5 commercial banks by total assets, 2025 (Tk mn):")
    for row in db.compare("total_assets", 2025, "CB")[:5]:
        print(f"  {row['display_name']:<40} {row['value']:>12,.0f}")
