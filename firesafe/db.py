"""SQLite copy of the curated NASA data package, for the assistant's read-only SQL tool.

`data/firesafe.sqlite` is generated from `data/clean/` (plus the hand-transcribed
Saffire list) and is never edited by hand. `connect()` rebuilds it whenever the
inputs change, so it cannot drift from the CSVs. Rules kept from the data package:

* An empty CSV cell becomes NULL (missing), never 0. A recorded 0 stays 0.
* The original NASA tables (`src_*`) keep every cell exactly as published, as TEXT.
* Every table is described in `_tables` (source file, grain, investigations,
  caveats) and every column in `_columns`, so query results can be traced back.

The app and the assistant only ever open the file read-only.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from functools import lru_cache
from pathlib import Path

from . import CLEAN, ROOT
from .data import OUTCOME_GROUPS, PSI_URL, SAFFIRE

DB_PATH = ROOT / "data" / "firesafe.sqlite"
SCHEMA_VERSION = "1"

# Columns that look numeric but are identifiers or verbatim NASA text: always TEXT.
_TEXT_COLUMNS = re.compile(r"(_id|_raw|_date|^sample|_identifier|_group)$")

# Curated tables: SQL name -> (CSV file, grain, caveats). Order is the order shown to the agent.
CURATED = {
    "solid_combustion_model": (
        "solid_combustion_model.csv",
        "One row per BASS (PSI-26) or BASS-II (PSI-25) solid-fuel test (250 tests). Conditions can change within a test.",
        "outcome/outcome_group are project-team-verified test-level labels. burned_binary means ANY flame "
        "was seen (including brief ignition); it is not sustained burning. airflow_cm_s is a single Air-display "
        "reading only when the test had one; all readings are in airflow_readings. airflow_raw is verbatim text: "
        "never average or parse it in SQL. BASS-II pressure was not recorded (NULL)."),
    "airflow_readings": (
        "airflow_readings.csv",
        "One row per airflow value recorded during a solid test (join on experiment_id).",
        "recorded_order is reading order, not a timestamp. Use airflow_display_cm_s only where "
        "reading_status = 'exact_display'. The outcome column is deliberately unassigned for most readings."),
    "solid_stage_observations": (
        "solid_stage_observations.csv",
        "One row per evidence-linked flame event/stage within a solid test (395 stages).",
        "Includes stages with unknown conditions and excluded endpoints. sustained_flame_binary is the "
        "project-team-verified stage label. training_eligible = 1 marks the 47 stages in solid_stage_training."),
    "solid_stage_training": (
        "solid_stage_training.csv",
        "The 47 solid stages with exact oxygen/airflow and a sustained-flame label: the solid model's training set.",
        "Small and exploratory. oxygen_initial_pct is the initial atmosphere (a proxy for oxygen at the stage). "
        "protocol (ignition_trial vs ongoing_burn_trial) must be kept separate when comparing outcomes."),
    "flex_labeled": (
        "flex_labeled.csv",
        "One row per FLEX (PSI-69) fuel-droplet combustion test (274 tests), with extinction labels.",
        "Liquid droplets: never pool with solid tests. extinction_binary is NULL for disrupted tests (censored). "
        "training_eligible = 1 marks the 207 tests in flex_training."),
    "flex_training": (
        "flex_training.csv",
        "The 207 FLEX droplet tests used to train the droplet extinction model.",
        "Subset of flex_labeled. 180 extinction / 27 completion."),
    "ground_thresholds": (
        "ground_thresholds.csv",
        "Earth-gravity oxygen flammability thresholds (ULOI/MOC) by material configuration, NTRS 20110008636.",
        "External to PSI, measured in 1 g. A different quantity from orbital burn outcomes: comparison only."),
    "investigation_catalog": (
        "investigation_catalog.csv",
        "One row per NASA investigation (19 PSI records plus the NTRS ground-test report).",
        "Join any table to this on source_record for the investigation name, title and URL."),
    "publications": (
        "publications.csv",
        "Publications listed by NASA PSI for each investigation.",
        "Bibliographic listing only; not verified results."),
    "excluded_rows": (
        "excluded_rows.csv",
        "Source rows the build excluded, with the reason.",
        ""),
}

SAFFIRE_TABLE = ("saffire_samples",
                 "One row per Saffire I-III (PSI-98/99/100) large-scale burn sample, transcribed from the NASA tables.",
                 "Values are TEXT quoted as NASA published them (e.g. '~ 22.1'). Rows with material NULL had a blank "
                 "material cell and must not be attributed to a material.")


def _source_tables() -> list[dict]:
    """table_index.json entries plus a stable SQL table name for each original NASA table."""
    out, used = [], set()
    for e in json.loads((CLEAN / "table_index.json").read_text()):
        stem = Path(e["file"]).stem.replace("Experimental table", "")
        name = "src_" + re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
        while name in used:
            name += "_2"
        used.add(name)
        out.append({**e, "table": name})
    return out


def _inputs() -> list[Path]:
    files = [CLEAN / f for f, _, _ in CURATED.values()]
    files += [CLEAN / e["file"] for e in _source_tables()]
    return files + [CLEAN / "table_index.json", CLEAN / "data_contract.json"]


def fingerprint() -> str:
    h = hashlib.sha256(SCHEMA_VERSION.encode())
    h.update(Path(__file__).read_bytes())          # build logic changes also trigger a rebuild
    for p in _inputs():
        h.update(p.name.encode())
        h.update(p.read_bytes())
    h.update(json.dumps(SAFFIRE, sort_keys=True, default=str).encode())
    return h.hexdigest()


def _read_csv(path: Path) -> tuple[list[str], list[list[str]]]:
    enc = "utf-8-sig"
    with path.open(encoding=enc, newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def _num(v: str):
    try:
        return int(v) if re.fullmatch(r"-?\d+", v) else float(v)
    except ValueError:
        return None


def _column_types(header: list[str], rows: list[list[str]]) -> list[str]:
    """INTEGER/REAL when every non-blank value is a number (or a true/false flag), else TEXT."""
    types = []
    for i, col in enumerate(header):
        vals = [r[i] for r in rows if i < len(r) and r[i] != ""]
        if _TEXT_COLUMNS.search(col) or not vals:
            types.append("TEXT")
        elif all(v.lower() in ("true", "false") for v in vals):
            types.append("BOOLEAN")
        elif all(_num(v) is not None for v in vals):
            types.append("INTEGER" if all(isinstance(_num(v), int) for v in vals) else "REAL")
        else:
            types.append("TEXT")
    return types


def _convert(v: str, t: str):
    if v == "":
        return None                       # blank = missing, never zero
    if t == "BOOLEAN":
        return 1 if v.lower() == "true" else 0
    if t in ("INTEGER", "REAL"):
        return _num(v)
    return v


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _create(con, table: str, header: list[str], types: list[str], rows: list[list]) -> None:
    decl = ", ".join(f"{_q(c)} {'INTEGER' if t == 'BOOLEAN' else t}" for c, t in zip(header, types))
    con.execute(f"CREATE TABLE {_q(table)} ({decl})")
    con.executemany(f"INSERT INTO {_q(table)} VALUES ({', '.join('?' * len(header))})", rows)


def build(path: Path = DB_PATH) -> Path:
    """Write the database atomically (temp file, then rename). Returns the path."""
    contract = json.loads((CLEAN / "data_contract.json").read_text())["columns"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".firesafe-", suffix=".sqlite", dir=path.parent)
    os.close(fd)
    con = sqlite3.connect(tmp)
    try:
        con.execute("CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT)")
        con.execute("CREATE TABLE _tables (table_name TEXT PRIMARY KEY, kind TEXT, source_file TEXT, grain TEXT, "
                    "caveats TEXT, source_records TEXT, row_count INTEGER)")
        con.execute("CREATE TABLE _columns (table_name TEXT, column_name TEXT, sql_type TEXT, unit TEXT, "
                    "contract_use TEXT, PRIMARY KEY (table_name, column_name))")

        def register(table, kind, src, grain, caveats, header, types, rows):
            recs = []
            if "source_record" in header:
                i = header.index("source_record")
                recs = sorted({r[i] for r in rows if r[i]})
            elif "experiment_id" in header:         # experiment_id = "<source_record>:<...>"
                i = header.index("experiment_id")
                recs = sorted({r[i].split(":")[0] for r in rows if r[i]})
            con.execute("INSERT INTO _tables VALUES (?,?,?,?,?,?,?)",
                        (table, kind, src, grain, caveats, json.dumps(recs), len(rows)))
            for c, t in zip(header, types):
                info = contract.get(c, {}) if kind == "curated" else {}
                con.execute("INSERT INTO _columns VALUES (?,?,?,?,?)",
                            (table, c, "INTEGER (0/1)" if t == "BOOLEAN" else t,
                             info.get("unit") or None, info.get("use") or None))

        for table, (file, grain, caveats) in CURATED.items():
            header, raw = _read_csv(CLEAN / file)
            types = _column_types(header, raw)
            rows = [[_convert(v, t) for v, t in zip(r, types)] for r in raw]
            if table == "solid_combustion_model":          # same display grouping the app's tools use
                i = header.index("outcome")
                header, types = header + ["outcome_group"], types + ["TEXT"]
                rows = [r + [OUTCOME_GROUPS.get(r[i], "not usable")] for r in rows]
            _create(con, table, header, types, rows)
            register(table, "curated", f"data/clean/{file}", grain, caveats, header, types, rows)

        s_header = ["source_record", "sample", "material", "material_raw", "thickness", "airflow_cm_s", "oxygen",
                    "flow_direction", "burn_time", "burn_length", "spread_rate", "result", "source_url"]
        s_types = ["TEXT"] * 5 + ["REAL"] + ["TEXT"] * 7
        s_rows = [[(r.get(c) if r.get(c) != "" else None) for c in s_header] for r in SAFFIRE]
        _create(con, SAFFIRE_TABLE[0], s_header, s_types, s_rows)
        register(SAFFIRE_TABLE[0], "curated", "firesafe/data.py SAFFIRE (from data/clean/source_tables PSI-98/99/100)",
                 SAFFIRE_TABLE[1], SAFFIRE_TABLE[2], s_header, s_types, s_rows)

        for e in _source_tables():
            header, raw = _read_csv(CLEAN / e["file"])
            header = ["_source_row"] + header
            if any(len(r) > len(header) - 1 for r in raw):
                raise ValueError(f"{e['file']}: a row has more cells than the header")
            rows = [[i + 2] + r + [""] * (len(header) - 1 - len(r)) for i, r in enumerate(raw)]
            types = ["INTEGER"] + ["TEXT"] * (len(header) - 1)
            _create(con, e["table"], header, types, rows)
            register(e["table"], "nasa_source_table", f"data/clean/{e['file']}",
                     f"Original NASA PSI experimental table for {e['source_record']}, one row per published row "
                     f"(role: {e['role']}). _source_row is the CSV line number (header = 1), the same numbering as "
                     f"source_row in the curated tables, so curated rows join back to the NASA row.",
                     "Every cell is TEXT exactly as NASA published it, including note/calibration rows, units in "
                     "cells and typos. Blank cells are ''. CAST(... AS REAL) only after checking the values.",
                     header, types, rows)
            con.execute("UPDATE _tables SET source_records = ? WHERE table_name = ?",
                        (json.dumps([e["source_record"]]), e["table"]))

        con.executemany("INSERT INTO _meta VALUES (?, ?)",
                        [("fingerprint", fingerprint()), ("schema_version", SCHEMA_VERSION),
                         ("null_encoding", "Empty CSV cell -> NULL in curated tables (missing, never zero); "
                                           "'' in src_* tables (verbatim)")])
        con.commit()
    finally:
        con.close()
    os.replace(tmp, path)
    return path


def _current(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = con.execute("SELECT value FROM _meta WHERE key = 'fingerprint'").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return False
    return bool(row) and row[0] == fingerprint()


@lru_cache(maxsize=None)
def ensure() -> Path:
    """Build the database if it is missing or older than the CSVs (checked once per process)."""
    if not _current(DB_PATH):
        build(DB_PATH)
    return DB_PATH


# ---- read-only access ------------------------------------------------------------------------

_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
_RECURSIVE = getattr(sqlite3, "SQLITE_RECURSIVE", 33)
MAX_ROWS = 200
MAX_STEPS = 100_000_000     # VM instructions (well under a second); stops runaway cross joins


class QueryError(ValueError):
    pass


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{ensure()}?mode=ro", uri=True, check_same_thread=False)
    con.execute("PRAGMA query_only = ON")
    return con


def run_select(sql: str, limit: int = 100) -> dict:
    """Run one read-only SELECT. Returns columns, rows (dicts), truncation flag and the tables read."""
    sql = (sql or "").strip().rstrip(";").strip()
    if not re.match(r"(?is)^(select|with)\b", sql):
        raise QueryError("Only a single SELECT (or WITH ... SELECT) statement is allowed.")
    limit = max(1, min(int(limit), MAX_ROWS))
    tables: set[str] = set()

    def authorizer(action, arg1, arg2, _db, _trigger):
        if action == sqlite3.SQLITE_READ:
            if arg1 and not arg1.startswith("sqlite_"):
                tables.add(arg1)
            return sqlite3.SQLITE_OK
        if action in _ALLOWED or action == _RECURSIVE:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    steps = [0]

    def progress():
        steps[0] += 1000
        return 1 if steps[0] > MAX_STEPS else 0

    con = connect()
    try:
        con.set_authorizer(authorizer)
        con.set_progress_handler(progress, 1000)
        try:
            cur = con.execute(sql)
            cols = [d[0] for d in cur.description or []]
            fetched = cur.fetchmany(limit + 1)
        except sqlite3.ProgrammingError as e:          # e.g. two statements
            raise QueryError(str(e)) from e
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "interrupted" in msg:
                msg = "Query stopped: too much work (check joins and add filters)."
            elif "not authorized" in msg:
                msg = "Not allowed: the database is read-only and accepts only SELECT."
            raise QueryError(msg) from e
    finally:
        con.close()
    rows = [dict(zip(cols, r)) for r in fetched[:limit]]
    return {"columns": cols, "rows": rows, "returned": len(rows), "truncated": len(fetched) > limit,
            "tables_used": sorted(tables)}


@lru_cache(maxsize=None)
def table_meta() -> dict[str, dict]:
    con = connect()
    try:
        con.row_factory = sqlite3.Row
        out = {r["table_name"]: {**dict(r), "source_records": json.loads(r["source_records"])}
               for r in con.execute("SELECT * FROM _tables")}
        for r in con.execute("SELECT * FROM _columns"):
            out[r["table_name"]].setdefault("columns", []).append(
                {k: r[k] for k in ("column_name", "sql_type", "unit") if r[k]})
    finally:
        con.close()
    return out


@lru_cache(maxsize=None)
def investigations() -> dict[str, dict]:
    """source_record -> name, title, URL, from the catalog table."""
    con = connect()
    try:
        rows = con.execute("SELECT source_record, investigation_name, official_title, url "
                           "FROM investigation_catalog").fetchall()
    finally:
        con.close()
    return {r[0]: {"source_record": r[0], "investigation": r[1], "title": r[2], "url": r[3] or PSI_URL.format(r[0])}
            for r in rows}


def schema_text() -> str:
    """Compact schema for the system prompt: every curated table with its columns, then the NASA tables."""
    meta = table_meta()
    lines = ["Curated tables (blank = NULL = missing, never zero):"]
    for name, m in meta.items():
        if m["kind"] != "curated":
            continue
        cols = ", ".join(f"{c['column_name']} {c['sql_type'].split()[0]}"
                         + (f" [{c['unit'].split(';')[0]}]" if c.get("unit") else "") for c in m["columns"])
        lines.append(f"- {name} ({m['row_count']} rows; {m['source_file']}): {m['grain']} "
                     f"CAVEATS: {m['caveats'] or 'none'}\n  columns: {cols}")
    lines.append("Original NASA tables (all TEXT, verbatim; call describe_database for their columns):")
    for name, m in meta.items():
        if m["kind"] == "nasa_source_table":
            lines.append(f"- {name} ({m['row_count']} rows, {', '.join(m['source_records'])})")
    return "\n".join(lines)
