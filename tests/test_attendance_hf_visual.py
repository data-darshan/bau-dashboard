"""Run: python -m unittest test_attendance_hf_visual.py
Pure-Python presentation tests. Synthetic data only; no personnel exports.
"""
from __future__ import annotations

import csv
import io
import unittest
from html.parser import HTMLParser
from pathlib import Path

from attendance_hf_table import (
    EXISTING_DETAIL_COLUMNS,
    attendance_hf_csv,
    attendance_hf_html,
    partition_5_to_8_hour_rows,
)


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = None
        self.in_row = False
        self.row_count = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.current_table = dict(attrs)
            self.tables.append(self.current_table)
        if tag == "tr" and self.current_table is not None:
            self.in_row = True

    def handle_endtag(self, tag):
        if tag == "table":
            self.current_table = None
        if tag == "tr":
            if self.current_table is not None and self.in_row:
                self.row_count += 1
            self.in_row = False


def row(employee, hours, *, total=9.0, name=None):
    return {
        "Employee ID": employee,
        "Employee Name": name or f"Demo {employee}",
        "Role": "Picker",
        "Shift": "Morning",
        "Working Hours": hours,
        "Total Hours": total,  # Must never drive the threshold or CSV columns.
    }


class FiveToEightVisualTests(unittest.TestCase):
    def test_exact_cutoff_actual_hours_and_descending(self):
        source = [
            row("below", 7.69, total=15),
            row("above", 7.99, total=8),
            row("exact", 7.7, total=5),
            row("middle", 7.81, total=10),
            row("low", 5.01, total=11),
        ]
        near, normal = partition_5_to_8_hour_rows(source)
        self.assertEqual([r["Employee ID"] for r in near], ["above", "middle", "exact"])
        self.assertEqual([r["Employee ID"] for r in normal], ["below", "low"])
        self.assertEqual([r["Employee ID"] for r in source], ["below", "above", "exact", "middle", "low"])

    def test_missing_and_bad_hours_not_flagged_as_ok(self):
        near, normal = partition_5_to_8_hour_rows([
            row("missing", None), row("nan", float("nan")),
            row("bad", "invalid"), row("near", 7.75), row("low", 7.5),
        ])
        self.assertEqual([r["Employee ID"] for r in near], ["near"])
        self.assertEqual([r["Employee ID"] for r in normal], ["low", "missing", "nan", "bad"])

    def test_green_dashed_and_black_solid_visual_groups(self):
        near, normal = partition_5_to_8_hour_rows([row("green", 7.9), row("regular", 6.4)])
        html = attendance_hf_html(near, normal)
        self.assertIn("border-top: 2px dashed #008A71", html)
        self.assertIn("border-left: 2px dashed #008A71", html)
        self.assertIn("border-top: 1px solid #231F20", html)
        self.assertIn("Actual Working Hours", html)
        parser = TableParser()
        parser.feed(html)
        self.assertEqual(len(parser.tables), 2)
        self.assertIn("bau-hf-green", parser.tables[0]["class"])
        self.assertIn("bau-hf-normal", parser.tables[1]["class"])
        self.assertEqual(parser.row_count, 4)  # 1 header + 1 employee per table
        self.assertLess(html.index("Demo green"), html.index("Demo regular"))

    def test_escapes_names_and_ids_as_html(self):
        records = [row("<fake&id>", 7.8, name="<img src=x onerror=alert(1)>")]
        near, normal = partition_5_to_8_hour_rows(records)
        html = attendance_hf_html(near, normal)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertIn("&lt;fake&amp;id&gt;", html)

    def test_csv_contains_existing_five_columns_only_and_is_sorted(self):
        near, normal = partition_5_to_8_hour_rows([
            row("a", 5.9, total=14), row("b", 7.8, total=10), row("c", 7.7, total=10)
        ])
        data = attendance_hf_csv(near, normal)
        reader = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
        self.assertEqual(reader.fieldnames, list(EXISTING_DETAIL_COLUMNS))
        lines = list(reader)
        self.assertEqual([r["Employee ID"] for r in lines], ["b", "c", "a"])
        self.assertEqual([r["Working Hours"] for r in lines], ["7.8", "7.7", "5.9"])
        self.assertFalse(any("Total Hours" in r for r in lines))

    def test_only_hf_branch_is_replaced_in_app(self):
        app = (Path(__file__).resolve().parent.parent / "app.py").read_text()
        self.assertIn('if status == "HF":', app)
        self.assertIn('partition_5_to_8_hour_rows(detail.iter_rows(named=True))', app)
        self.assertIn("attendance_hf_html(near, remaining)", app)
        self.assertIn("attendance_hf_csv(near, remaining)", app)
        self.assertIn('else:\n            st.html(detail_frame_html(detail))', app)
        # Existing site and date limited query is still used.
        self.assertIn('attendance_detail_for(DB_PATH, data_date, payload["site_key"], status)', app)


if __name__ == "__main__":
    unittest.main()
