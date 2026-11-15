#!/usr/bin/env python3
"""Build a SQLite database from the cleaned CSVs in data/clean/.

One table per CSV:
  data/clean/<name>.csv              -> table <name>             (typed columns)
  data/clean/source_tables/<f>.csv   -> table src_<short name>   (original NASA text, untyped),
                                        e.g. "PSI-69_Experimental table_FLEX.csv" -> src_psi_69_flex
  data/clean/evidence_chunks.jsonl   -> table evidence_chunks    (research-assistant text)

Plus two catalogue tables:
  _tables   one row per table: source file, row count, kind, description
  _columns  one row per column: original CSV header, SQL name, inferred type

Data rules from data/DATA_HANDOFF.md are kept:
  - A blank cell becomes NULL, never 0.
  - Source tables keep NASA's original cell text (TEXT columns, nothing "fixed").
  - Clean-table columns become INTEGER/REAL only if every non-blank value parses;
    values with leading zeros (e.g. "007") keep the column as TEXT.

Standard library only. Run from the repo root:
    python data/scripts/build_sqlite.py                  # writes data/flame.sqlite
    python data/scripts/build_sqlite.py --out other.db
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "data" / "clean"
DEFAULT_OUT = ROOT / "data" / "flame.sqlite"

DESCRIPTIONS = {
    "solid_combustion_model": "250 BASS/BASS-II solid-fuel tests: conditions, crew notes, team-verified whole-test outcome",
    "solid_stage_observations": "Evidence-linked flame events within solid tests, with exclusion reasons",
    "solid_stage_training": "47 screened solid stages with sustained_flame_binary (exploratory; no model trained)",
    "label_review_queue": "Team-verified review worksheet for all 250 solid tests",
    "airflow_readings": "Ordered airflow display readings per solid test (order is not time)",
    "flex_backup": "274 FLEX droplet tests (PSI-69) as cleaned",
    "flex_labeled": "All 274 FLEX tests with extinction_binary and exclusion reasons",
    "flex_training": "202 FLEX tests used to train the extinction and burn-time models",
    "ground_thresholds": "70 Earth-gravity ULOI/MOC oxygen limits (NTRS 20110008636); comparison only",
    "investigation_catalog": "19 PSI investigations plus the NTRS ground report",
    "publications": "Publication references listed by PSI",
    "excluded_rows": "Rows removed from source tables, with reasons",
    "evidence_chunks": "757 NASA text passages with locators, for search and the chat agent",
}
INDEX_COLUMNS = ("source_record", "experiment_id", "material", "fuel", "split_group", "validation_group", "test_id")


def sql_name(raw: str, used: set[str], fallback: str) -> str:
    """Lower-case snake_case identifier, unique within `used`."""
    name = re.sub(r"[^0-9a-zA-Z]+", "_", raw.strip()).strip("_").lower() or fallback
    if name[0].isdigit():
        name = "c_" + name
    base, n = name, 2
    while name in used:
        name, n = f"{base}_{n}", n + 1
    used.add(name)
    return name


def infer_type(values: list[str]) -> str:
    seen = [v for v in values if v != ""]
    if not seen:
        return "TEXT"
    if any(len(v) > 1 and v[0] == "0" and v[1].isdigit() for v in seen):
        return "TEXT"  # keep leading zeros
    try:
        for v in seen:
            int(v)
        return "INTEGER"
    except ValueError:
        pass
    try:
        for v in seen:
            if v.lower() in {"nan", "inf", "-inf", "infinity"}:
                return "TEXT"
            float(v)
        return "REAL"
    except ValueError:
        return "TEXT"


def convert(v: str, typ: str):
    if v == "":
        return None
    return int(v) if typ == "INTEGER" else float(v) if typ == "REAL" else v


def read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    width = len(header)
    # Pad short rows (trailing blanks) and refuse silently dropping data from long ones.
    for i, r in enumerate(body):
        if len(r) > width:
            if any(c.strip() for c in r[width:]):
                raise ValueError(f"{path.name} row {i + 2} has more cells than the header")
            body[i] = r[:width]
        elif len(r) < width:
            body[i] = r + [""] * (width - len(r))
    return header, body


def load_table(con, table, header, body, typed, source_file, kind):
    used: set[str] = set()
    cols = [sql_name(h, used, f"col_{i + 1}") for i, h in enumerate(header)]
    types = [infer_type([r[i] for r in body]) if typed else "TEXT" for i in range(len(cols))]
    con.execute(f'DROP TABLE IF EXISTS "{table}"')
    con.execute(f'CREATE TABLE "{table}" ({", ".join(f"{c} {t}" for c, t in zip(cols, types))})')
    con.executemany(f'INSERT INTO "{table}" VALUES ({", ".join("?" * len(cols))})',
                    [[convert(v, t) if typed else (None if v == "" else v) for v, t in zip(r, types)] for r in body])
    for c in cols:
        if c in INDEX_COLUMNS:
            con.execute(f'CREATE INDEX "ix_{table}_{c}" ON "{table}" ({c})')
    con.execute("INSERT INTO _tables VALUES (?,?,?,?,?)",
                (table, source_file, len(body), kind, DESCRIPTIONS.get(table, "")))
    con.executemany("INSERT INTO _columns VALUES (?,?,?,?,?)",
                    [(table, i + 1, h, c, t) for i, (h, c, t) in enumerate(zip(header, cols, types))])
    return len(body)


def build(out: Path) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.execute("CREATE TABLE _tables (table_name TEXT PRIMARY KEY, source_file TEXT, row_count INTEGER, kind TEXT, description TEXT)")
    con.execute("CREATE TABLE _columns (table_name TEXT, position INTEGER, original_header TEXT, column_name TEXT, sql_type TEXT)")
    counts = {}

    for path in sorted(CLEAN.glob("*.csv")):
        header, body = read_csv(path)
        counts[path.stem] = load_table(con, path.stem, header, body, True, f"data/clean/{path.name}", "clean")

    used_names: set[str] = set(counts)
    for path in sorted((CLEAN / "source_tables").glob("*.csv")):
        header, body = read_csv(path)
        table = "src_" + sql_name(path.stem.replace("_Experimental table_", "_"), used_names, "table")
        counts[table] = load_table(con, table, header, body, False,
                                   f"data/clean/source_tables/{path.name}", "nasa_source_table")

    chunks = [json.loads(line) for line in (CLEAN / "evidence_chunks.jsonl").read_text(encoding="utf-8").split("\n") if line.strip()]
    keys = list(chunks[0])
    counts["evidence_chunks"] = load_table(con, "evidence_chunks", keys, [[str(c.get(k, "")) for k in keys] for c in chunks],
                                           False, "data/clean/evidence_chunks.jsonl", "evidence_text")

    con.commit()
    con.execute("VACUUM")
    con.close()
    tmp.replace(out)
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    counts = build(args.out)
    print(f"Wrote {args.out} with {len(counts)} tables:")
    for t, n in counts.items():
        print(f"  {t:60s} {n:5d} rows")


if __name__ == "__main__":
    main()
