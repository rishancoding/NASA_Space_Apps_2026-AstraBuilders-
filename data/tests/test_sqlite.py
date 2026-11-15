"""The SQLite build must reproduce every CSV cell exactly (blank -> NULL, never 0).

Run: python -m unittest data.tests.test_sqlite -v   (standard library only)
"""
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data" / "scripts"))
import build_sqlite  # noqa: E402


class SqliteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = Path(cls.tmp.name) / "test.sqlite"
        cls.counts = build_sqlite.build(cls.db)
        cls.con = sqlite3.connect(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()

    def tables(self):
        return self.con.execute("SELECT table_name, source_file, kind FROM _tables").fetchall()

    def test_one_table_per_file(self):
        csvs = list((build_sqlite.CLEAN).glob("*.csv")) + list((build_sqlite.CLEAN / "source_tables").glob("*.csv"))
        files = {t[1] for t in self.tables()}
        self.assertEqual(len(self.tables()), len(csvs) + 1)  # + evidence_chunks
        for p in csvs:
            self.assertIn(str(p.relative_to(ROOT)).replace("\\", "/"), files)

    def test_every_cell_matches_csv(self):
        for table, source, kind in self.tables():
            if kind == "evidence_text":
                continue
            with (ROOT / source).open(encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))[1:]
            db_rows = self.con.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            self.assertEqual(len(rows), len(db_rows), table)
            for r, d in zip(rows, db_rows):
                for raw, got in zip(r, d):
                    if raw == "":
                        self.assertIsNone(got, f"{table}: blank must be NULL")
                    elif isinstance(got, (int, float)):
                        self.assertEqual(float(raw), float(got), table)
                    else:
                        self.assertEqual(raw, got, table)

    def test_source_tables_stay_text(self):
        types = self.con.execute("SELECT DISTINCT c.sql_type FROM _columns c JOIN _tables t USING (table_name) "
                                 "WHERE t.kind = 'nasa_source_table'").fetchall()
        self.assertEqual(types, [("TEXT",)])

    def test_key_counts_and_types(self):
        q = lambda s: self.con.execute(s).fetchone()[0]
        self.assertEqual(q("SELECT COUNT(*) FROM solid_combustion_model"), 250)
        self.assertEqual(q("SELECT COUNT(*) FROM flex_training"), 202)
        self.assertEqual(q("SELECT COUNT(*) FROM flex_training WHERE extinction_binary = 1"), 176)
        self.assertEqual(q("SELECT COUNT(*) FROM evidence_chunks"), 757)
        self.assertEqual(q("SELECT typeof(oxygen_pct) FROM solid_combustion_model LIMIT 1"), "real")
        # numeric blanks are NULL, not zero
        self.assertGreater(q("SELECT COUNT(*) FROM solid_combustion_model WHERE airflow_cm_s IS NULL"), 0)
        self.assertEqual(q("SELECT COUNT(*) FROM solid_combustion_model WHERE pressure_kpa = 0"), 0)

    def test_evidence_matches_jsonl(self):
        text = (build_sqlite.CLEAN / "evidence_chunks.jsonl").read_text(encoding="utf-8")
        first = json.loads(text.split("\n")[0])
        row = self.con.execute("SELECT text FROM evidence_chunks WHERE chunk_id = ?", (first["chunk_id"],)).fetchone()
        self.assertEqual(row[0], first["text"])


if __name__ == "__main__":
    unittest.main()
