"""19 Oct Flex UX regression checks using synthetic data only.

The AST-isolated tests work without Streamlit or Polars and exercise the actual
Flex helper/branching code. A separate native-Polars check runs when installed.
"""
from __future__ import annotations

import ast
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")
APP_TREE = ast.parse(APP)
METRICS = ast.parse((ROOT / "flex_metrics.py").read_text(encoding="utf-8"))


def isolated_function(tree: ast.Module, name: str, scope: dict):
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
    exec(compile(module, f"<isolated {name}>", "exec"), scope)
    return scope[name]


class ColumnExpression:
    """Tiny expression interpreter for the filter predicate in one pure helper."""
    def __init__(self, fn):
        self.fn = fn

    def __eq__(self, value):
        return ColumnExpression(lambda row: self.fn(row) == value)

    def __gt__(self, value):
        return ColumnExpression(lambda row: self.fn(row) > value)

    def __and__(self, other):
        return ColumnExpression(lambda row: self.fn(row) and other.fn(row))

    def is_not_null(self):
        return ColumnExpression(lambda row: self.fn(row) is not None)


class Rows:
    def __init__(self, values):
        self.values = [dict(r) for r in values]

    def is_empty(self):
        return not self.values

    def head(self, count):
        return Rows(self.values[:count])

    def filter(self, expression):
        return Rows([row for row in self.values if expression.fn(row)])

    def select(self, names):
        return Rows([{name: row[name] for name in names} for row in self.values])

    def unique(self):
        seen = set()
        unique = []
        for row in self.values:
            key = tuple(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return Rows(unique)

    def join(self, right, on, how):
        assert how == "inner"
        keys = {tuple(row[column] for column in on) for row in right.values}
        return Rows([row for row in self.values if tuple(row[column] for column in on) in keys])

    def sort(self, columns):
        return Rows(sorted(self.values, key=lambda row: tuple(row[column] for column in columns)))

    def to_dicts(self):
        return [dict(row) for row in self.values]


class FlexTrendFiltering(unittest.TestCase):
    def setUp(self):
        self.filter_data = isolated_function(METRICS, "flex_working_on_used_days", {
            "pl": SimpleNamespace(DataFrame=Rows, col=lambda column: ColumnExpression(lambda row: row[column])),
        })

    def test_skips_yesterday_without_inserting_fake_100_percent(self):
        first, middle, last = [date(2026, 10, day) for day in (17, 18, 19)]
        working = Rows([
            {"site": "Site A", "site_key": "site a", "data_date": first, "value": 83.0},
            {"site": "Site A", "site_key": "site a", "data_date": middle, "value": 100.0},
            {"site": "Site A", "site_key": "site a", "data_date": last, "value": 91.0},
            {"site": "Site B", "site_key": "site b", "data_date": middle, "value": 75.0},
            {"site": "Site B", "site_key": "site b", "data_date": last, "value": 100.0},
        ])
        used = Rows([
            {"site_key": "site a", "data_date": first, "metric": "Total Flex Used", "value": 6},
            {"site_key": "site a", "data_date": middle, "metric": "Total Flex Used", "value": 0},
            {"site_key": "site a", "data_date": last, "metric": "Total Flex Used", "value": 3},
            {"site_key": "site b", "data_date": middle, "metric": "Total Flex Used", "value": 2},
            {"site_key": "site b", "data_date": last, "metric": "Total Flex Used", "value": 0},
        ])
        result = self.filter_data(working, used).to_dicts()
        self.assertEqual([(r["site_key"], r["data_date"], r["value"]) for r in result], [
            ("site a", first, 83.0), ("site a", last, 91.0), ("site b", middle, 75.0),
        ])
        # No in-place mutation; plotted data is a filtered view of official values.
        self.assertEqual(len(working.values), 5)
        self.assertEqual(len(used.values), 5)
        # Plotly draws ONE line with two observed markers, directly from
        # 17 to 19 Oct; the 18 Oct 100% is not a plotted point.
        import plotly.express as px
        chart = px.line(result, x="data_date", y="value", color="site", markers=True)
        site_a = next(trace for trace in chart.data if trace.name == "Site A")
        self.assertEqual(list(site_a.x), [first, last])
        self.assertEqual(list(site_a.y), [83.0, 91.0])
        self.assertEqual(site_a.mode, "lines+markers")

    def test_missing_null_negative_and_wrong_metric_do_not_create_points(self):
        day = date(2026, 10, 19)
        working = Rows([
            {"site_key": site, "site": site, "data_date": day, "value": 100.0}
            for site in ("missing", "null", "negative", "wrong-metric", "valid")
        ])
        used = Rows([
            {"site_key": "null", "data_date": day, "metric": "Total Flex Used", "value": None},
            {"site_key": "negative", "data_date": day, "metric": "Total Flex Used", "value": -1},
            {"site_key": "wrong-metric", "data_date": day, "metric": "Other", "value": 1},
            {"site_key": "valid", "data_date": day, "metric": "Total Flex Used", "value": 1},
            {"site_key": "valid", "data_date": day, "metric": "Total Flex Used", "value": 1},
        ])
        rows = self.filter_data(working, used).to_dicts()
        self.assertEqual([row["site_key"] for row in rows], ["valid"])

    def test_empty_source_gives_empty_result(self):
        working = Rows([{"site_key": "s", "site": "S", "data_date": date(2026, 10, 19), "value": 100}])
        self.assertEqual(self.filter_data(working, Rows([])).to_dicts(), [])
        self.assertEqual(self.filter_data(Rows([]), Rows([])).to_dicts(), [])


class FlexScopeAndDateUI(unittest.TestCase):
    def test_neither_site_nor_region_shows_prompt_but_both_scope_modes_work(self):
        events = []
        fake_st = SimpleNamespace(
            session_state={}, container=lambda **kwargs: nullcontext(),
            markdown=lambda *a, **k: None,
            info=lambda message: events.append(("info", message)),
            selectbox=lambda *a, **k: "8 Hrs + Adherence",
        )
        def filtered(section, filters, metrics):
            events.append(("query", section, tuple(filters[2]), tuple(filters[4])))
            return Rows([])
        scope = {
            "st": fake_st,
            "FLEX_WORKING_OPTIONS": ["8 Hrs + Adherence"],
            "filtered": filtered,
            "render_flex_scope_prompt": lambda: events.append(("prompt",)),
            "render_flex_usage_empty_state": lambda _: events.append(("empty",)),
            "flex_source_metrics": lambda _: ["8 Hrs+ Adherence"],
            "derive_flex_working_metric": lambda source, metric: source,
            "flex_working_on_used_days": lambda working, used: working,
        }
        render = isolated_function(APP_TREE, "render_flex", scope)
        for region, sites, expect_prompt in [
            ([], [], True),
            ([], ["site a"], False),
            ([], ["site a", "site b"], False),
            (["North"], [], False),
        ]:
            events.clear()
            render((date(2026, 10, 1), date(2026, 10, 19), region, [], sites), {"flex_usage": True})
            self.assertEqual(("prompt",) in events, expect_prompt)
            self.assertEqual(("empty",) in events, not expect_prompt)
            # When a site or region is selected, Flex Used is actually queried.
            # The second (working hours) graph queries both source domains.
            flex_queries = [e for e in events if e[:2] == ("query", "flex_usage")]
            self.assertEqual(len(flex_queries), 1 if expect_prompt else 2)
            self.assertIn(("query", "flex_working", tuple(region), tuple(sites)), events)

    def test_selected_sites_render_actual_flex_bars_without_region(self):
        day = date(2026, 10, 19)
        result_rows = []
        requested_scopes = []
        class Values:
            def __init__(self, items):
                self.items = list(items)
            def to_list(self):
                return self.items
        class Pivot:
            def __init__(self, selected):
                self.selected = selected
            def get_column(self, name):
                assert name == "site"
                return Values([s.title() for s in self.selected])
            def iter_rows(self, named=False):
                assert named
                return iter([{
                    "site_key": site, "site": site.title(),
                    "Total Flex Used": 3.0,
                    "Onboarded & Punched": 2.0,
                    "Onboarded & Not Punched": 1.0,
                    "Not Onboarded": 0.0,
                } for site in self.selected])
        selected_scope = []
        def filtered(section, filters, metrics):
            if section == "flex_usage" and metrics[0] == "Total Flex Used" and len(metrics) == 4:
                selected_scope[:] = filters[4]
                requested_scopes.append(tuple(selected_scope))
                return Rows([{
                    "site_key": site, "site": site.title(),
                    "metric": "Total Flex Used", "value": 3, "data_date": day,
                } for site in selected_scope])
            return Rows([])
        fake_st = SimpleNamespace(
            session_state={}, container=lambda **kwargs: nullcontext(),
            markdown=lambda *a, **k: None,
            columns=lambda widths, **kwargs: [nullcontext() for _ in widths],
            selectbox=lambda *a, **k: "8 Hrs + Adherence",
            info=lambda *a: None,
        )
        scope = {
            "st": fake_st,
            "pl": SimpleNamespace(col=lambda name: ColumnExpression(lambda row: row[name])),
            "FLEX_WORKING_OPTIONS": ["8 Hrs + Adherence"],
            "filtered": filtered,
            "render_flex_scope_prompt": lambda: self.fail("Site selection should bypass prompt"),
            "render_flex_usage_empty_state": lambda _: self.fail("Site selection should yield usage"),
            "select_report_day": lambda *a: day,
            "pivot_site_metrics": lambda frame, _: Pivot([r["site_key"] for r in frame.values]),
            "site_color_map": lambda sites, db_path: {site: "#346788" for site in sites},
            "flex_site_shades": lambda color: (color, color, color),
            "render_flex_usage_chart": lambda rows: result_rows.append(rows) or None,
            "SETTINGS_DB_PATH": "site-registry",
            "flex_source_metrics": lambda _: ["8 Hrs+ Adherence"],
            "derive_flex_working_metric": lambda raw, metric: raw,
            "flex_working_on_used_days": lambda working, used: working,
        }
        render = isolated_function(APP_TREE, "render_flex", scope)
        for sites in (["site a"], ["site a", "site b"]):
            render((day, day, [], [], sites), {"flex_usage": True})
            self.assertEqual(len(result_rows[-1]), len(sites))
            self.assertEqual([r["site_key"] for r in result_rows[-1]], sites)
            self.assertTrue(all(row["total"] == 3.0 for row in result_rows[-1]))
        self.assertEqual(requested_scopes, [("site a",), ("site a", "site b")])

    def test_site_only_filters_are_forwarded_to_summary_query(self):
        calls = []
        def query(*args):
            calls.append(args)
            return "site records"
        fn = isolated_function(APP_TREE, "filtered", {"query_summary": query, "DB_PATH": "in-memory"})
        day = date(2026, 10, 19)
        self.assertEqual(fn("flex_usage", (day, day, [], [], ["site a", "site b"]), ["Total Flex Used"]), "site records")
        self.assertEqual(calls[0][4], [])  # No region requirement.
        self.assertEqual(calls[0][6], ["site a", "site b"])

    def test_roster_date_is_preserved_and_flex_working_date_checkbox_gone(self):
        render_roster = next(x for x in APP_TREE.body if isinstance(x, ast.FunctionDef) and x.name == "render_roster")
        roster_text = ast.get_source_segment(APP, render_roster)
        self.assertIn('"Roster date", "roster_single_day"', roster_text)
        render_flex = next(x for x in APP_TREE.body if isinstance(x, ast.FunctionDef) and x.name == "render_flex")
        flex_text = ast.get_source_segment(APP, render_flex)
        self.assertIn('"Flex Used date", "flex_usage_single_day"', flex_text)
        self.assertNotIn("st.checkbox(", flex_text)
        self.assertNotIn("flex_working_single_day", flex_text)
        self.assertNotIn("px.scatter(", flex_text)
        self.assertIn("px.line(", flex_text)
        self.assertIn('coerce_date(p.get("x"))', flex_text)


try:
    import polars as pl
    from flex_metrics import flex_working_on_used_days
except ImportError:
    pl = None


@unittest.skipUnless(pl is not None, "Polars not installed in offline environment")
class NativePolarsCompatibility(unittest.TestCase):
    def test_native_dataframe_join_skips_only_same_site_zero_usage(self):
        working = pl.DataFrame([
            {"site": "A", "site_key": "a", "data_date": date(2026, 10, 17), "value": 70.0},
            {"site": "A", "site_key": "a", "data_date": date(2026, 10, 18), "value": 100.0},
            {"site": "A", "site_key": "a", "data_date": date(2026, 10, 19), "value": 90.0},
        ])
        usage = pl.DataFrame([
            {"site_key": "a", "data_date": date(2026, 10, 17), "metric": "Total Flex Used", "value": 2.0},
            {"site_key": "a", "data_date": date(2026, 10, 18), "metric": "Total Flex Used", "value": 0.0},
            {"site_key": "a", "data_date": date(2026, 10, 19), "metric": "Total Flex Used", "value": 3.0},
        ])
        actual = flex_working_on_used_days(working, usage)
        self.assertEqual(actual.get_column("data_date").to_list(), [date(2026, 10, 17), date(2026, 10, 19)])
        self.assertEqual(actual.get_column("value").to_list(), [70.0, 90.0])


if __name__ == "__main__":
    unittest.main()
