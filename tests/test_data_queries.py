"""Focused smoke/regression tests for the Pandas -> Polars switch.

Run after installing dependencies: python -m unittest test_polars_migration.py
No real employee records or BAU workbooks are required.
"""
from __future__ import annotations

import ast
import tempfile
import unittest
from datetime import date
from pathlib import Path

import polars as pl
import plotly.express as px

import db
from onboarding_breakdown import query_hr_site_counts

ROOT = Path(__file__).resolve().parent.parent


def summary(section, day, site, type_, metric, value, unit="count"):
    return {
        "section": section, "data_date": day, "site_key": db.normalize_site(site),
        "site": site, "facility_type": type_, "metric": metric, "value": value,
        "unit": unit, "source_file": "synthetic.xlsx",
    }


def pivot_helper():
    # Load ONLY the pure pivot helper from app.py: import app.py would start Streamlit.
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "pivot_site_metrics")
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    scope = {"pl": pl}
    exec(compile(module, "app.py", "exec"), scope)
    return scope["pivot_site_metrics"]


class PolarsMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dbpath = Path(self.tmp.name) / "test.db"
        db.init_db(self.dbpath)
        db.upsert_sites(self.dbpath, [
            ("Example DC", "DC", "North"), ("New XD", "XD", None),
        ])
        db.replace_summary_rows(self.dbpath, [
            summary("attendance", "2026-10-07", "Example DC", "DC", "8 Hrs + Adherence", 80, "percent"),
            summary("attendance", "2026-10-08", "Example DC", "DC", "8 Hrs + Adherence", 90, "percent"),
            summary("attendance", "2026-10-08", "New XD", "XD", "8 Hrs + Adherence", 70, "percent"),
            summary("roster", "2026-10-07", "Example DC", "DC", "Active HC", 20),
            summary("roster", "2026-10-07", "Example DC", "DC", "Rostered HC", 16),
            summary("roster", "2026-10-07", "Example DC", "DC", "Roster Match", 12),
            summary("roster", "2026-10-08", "Example DC", "DC", "Active HC", 10),
            summary("roster", "2026-10-08", "Example DC", "DC", "Rostered HC", 8),
            summary("roster", "2026-10-08", "Example DC", "DC", "Roster Match", 6),
        ])

    def test_query_summary_date_filters_and_polars_type(self):
        result = db.query_summary(
            self.dbpath, "attendance", date(2026, 10, 7), date(2026, 10, 8),
            ["North"], ["DC"], [db.normalize_site("Example DC")], ["8 Hrs + Adherence"],
        )
        self.assertIsInstance(result, pl.DataFrame)
        self.assertEqual(result.height, 2)
        self.assertEqual(result.schema["data_date"], pl.Date)
        self.assertEqual(result.get_column("value").to_list(), [80.0, 90.0])
        self.assertEqual(result.get_column("data_date")[0], date(2026, 10, 7))
        self.assertTrue(db.query_summary(self.dbpath, "attendance", date(2026, 10, 8), date(2026, 10, 8), ["South"], []).is_empty())

    def test_region_editor_round_trip_and_preservation(self):
        mapping = db.get_site_mapping(self.dbpath)
        self.assertIsInstance(mapping, pl.DataFrame)
        self.assertEqual(mapping.filter(pl.col("Region") == "UNASSIGNED").height, 1)
        # Exactly the same Arrow conversion used by the Streamlit editor.
        after_arrow = pl.from_arrow(mapping.to_arrow())
        assigned = after_arrow.with_columns(
            pl.when(pl.col("site_key") == "new xd").then(pl.lit("West"))
              .otherwise(pl.col("Region")).alias("Region")
        )
        db.save_site_mapping(self.dbpath, assigned)
        db.upsert_sites(self.dbpath, [("New XD", "XD", "East")])
        result = db.get_site_mapping(self.dbpath)
        self.assertEqual(result.filter(pl.col("site_key") == "new xd").get_column("Region")[0], "West")

    def test_available_sites_and_import_history(self):
        sites = db.available_sites(self.dbpath, ["North"], ["DC"])
        self.assertEqual(sites.get_column("site").to_list(), ["Example DC"])
        db.add_import_history(self.dbpath, "Attendance", "synthetic.xlsx", ["2026-10-07"], 3, 0)
        history = db.get_import_history(self.dbpath, 4)
        self.assertIsInstance(history, pl.DataFrame)
        self.assertEqual(history.row(0, named=True)["Report"], "Attendance")

    def test_site_metric_pivot_sums_multiple_days_and_missing_metrics(self):
        frame = db.query_summary(self.dbpath, "roster", date(2026, 10, 7), date(2026, 10, 8), [], [])
        pivot = pivot_helper()(frame, ["Active HC", "Rostered HC", "Roster Match", "Missing"])
        row = pivot.row(0, named=True)
        self.assertEqual((row["Active HC"], row["Rostered HC"], row["Roster Match"]), (30, 24, 18))
        self.assertEqual(row["Missing"], 0)
        self.assertTrue(all(x is not None for x in pivot.get_column("Missing")))

    def test_hr_site_breakdown_sorted_grouped_and_filtered(self):
        records = [
            {"date": "2026-10-08", "site_key": "example dc", "site": "Example DC", "facility_type": "DC", "hr": "HR A", "method": "Aadhar", "count": 3},
            {"date": "2026-10-08", "site_key": "example dc", "site": "Example DC", "facility_type": "DC", "hr": "HR A", "method": "Aadhar", "count": 2},
            {"date": "2026-10-08", "site_key": "new xd", "site": "New XD", "facility_type": "XD", "hr": "HR B", "method": "Manual", "count": 2},
        ]
        frame = query_hr_site_counts(
            records, date(2026, 10, 8), date(2026, 10, 8), "Aadhar",
            ["North"], ["DC"], [], db.get_site_mapping(self.dbpath),
        )
        self.assertEqual(frame.columns, ["Site HR", "Site", "Count"])
        self.assertEqual(frame.to_dicts(), [{"Site HR": "HR A", "Site": "Example DC", "Count": 5}])
        blank = query_hr_site_counts(records, date(2026, 10, 8), date(2026, 10, 8), "Manual", ["North"], ["DC"], [], db.get_site_mapping(self.dbpath))
        self.assertTrue(blank.is_empty())

    def test_plotly_express_with_polars_date_and_site_metrics(self):
        df = db.query_summary(self.dbpath, "attendance", date(2026, 10, 7), date(2026, 10, 8), [], [], metrics=["8 Hrs + Adherence"])
        fig = px.line(df, x="data_date", y="value", color="site", markers=True, custom_data=["site_key", "site", "metric"])
        self.assertGreaterEqual(len(fig.data), 2)
        self.assertEqual(sum(len(trace.x) for trace in fig.data), 3)


if __name__ == "__main__":
    unittest.main()
