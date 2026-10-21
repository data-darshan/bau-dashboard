"""Roster V6 tests: stable colors shared with Attendance; no gray and no blue-only screenshots."""
from __future__ import annotations
import colorsys
import unittest
import re
from datetime import date
from pathlib import Path
from roster_layers import (
    ROSTER_VISUAL_VERSION, roster_coverage_rows, roster_grouped_figure,
    roster_page, roster_site_colors, site_shades, _legible_ink,
)
from site_palette import SITE_PALETTE_VERSION, ASSIGNED_SITE_COLORS, site_color, site_color_map


class RosterV6Tests(unittest.TestCase):
    @staticmethod
    def records(site='Kanpur XD', active=167, adopted=163, match=102):
        # The production chart consumes official percentages; synthetic tests
        # explicitly include their report columns, rather than relying on the
        # chart to derive percentages from counts.
        metrics = [
            ('Active HC', active), ('Rostered HC', adopted), ('Roster Match', match),
            ('Roster Adoption', 100 * adopted / active if active else 0),
            ('Roster Adherence', 100 * match / adopted if adopted else 0),
        ]
        return [dict(site=site, site_key=site.casefold(), metric=k, value=v)
                for k, v in metrics]

    def chart(self, records=None, colors=None):
        rows,errors=roster_coverage_rows(records if records is not None else self.records())
        self.assertFalse(errors)
        return roster_grouped_figure(rows,date(2026,10,8),colors or {'Kanpur XD':'#EF553B'})

    def test_version_marker(self):
        self.assertEqual(ROSTER_VISUAL_VERSION,'ROSTER_V6_ASSIGNED_SITE_PALETTE_20261012')
        self.assertEqual(SITE_PALETTE_VERSION,'SITE_PALETTE_V7_PERSISTENT_20261012')

    def test_count_coverage_values(self):
        rows,bad=roster_coverage_rows(self.records(active=200,adopted=160,match=110))
        self.assertFalse(bad)
        self.assertEqual(rows[0]['adoption_pct'],80)
        self.assertAlmostEqual(rows[0]['adherence_pct'],68.75)

    def test_imported_report_adherence_matches_this_workbooks_rostered_headcount(self):
        rows, invalid = roster_coverage_rows(self.records('Generic DC', active=561, adopted=198, match=170))
        self.assertFalse(invalid)
        self.assertAlmostEqual(rows[0]['adoption_pct'], 100*198/561)
        self.assertAlmostEqual(rows[0]['adherence_pct'], 100*170/198)
        self.assertNotAlmostEqual(rows[0]['adherence_pct'], 100*170/561)
        zero, bad = roster_coverage_rows(self.records('Empty DC', active=100, adopted=0, match=0))
        self.assertFalse(bad)
        self.assertEqual(zero[0]['adherence_pct'], 0)

    def test_official_percentages_override_any_count_based_estimate(self):
        values = self.records('Generic DC', active=200, adopted=160, match=110)
        for metric in values:
            if metric['metric'] == 'Roster Adherence':
                metric['value'] = 72.5  # source report, not 110 / 160 = 68.75
            if metric['metric'] == 'Roster Adoption':
                metric['value'] = 79.5  # source report, not 160 / 200 = 80
        rows, bad = roster_coverage_rows(values)
        self.assertFalse(bad)
        self.assertEqual(rows[0]['adherence_pct'], 72.5)
        self.assertEqual(rows[0]['adoption_pct'], 79.5)
        fig = roster_grouped_figure(rows, date(2026, 10, 1))
        labels = [t.text[0] for t in fig.data if t.type == 'scatter' and t.mode == 'text']
        self.assertIn('73%', labels)  # Excel-style halves up, not Python banker rounding
        self.assertIn('80%', labels)
        self.assertEqual(fig.data[2].customdata[0][5], '73%')
        self.assertEqual(fig.data[4].customdata[0][4], '80%')
        self.assertEqual([b.y[0] for b in fig.data if b.type == 'bar'], [200, 160, 110])

    def test_missing_report_percent_does_not_invent_zero_or_recompute(self):
        source = [v for v in self.records() if v['metric'] != 'Roster Adherence']
        rows, bad = roster_coverage_rows(source)
        self.assertFalse(bad)
        self.assertIsNone(rows[0]['adherence_pct'])
        chart = roster_grouped_figure(rows, date(2026, 10, 1))
        self.assertEqual(chart.data[4].customdata[0][5], '—')
        self.assertEqual(chart.data[-1].text[0], '—')
        self.assertEqual([b.y[0] for b in chart.data if b.type == 'bar'], [167, 163, 102])
        # An invalid reported percentage also stays unknown.
        bad_source = self.records()
        next(v for v in bad_source if v['metric'] == 'Roster Adherence')['value'] = float('nan')
        again, ignored = roster_coverage_rows(bad_source)
        self.assertFalse(ignored)
        self.assertIsNone(again[0]['adherence_pct'])

    def test_no_100_percent_background(self):
        fig=self.chart(self.records('Big DC',1973,1595,1292)+self.records('Small XD',167,163,102),
                       {'Big DC':'#006ACD','Small XD':'#EF7696'})
        bars=[t for t in fig.data if t.type=='bar']
        self.assertEqual([float(t.y[0]) for t in bars],[1973,1595,1292,167,163,102])
        self.assertEqual(fig.layout.yaxis.title.text,'Employees (headcount)')
        self.assertGreater(fig.layout.yaxis.range[1],1973)
        self.assertNotEqual(fig.layout.yaxis.range[1],100)

    def test_inner_bars_touch_with_no_gap(self):
        fig=self.chart()
        active,adoption,adherence=fig.data[1],fig.data[2],fig.data[4]
        self.assertEqual(fig.layout.barmode,'overlay')
        self.assertLess(adoption.x[0],active.x[0])
        self.assertGreater(adherence.x[0],active.x[0])
        self.assertAlmostEqual(adoption.x[0]+adoption.width/2,
                               adherence.x[0]-adherence.width/2,places=8)
        self.assertLess(active.width,1)
        self.assertGreater(active.width,adoption.width+adherence.width)

    def test_three_color_shades_are_the_same_hue(self):
        for color in ['#006ACD','#32CC70','#21B2A5','#FF8B00','#EF3030','#EF7696']:
            with self.subTest(color=color):
                fills=site_shades(color)
                self.assertEqual(len(set(fills)),3)
                hues=[]
                for shade in fills:
                    channels=tuple(int(shade[i:i+2],16)/255 for i in (1,3,5))
                    h,l,s=colorsys.rgb_to_hls(*channels)
                    hues.append(h)
                    self.assertGreater(s,0.6,'A neutral gray fill was generated')
                self.assertLess(max(hues)-min(hues),.025)

    def test_labels_are_scatter_text_not_hidden_bar_text(self):
        fig=self.chart()
        inner_labels=[fig.data[3],fig.data[5]]
        for t,label in zip(inner_labels,['163','102']):
            self.assertEqual(t.type,'scatter')
            self.assertEqual(t.mode,'text')
            self.assertEqual(t.text[0],label)
            self.assertEqual(t.textposition,'middle center')
            self.assertIsNone(t.hovertemplate)
        self.assertIsNone(fig.layout.uniformtext.mode)
        self.assertEqual(fig.data[6].text[0],'167')
        self.assertGreater(fig.data[6].y[0],167)
        self.assertEqual([t.text for t in fig.data if t.type=='bar'],[None,None,None])

    def test_labels_inside_count_values_even_for_large_bars(self):
        fig=self.chart(self.records('Big DC',1973,1595,1292),{'Big DC':'#006ACD'})
        for bar_idx,text_idx in [(2,3),(4,5)]:
            value=float(fig.data[bar_idx].y[0])
            position=float(fig.data[text_idx].y[0])
            self.assertGreater(position,0)
            self.assertLess(position,value)
        self.assertEqual(fig.data[3].text[0],'1,595')
        self.assertEqual(fig.data[5].text[0],'1,292')

    def test_zero_counts_marked_without_fake_headcount(self):
        fig=self.chart(self.records(active=1189,adopted=0,match=0))
        self.assertEqual(fig.data[2].y[0],0)
        self.assertEqual(fig.data[4].y[0],0)
        self.assertEqual(fig.data[3].text[0],'0')
        self.assertEqual(fig.data[5].text[0],'0')
        self.assertGreater(fig.data[3].y[0],0)

    def test_dark_ink_contrast(self):
        self.assertEqual(_legible_ink('#004387'),'#FFFFFF')
        self.assertEqual(_legible_ink('#6BFF92'),'#11263B')

    def test_full_hover_preserved(self):
        fig=self.chart()
        for bar in (fig.data[1],fig.data[2],fig.data[4]):
            self.assertIn('Active HC:',bar.hovertemplate)
            self.assertIn('Rostered HC:',bar.hovertemplate)
            self.assertIn('Roster Match:',bar.hovertemplate)
            self.assertIn('Roster Adoption:',bar.hovertemplate)
            self.assertIn('Roster Adherence: %{customdata[5]} of Rostered HC',bar.hovertemplate)

    def test_legend_controls_all_labels_and_bars(self):
        fig=self.chart()
        self.assertEqual({t.legendgroup for t in fig.data},{'Kanpur XD'})
        self.assertEqual(sum(t.showlegend is True for t in fig.data),1)
        self.assertEqual(fig.layout.legend.groupclick,'togglegroup')
        self.assertEqual(len(fig.data),9)  # original seven + two percentage labels

    def test_palette_is_shared_across_attendance_and_roster(self):
        names=['Kanpur XD','varanasi XD','ONE NCR DC','Mumbai DC']
        expected=site_color_map(names)
        actual=roster_site_colors([{'site':name} for name in reversed(names)])
        self.assertEqual(actual,expected)
        self.assertEqual(site_color('Kanpur  XD'),expected['Kanpur XD'])
        self.assertEqual(site_color('VAranasi XD'),expected['varanasi XD'])

    def test_attendance_and_roster_never_use_filtered_session_palette(self):
        app=(Path(__file__).resolve().parent.parent/'app.py').read_text()
        attendance=app.split('def render_attendance(',1)[1].split('def render_roster(',1)[0]
        roster=app.split('def render_roster(',1)[1].split('def render_flex(',1)[0]
        self.assertIn('color_discrete_map=site_color_map(',attendance)
        self.assertNotIn('attendance_site_palette',attendance)
        self.assertNotIn('attendance_site_palette',roster)
        self.assertIn('roster_grouped_figure(visible_rows, selected_day, db_path=SETTINGS_DB_PATH)',roster)
        self.assertIn('roster_v6_fixed_site_palette_20261012',roster)

    def test_no_invalid_snapshot_can_repaint_every_site_blue(self):
        names=['ONE NCR DC','Bangalore DC','NCR Bilaspur DC','Mumbai DC']
        wrong={name:'None' for name in names}
        rows=[{'site':name} for name in names]
        self.assertEqual(roster_site_colors(rows,wrong),site_color_map(names))
        self.assertGreater(len(set(roster_site_colors(rows,wrong).values())),1)

    def test_assignments_are_permanent_and_saturated(self):
        self.assertEqual(len(ASSIGNED_SITE_COLORS),64)
        self.assertEqual(len(set(ASSIGNED_SITE_COLORS.values())),64)
        self.assertEqual(site_color('Kanpur XD'),'#E63D43')
        self.assertEqual(site_color('varanasi XD'),'#189D9C')
        self.assertNotEqual(site_color('Vanaras XD'),site_color('varanasi XD'))
        for base in ASSIGNED_SITE_COLORS.values():
            rgb=tuple(int(base[i:i+2],16)/255 for i in (1,3,5))
            _,_,sat=colorsys.rgb_to_hls(*rgb)
            self.assertGreater(sat,.54)
        self.assertEqual(site_color('Newtown XD'),site_color('newtown   xd'))

    def test_screenshot_eight_sites_use_eight_different_shades_and_legend(self):
        site_names=['ONE NCR DC','Bangalore DC','NCR Bilaspur DC','NCR Bamnoli DC',
            'Surat DC','NCR TAURU DC','Kolkata DC','Mumbai DC']
        counts=[(1973,1595,1292),(1687,1,1),(1290,1026,921),(1227,1135,582),
                (1226,81,81),(1052,613,536),(997,795,461),(910,707,561)]
        metric_rows=[]
        for name,(a,b,c) in zip(site_names,counts):
            metric_rows+=self.records(name,a,b,c)
        figure=self.chart(metric_rows,{'ONE NCR DC':'#0055FF'})
        legends=[t for t in figure.data if t.type=='scatter' and t.showlegend]
        bars=[t for t in figure.data if t.type=='bar']
        self.assertEqual(len(legends),8)
        self.assertEqual(len(bars),24)
        self.assertEqual(len({t.marker.color for t in legends}),8)
        for name in site_names:
            own_bars=[t for t in bars if t.name==name]
            own_legend=next(t for t in legends if t.name==name)
            self.assertEqual(own_legend.marker.color,site_color(name))
            self.assertEqual([t.marker.color for t in own_bars],list(site_shades(site_color(name))))
            for t in own_bars:
                self.assertNotIn(t.marker.color,{'#808080','#AAAAAA','#333333','#636EFA'})

    def test_unapproved_clipping_or_fudging_absent(self):
        for a,b,c in [(0,0,0),(100,101,99),(100,30,31),(100,-1,0)]:
            ok,bad=roster_coverage_rows(self.records(active=a,adopted=b,match=c))
            self.assertFalse(ok)
            self.assertEqual(len(bad),1)

    def test_pagination_preserves_57_sites(self):
        all_rows=[dict(site=f'Site {i}',active_hc=i) for i in range(1,58)]
        accum=[]
        for index in range(8):
            subset, page, count=roster_page(all_rows,index,page_size=8)
            self.assertEqual(page,index)
            self.assertEqual(count,8)
            accum.extend(r['site'] for r in subset)
        self.assertEqual(len(set(accum)),57)

    def test_app_loads_v6_no_roster_caption(self):
        app=(Path(__file__).resolve().parent.parent/'app.py').read_text()
        snippet=app.split('def render_roster(',1)[1].split('def render_flex(',1)[0]
        self.assertIn('roster_v6_fixed_site_palette_20261012',snippet)
        self.assertNotIn('Each site uses its attendance color',snippet)
        self.assertNotIn('st.caption(',snippet)

    def test_screenshot_8sites_24_count_labels(self):
        counts=[(1973,1595,1292),(1290,1026,921),(1227,1135,582),(1052,613,536),
                (617,496,394),(537,483,409),(346,312,286),(167,163,102)]
        metric_rows=[]
        for i,(a,b,c) in enumerate(counts):
            metric_rows+=self.records(f'Site{i}',a,b,c)
        fig=self.chart(metric_rows)
        labels = [t.text[0] for t in fig.data if t.type == 'scatter' and t.mode == 'text']
        self.assertEqual(len([v for v in labels if not v.endswith('%')]), 24)
        self.assertEqual(len([v for v in labels if v.endswith('%')]), 16)
        self.assertEqual(len([t for t in fig.data if t.type=='bar']),24)
        all_labels=[t.text[0] for t in fig.data if t.type=='scatter' and t.mode=='text']
        for text in ['1,595','1,026','1,135','163','102']:
            self.assertIn(text,all_labels)

if __name__=='__main__':unittest.main()
