"""Regression tests: Hyperverge RED bars retain site order after dialog reruns.

These tests are deliberately limited to ordering.  All counts, date/region/site
filters, direct-click chart, and detail popup continue using V7.3 behavior.
"""
from __future__ import annotations

import ast
from itertools import permutations
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent.parent
APP = BASE / "app.py"
CHART = BASE / "onboarding_red_chart.py"


def red_sort_spec() -> tuple[list[str], list[bool]]:
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    render = next(
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "render_onboarding"
    )
    # The RED metric aggregation is the only sort in render_onboarding.
    sorts = [
        n for n in ast.walk(render)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "sort"
    ]
    if len(sorts) != 1:
        raise AssertionError(f"Expected one Hyperverge RED sort, got {len(sorts)}")
    sort = sorts[0]
    cols = ast.literal_eval(sort.args[0])
    descending_kw = next(k.value for k in sort.keywords if k.arg == "descending")
    return cols, ast.literal_eval(descending_kw)


class RedChartOrderingV74Tests(unittest.TestCase):
    def test_sort_prioritizes_count_then_stable_site_keys(self):
        self.assertEqual(
            red_sort_spec(),
            (["value", "site_key", "site"], [True, False, False]),
        )

    def test_screenshot_three_tied_sites_have_one_stable_order(self):
        # Browser reruns can produce any permutation before sorting.
        sites = [
            {"site": "Patna DC", "site_key": "patna dc", "value": 1},
            {"site": "NCR Bamnoli DC", "site_key": "ncr bamnoli dc", "value": 1},
            {"site": "ONE NCR DC", "site_key": "one ncr dc", "value": 1},
        ]
        expected = ["NCR Bamnoli DC", "ONE NCR DC", "Patna DC"]
        # Express the exact ascending tie-breaker demanded by the sort spec.
        keys, descending = red_sort_spec()
        self.assertEqual(keys, ["value", "site_key", "site"])
        self.assertEqual(descending, [True, False, False])
        for items in permutations(sites):
            ordered = sorted(items, key=lambda r: (-r["value"], r["site_key"], r["site"]))
            self.assertEqual([x["site"] for x in ordered], expected)

    def test_count_remains_primary(self):
        sites = [
            {"site": "Z Site", "site_key": "z site", "value": 3},
            {"site": "A Site", "site_key": "a site", "value": 1},
            {"site": "B Site", "site_key": "b site", "value": 3},
        ]
        expected = ["B Site", "Z Site", "A Site"]
        for items in permutations(sites):
            actual = sorted(items, key=lambda r: (-r["value"], r["site_key"], r["site"]))
            self.assertEqual([x["site"] for x in actual], expected)

    def test_click_order_is_taken_from_input_not_resorted_in_js(self):
        script = CHART.read_text(encoding="utf-8")
        self.assertIn("points.forEach((point, i)", script)
        self.assertNotIn("points.sort(", script)
        self.assertIn("setTriggerValue('site_key', point.site_key)", script)

    def test_existing_popup_filters_are_untouched(self):
        app = APP.read_text(encoding="utf-8")
        self.assertIn('dfrom, dto, *_ = filters', app)
        self.assertIn('hyperverge_red_direct_payload(', app)
        self.assertIn('st.session_state.pending_dialog = payload', app)
        self.assertIn('onboarding_red_for(DB_PATH, payload["from"], payload["to"], payload["site_key"])', app)

    def test_actual_polars_ordering_if_installed(self):
        try:
            import polars as pl
        except ImportError:
            self.skipTest("Polars not installed in this packaging environment; run this test in Streamlit environment")
        samples = [
            {"site": "Patna DC", "site_key": "patna dc", "value": 1.0},
            {"site": "NCR Bamnoli DC", "site_key": "ncr bamnoli dc", "value": 1.0},
            {"site": "ONE NCR DC", "site_key": "one ncr dc", "value": 1.0},
        ]
        cols, descending = red_sort_spec()
        for perm in permutations(samples):
            df = pl.DataFrame(list(perm))
            agg = (
                df.group_by(["site_key", "site"])
                .agg(pl.col("value").sum())
                .sort(cols, descending=descending)
                .filter(pl.col("value") > 0)
            )
            self.assertEqual(
                agg.get_column("site").to_list(),
                ["NCR Bamnoli DC", "ONE NCR DC", "Patna DC"],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
