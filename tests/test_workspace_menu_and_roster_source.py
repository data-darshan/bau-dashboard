"""Regression checks: genuine WORKSPACE menu and direct report Roster percentages.

No real BAU workbook, employee data or running Streamlit server is required.
"""
from __future__ import annotations

import ast
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from roster_layers import roster_coverage_rows, roster_grouped_figure

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
CSS = (ROOT / "theme.py").read_text(encoding="utf-8")
TREE = ast.parse(APP)


class WorkspaceNavigationTests(unittest.TestCase):
    def test_no_radio_ui_and_six_menu_pages(self):
        self.assertNotIn("st.sidebar.radio(", APP)
        self.assertNotIn('data-testid="stRadio"', CSS)
        self.assertIn('st.sidebar.container(key="bau_workspace_nav")', APP)
        self.assertIn('NAV_PAGES = ("Dashboard", "Onboarding", "Attendance", "Roster", "Flex", "Settings")', APP)
        self.assertIn('type="primary" if page == st.session_state["nav_page"] else "secondary"', APP)
        self.assertIn('on_click=navigate_to,', APP)
        self.assertIn('args=(page,),', APP)
        self.assertIn('menu = st.session_state["nav_page"]', APP)

    def test_navigation_callback_sets_page_state(self):
        fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "navigate_to")
        module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
        state = {}
        env = {"st": SimpleNamespace(session_state=SimpleNamespace(nav_page="Dashboard"))}
        exec(compile(module, "app.py", "exec"), env)
        for page in ("Settings", "Roster", "Dashboard"):
            env["navigate_to"](page)
            self.assertEqual(env["st"].session_state.nav_page, page)

    def test_styling_is_scoped_menu_like_left_aligned_and_focus_accessible(self):
        self.assertIn('.st-key-bau_workspace_nav [data-testid="stButton"] button', CSS)
        self.assertIn('justify-content: flex-start;', CSS)
        self.assertIn('text-align: left;', CSS)
        self.assertIn('button[kind="primary"]', CSS)
        self.assertIn('button:focus-visible', CSS)
        # Keep the toolbar collision padding from the manager review.
        self.assertIn('padding: 4.65rem', CSS)
        self.assertIn('padding: 5rem 1rem', CSS)


class ReportBackedRosterTests(unittest.TestCase):
    def test_roster_query_requests_both_official_percentages(self):
        roster = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'render_roster')
        calls = [n for n in ast.walk(roster) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == 'filtered']
        self.assertEqual(len(calls), 1)
        requested = ast.literal_eval(calls[0].args[2])
        self.assertEqual(requested, ['Active HC', 'Rostered HC', 'Roster Match',
                                      'Roster Adoption', 'Roster Adherence'])

    def test_source_adherence_value_controls_bar_label_and_hover(self):
        source = {
            'Active HC': 561, 'Rostered HC': 198, 'Roster Match': 170,
            'Roster Adoption': 35.294117647058826,
            'Roster Adherence': 85.85858585858585,
        }
        data = [dict(site='OneSRT DC', site_key='onesrt dc', metric=k, value=v)
                for k, v in source.items()]
        rows, excluded = roster_coverage_rows(data)
        self.assertFalse(excluded)
        self.assertEqual(rows[0]['adherence_pct'], source['Roster Adherence'])
        fig = roster_grouped_figure(rows, date(2026, 10, 1))
        labels = [t.text[0] for t in fig.data if t.type == 'scatter' and t.mode == 'text']
        self.assertIn('86%', labels)
        self.assertIn('35%', labels)
        self.assertEqual(fig.data[4].customdata[0][5], '86%')
        self.assertEqual(fig.data[4].y[0], 170)
        self.assertIn('%{customdata[5]}', fig.data[4].hovertemplate)
        self.assertNotIn(':.0f', fig.data[4].hovertemplate)

    def test_missing_source_percentage_never_becomes_fabricated_zero(self):
        data = [dict(site='Site DC', site_key='site dc', metric=k, value=v) for k, v in [
            ('Active HC', 100), ('Rostered HC', 80), ('Roster Match', 60),
            ('Roster Adoption', 80),
        ]]
        rows, excluded = roster_coverage_rows(data)
        self.assertFalse(excluded)
        self.assertIsNone(rows[0]['adherence_pct'])
        fig = roster_grouped_figure(rows, date(2026, 10, 1))
        self.assertEqual(fig.data[4].customdata[0][5], '—')
        self.assertEqual([bar.y[0] for bar in fig.data if bar.type == 'bar'], [100, 80, 60])


if __name__ == '__main__':
    unittest.main()
