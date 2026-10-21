"""Offline parser/progress integration without Polars or Streamlit.

Parses actual synthetic XLSX bytes while replacing only the SQLite interface
with a stub. Full real-DB integration is covered by test_report_retention.py.
"""
from __future__ import annotations

import importlib.util
import io
import sys
import types
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent


def workbook(with_summary: bool = True) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name in ["DC Summary", "XD Summary", "DC Roster Adoption", "XD Roster Adoption"]:
        ws = book.create_sheet(name)
        ws.append(["Site", datetime(2026, 10, 15), None, None])
        ws.append([None, "Active HC", "Rostered HC", "Roster Match"])
        if name == "DC Summary" and with_summary:
            ws.append(["Demo DC", 25, 22, 20])
    output = io.BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def isolated_parser():
    fake = types.ModuleType("db")
    calls = []

    class Connection:
        def execute(self, sql):
            calls.append(("execute", sql))

    @contextmanager
    def connect(_database):
        yield Connection()

    fake.connect = connect
    fake.normalize_site = lambda site: site.strip().casefold()
    fake.infer_facility_type = lambda site: site.rsplit(" ", 1)[-1]
    fake.clear_previous_report = lambda _connection, kind: calls.append(("clear", kind))
    fake.upsert_sites = lambda *args, **kwargs: calls.append(("sites", len(args[1])))
    fake.replace_summary_rows = lambda _path, rows, **kwargs: len(rows)
    fake.replace_attendance_detail = lambda *args, **kwargs: 0
    fake.replace_flex_detail = lambda *args, **kwargs: 0
    fake.replace_onboarding_red_detail = lambda *args, **kwargs: 0
    fake.sync_attendance_single_punch_percent = lambda *args, **kwargs: None
    fake.add_import_history = lambda *args, **kwargs: calls.append(("history", args[1]))
    spec = importlib.util.spec_from_file_location("parser_stage_test", ROOT / "parsers.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"db": fake}):
        spec.loader.exec_module(module)
    return module, calls


class ParserStageTests(unittest.TestCase):
    def test_real_xlsx_parser_emits_accurate_stage_captions(self):
        parser, calls = isolated_parser()
        stages = []
        result = parser.process_workbook(
            workbook(), "synthetic_roster.xlsx", "memory",
            progress=lambda fraction, description: stages.append((fraction, description)),
        )
        self.assertEqual(result["report_type"], "Roster")
        self.assertEqual(result["summary_rows"], 3)
        self.assertEqual([value for value, _ in stages], [.06, .17, .28, .65, .74, .87])
        self.assertIn("Parsing Roster", stages[2][1])
        self.assertIn("3 summary rows", stages[3][1])
        self.assertIn(("clear", "Roster"), calls)
        self.assertIn(("history", "Roster"), calls)

    def test_bad_workbook_never_clears_previous_data(self):
        parser, calls = isolated_parser()
        stages = []
        with self.assertRaisesRegex(ValueError, "no usable summary"):
            parser.process_workbook(
                workbook(with_summary=False), "empty.xlsx", "memory",
                progress=lambda fraction, description: stages.append((fraction, description)),
            )
        self.assertEqual([value for value, _ in stages], [.06, .17, .28, .65])
        self.assertFalse(any(record[0] in ("clear", "history") for record in calls))


if __name__ == "__main__":
    unittest.main()
