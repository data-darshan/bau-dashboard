"""Manager-requested presentation improvements. Synthetic records only."""
from __future__ import annotations

import ast
import unittest
from datetime import date
from pathlib import Path

from chart_formatting import percentage_hover_template
from roster_layers import _bar_label_positions, roster_grouped_figure, roster_coverage_rows

ROOT = Path(__file__).resolve().parent.parent


def sample(site, active, rostered, matched):
    return [
        dict(site=site, site_key=site.casefold(), metric=name, value=value)
        for name, value in zip(
            ('Active HC', 'Rostered HC', 'Roster Match', 'Roster Adoption', 'Roster Adherence'),
            (active, rostered, matched,
             100 * rostered / active if active else 0,
             100 * matched / rostered if rostered else 0),
        )
    ]


class ManagerChartTests(unittest.TestCase):
    def test_bars_keep_counts_and_imported_official_percentages(self):
        records = sample('Large DC', 1973, 1595, 1292) + sample('Small XD', 1687, 1, 1)
        rows, excluded = roster_coverage_rows(records)
        self.assertFalse(excluded)
        fig = roster_grouped_figure(rows, date(2026, 10, 15))
        bar_values = [b.y[0] for b in fig.data if b.type == 'bar']
        self.assertEqual(bar_values, [1973, 1595, 1292, 1687, 1, 1])
        percentages = [t.text[0] for t in fig.data
                       if t.type == 'scatter' and t.mode == 'text' and t.text[0].endswith('%')]
        self.assertEqual(percentages, ['81%', '81%', '0%', '100%'])
        self.assertAlmostEqual(rows[0]['adoption_pct'], 100 * 1595 / 1973)
        self.assertAlmostEqual(rows[0]['adherence_pct'], 100 * 1292 / 1595)

    def test_percentages_at_bar_foot_for_tall_bars_and_in_gutter_for_short(self):
        mx = 2000
        for count in [400, 750, 2000]:
            spec = _bar_label_positions(count, mx, '#004D9F')
            self.assertGreater(spec['percentage_y'], 0)
            self.assertLess(spec['percentage_y'], count)
            self.assertGreaterEqual(spec['count_y'] - spec['percentage_y'], mx * .085)
        for count in [0, 1, 100, 199, 399]:
            spec = _bar_label_positions(count, mx, '#004D9F')
            self.assertLess(spec['percentage_y'], 0)
            self.assertGreater(spec['count_y'], 0)
            self.assertGreater(spec['count_y'] - spec['percentage_y'], mx * .055)

    def test_no_collapsing_roster_labels_and_extra_lower_axis_space(self):
        rows, _ = roster_coverage_rows(sample('Large DC', 2000, 1500, 1000)
                                        + sample('Tiny XD', 12, 1, 0))
        fig = roster_grouped_figure(rows, date(2026, 10, 15))
        self.assertLess(fig.layout.yaxis.range[0], 0)
        self.assertGreater(fig.layout.yaxis.range[1], 2000)
        texts = [t for t in fig.data if t.type == 'scatter' and t.mode == 'text']
        for label in texts:
            self.assertTrue(label.cliponaxis is False)
        self.assertEqual(sum(t.text[0] == '0%' for t in texts), 1)
        self.assertEqual(sum(t.text[0] == '0' for t in texts), 1)
        self.assertIn('%{customdata[5]}', [b for b in fig.data if b.type == 'bar'][0].hovertemplate)

    def test_percentage_hover_formatter_escapes_metric_and_preserves_raw_y(self):
        self.assertIn('%{y:.0f}%', percentage_hover_template('Single Punch %'))
        self.assertIn('%{x|%d %b %Y}', percentage_hover_template('Single Punch %'))
        self.assertIn('&lt;5 Hrs Adherence', percentage_hover_template('<5 Hrs Adherence'))
        day_view = percentage_hover_template('8 Hrs + Adherence', by_site=True,
                                            report_day=date(2026, 10, 15))
        self.assertIn('15 Oct 2026', day_view)
        self.assertNotIn('%{x|', day_view)
        with self.assertRaises(ValueError):
            percentage_hover_template('Metric', by_site=True)

    def test_onboarding_precision_unchanged_and_all_metric_tooltips_formatted(self):
        app = (ROOT / 'app.py').read_text()
        donut = (ROOT / 'onboarding_donut.py').read_text()
        self.assertIn('while (decimals < 10', donut)
        self.assertIn('fig.update_traces(hovertemplate=percentage_hover_template(metric))', app)
        self.assertNotIn('hovertemplate=percentage_hover_template(metric, by_site=True', app)
        self.assertEqual(app.count('hovertemplate=percentage_hover_template(metric)'), 2)
        roster = (ROOT / 'roster_layers.py').read_text()
        self.assertIn('Roster Adoption: %{customdata[4]}', roster)
        self.assertIn('Roster Adherence: %{customdata[5]} of Rostered HC', roster)
        self.assertIn('_reported_percentage_label(row.get(', roster)
        self.assertNotIn('100 * match / rostered', roster)
        self.assertNotIn('Roster Adherence: %{customdata[5]:.1f}%', roster)

    def test_nav_does_not_obscure_heading_and_typography_is_consistent(self):
        css = (ROOT / 'theme.py').read_text()
        app = (ROOT / 'app.py').read_text()
        self.assertIn('[data-testid="stMain"] .block-container', css)
        self.assertIn('padding: 4.65rem', css)
        self.assertIn('@media (max-width: 768px)', css)
        self.assertIn('padding: 5rem 1rem', css)
        self.assertIn('initial_sidebar_state="auto"', app)
        self.assertIn('render_page_header("Management Dashboard"', app)
        self.assertIn('render_page_header("Settings"', app)
        self.assertIn('class="bau-page-header"', app)


if __name__ == '__main__':
    unittest.main()
