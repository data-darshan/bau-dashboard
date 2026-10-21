"""Regression checks for centered landing copy and source-backed 8-hour counts.

No Streamlit runtime or real employee workbook is required.
"""
from __future__ import annotations

import ast
import unittest
from datetime import date
from pathlib import Path

from metric_mappings import source_count_metric

ROOT = Path(__file__).resolve().parent.parent
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


def isolated_count_lookup(query_summary):
    """Run the actual app helper with a controlled query; no Streamlit import."""
    function = next(
        node for node in APP_TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "chart_point_count"
    )
    isolated = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    scope = {
        "source_count_metric": source_count_metric,
        "query_summary": query_summary,
        "DB_PATH": "session_database",
        "date": date,
    }
    exec(compile(isolated, str(ROOT / "app.py"), "exec"), scope)
    return scope["chart_point_count"]


class FakeFrame:
    def __init__(self, count=None):
        self.count = count
    def is_empty(self):
        return self.count is None
    def row(self, idx, named=False):
        assert idx == 0 and named
        return {"value": self.count}


class PopupCountRegressionTests(unittest.TestCase):
    def test_attendance_and_flex_have_different_official_8hour_headers(self):
        self.assertEqual(source_count_metric("attendance", "8 Hrs + Adherence"), "8 Hours +")
        self.assertEqual(source_count_metric("flex_working", "8 Hrs + Adherence"), "8 Hours+")
        for metric, official in (
            ("5 to 8 Hrs Adherence", "5 to 8 Hours"),
            ("<5 Hrs Adherence", "Less than 5 Hours"),
            ("Single Punch %", "Single Punch"),
        ):
            for section in ("attendance", "flex_working"):
                with self.subTest(section=section, metric=metric):
                    self.assertEqual(source_count_metric(section, metric), official)
        self.assertIsNone(source_count_metric("attendance", "Unknown"))
        self.assertIsNone(source_count_metric("onboarding", "8 Hrs + Adherence"))

    def test_click_retrieves_exact_attendance_count_and_preserves_filter_scope(self):
        calls = []
        sample = {("attendance", "2026-10-01", "ncr bamnoli dc", "8 Hours +"): 164}
        def query(db_path, section, dfrom, dto, regions, types, sites, metrics):
            calls.append((db_path, section, dfrom, dto, regions, types, sites, metrics))
            return FakeFrame(sample.get((section, dfrom.isoformat(), sites[0], metrics[0])))
        picker = isolated_count_lookup(query)
        day = date(2026, 10, 1)
        count = picker("attendance", day, "ncr bamnoli dc", "8 Hrs + Adherence",
                       (day, day, ["North"], ["DC"], ["ncr bamnoli dc"]))
        self.assertEqual(count, 164)
        self.assertEqual(calls, [("session_database", "attendance", day, day,
                                  ["North"], ["DC"], ["ncr bamnoli dc"], ["8 Hours +"])])

    def test_zero_is_a_real_count_not_a_missing_value(self):
        def query(*args):
            self.assertEqual(args[1], "flex_working")
            self.assertEqual(args[-1], ["8 Hours+"])
            return FakeFrame(0)
        picker = isolated_count_lookup(query)
        day = date(2026, 10, 6)
        self.assertEqual(picker("flex_working", day, "nagpur dc", "8 Hrs + Adherence",
                                (day, day, [], [], [])), 0)

    def test_missing_summary_count_stays_missing_not_estimated(self):
        picker = isolated_count_lookup(lambda *args: FakeFrame())
        day = date(2026, 10, 1)
        self.assertIsNone(picker("attendance", day, "unknown xd", "8 Hrs + Adherence",
                                 (day, day, [], [], [])))
        self.assertIsNone(picker("attendance", day, "unknown xd", "Other",
                                 (day, day, [], [], [])))

    def test_both_actual_popup_payloads_call_the_same_lookup_helper(self):
        def all_functions(node):
            return [n for n in ast.walk(node) if isinstance(n, ast.FunctionDef)]
        for section, name in (("attendance", "render_attendance"), ("flex_working", "render_flex")):
            outer = next(n for n in APP_TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
            nested = [n for n in all_functions(outer) if n.name == "payload"]
            self.assertEqual(len(nested), 1)
            calls = [n for n in ast.walk(nested[0]) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == "chart_point_count"]
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0].args[0].value, section)
        self.assertIn('"—" if count is None else f"{int(count):,}"', APP_SOURCE)

    def test_landing_paragraph_has_explicit_center_alignment(self):
        css = (ROOT / "theme.py").read_text(encoding="utf-8")
        self.assertIn('.bau-empty-state p.bau-empty-description', css)
        self.assertIn('text-align: center !important;', css)
        self.assertIn('margin: 0 auto;', css)
        self.assertIn('<p class="bau-empty-description">Please upload your reports', APP_SOURCE)


if __name__ == "__main__":
    unittest.main()
