"""
examples/quickstart.py — run this first.

    cd DyingCyrus-DB
    python3 examples/quickstart.py

It uses only the standard library. Every section is something you will
plausibly want to do on day one.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dyingcyrus import DyingCyrus  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "dyingcyrus.db")


def rule(title):
    print(f"\n{'=' * 68}\n{title}\n{'=' * 68}")


with DyingCyrus(DB) as db:

    rule("1. What's in the box")
    meta = db.metadata()
    print(f"build {meta['build_version']} — {meta['n_banks']} banks "
          f"({meta['n_banks_cb']} CB, {meta['n_banks_socb']} SOCB), "
          f"{meta['n_financial_rows']} cells, {meta['n_raw_cells']} raw cells, "
          f"{meta['n_log_entries']} log entries")
    for b in db.banks():
        print(f"  [{b['bank_type']}] {b['display_name']:<40} {b['year_min']}–{b['year_max']}")

    rule("2. One bank over time — City Bank ROE")
    for row in db.series("city_bank_plc", "roe_pct"):
        print(f"  {row['year']}  {row['value']:>7.2f} %")

    rule("3. League table — commercial banks, total assets 2025 (Tk mn)")
    for row in db.compare("total_assets", 2025, "CB"):
        print(f"  {row['display_name']:<42} {row['value']:>14,.0f}")

    rule("4. State-owned vs commercial — average NPL %, 2024 (deliberate stack)")
    buckets = {}
    for row in db.panel(None, year_from=2024, year_to=2024):
        if row["npl_pct"] is not None:
            buckets.setdefault(row["bank_type"], []).append(row["npl_pct"])
    for kind, values in sorted(buckets.items()):
        print(f"  {kind}: {sum(values) / len(values):.2f} %  (n={len(values)})")

    rule("5. Check before you quote — Mutual Trust Bank")
    issues = db.issues("mutual_trust_bank_plc", severity="critical")
    print(f"  {len(issues)} critical entries. First one:")
    print("  " + issues[0]["detail"][:300] + "...")

    rule("6. The compiler's own notes — Bangladesh Krishi Bank")
    for note in db.notes("bangladesh_krishi_bank_bkb")[:3]:
        print("  • " + note[:160] + ("..." if len(note) > 160 else ""))

    rule("7. Trace a single number to its cell")
    p = db.provenance("sonali_bank", "total_assets", 2024)
    print(f"  Sonali total assets 2024 = {p['value_numeric']:,.1f} {p['unit']}")
    print(f"  from {p['source_file']}  sheet cell {p['source_col']}{p['source_row']}  "
          f"(raw text {p['raw_value']!r}, parsed as {p['value_source']})")

    rule("8. How complete is the data? (core five series, inside each bank's range)")
    for c in db.coverage():
        print(f"  [{c['segment']:<4}] {c['bank_id']:<38} {c['compiled_first']}–{c['compiled_last']}"
              f"  {c['core5_pct']:>5.1f} %")

    rule("9. The trap — Krishi Bank ROE on negative equity")
    for r in db.series("krishi", "roe_pct")[-4:]:
        if r["value"] is not None:
            print(f"  {r['year']}  printed ROE {r['value']:>6.1f} %   "
                  f"negative equity: {r['negative_equity']}")
    print("  A loss divided by negative equity prints as a POSITIVE ROE. Don't rank on it.")

    rule("10. The raw layer — untouched source cells")
    cells = db.raw("sonali", row=p["source_row"])      # the row from step 7
    print(f"  Sonali sheet row {p['source_row']} (the total-assets row), first cells:")
    for c in cells[:4]:
        print(f"    {c['source_col']}{p['source_row']}  {c['cell_text'][:40]!r}  ({c['cell_type']})")

    rule("11. Anything else — raw SQL")
    rows = db.sql("""
        SELECT display_name, year, car_pct FROM v_all_year
        WHERE car_pct < 0 ORDER BY car_pct LIMIT 5
    """)
    for r in rows:
        print(f"  {r['display_name']:<42} {r['year']}  CAR {r['car_pct']:.2f} %")

print("\nDone. Next: examples/queries.sql, then docs/USER_MANUAL.md")
