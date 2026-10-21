"""Pure-standard-library new-site color persistence regression tests.

Run: python -m unittest -q test_site_palette_v7.py test_roster_layers.py
No report import, Pandas or Streamlit process is needed for these tests.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest

from roster_layers import roster_grouped_figure, site_shades
from site_palette import (
    ASSIGNED_SITE_COLORS, SITE_PALETTE_VERSION,
    _oklab, _candidate_colors, ensure_site_colors,
    site_color, site_color_map, site_key,
)


class SiteColorV7Tests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.database = Path(self.directory.name) / 'dashboard.db'

    def test_all_64_approved_colors_remain_exactly_the_same(self):
        saved = ensure_site_colors(self.database)
        self.assertEqual(SITE_PALETTE_VERSION, 'SITE_PALETTE_V7_PERSISTENT_20261012')
        self.assertEqual(len(ASSIGNED_SITE_COLORS), 64)
        self.assertEqual(len(saved), 64)
        self.assertEqual(len(set(saved.values())), 64)
        self.assertEqual({k: saved[k] for k in ASSIGNED_SITE_COLORS}, ASSIGNED_SITE_COLORS)
        self.assertEqual(site_color('Kanpur XD', db_path=self.database), '#E63D43')
        self.assertEqual(site_color('varanasi XD', db_path=self.database), '#189D9C')

    def test_three_new_names_receive_unique_saved_colors(self):
        previous = ensure_site_colors(self.database)
        names = ['Delhi XD', 'Delhi DC', 'Port Blair XD']
        colored = site_color_map(names, db_path=self.database)
        self.assertEqual(len(set(colored.values())), 3)
        self.assertFalse(set(colored.values()) & set(previous.values()))
        self.assertEqual(len(ensure_site_colors(self.database)), 67)
        with closing(sqlite3.connect(self.database)) as con, con:
            rows = con.execute("SELECT site_key, color_hex, source FROM site_color_mapping WHERE source='AUTO_GENERATED'").fetchall()
        self.assertEqual(len(rows), 3)
        self.assertEqual({x[2] for x in rows}, {'AUTO_GENERATED'})

    def test_reimport_and_restart_cannot_change_assignments(self):
        first = site_color('Newtown XD', db_path=self.database)
        with closing(sqlite3.connect(self.database)) as con, con:
            earlier = con.execute("SELECT color_hex, assigned_at FROM site_color_mapping WHERE site_key='newtown xd'").fetchone()
        for _ in range(3):
            ensure_site_colors(self.database, ['NEWTOWN  xd'])
        again = site_color('Newtown XD', db_path=self.database)
        self.assertEqual(again, first)
        with closing(sqlite3.connect(self.database)) as con, con:
            after = con.execute("SELECT color_hex, assigned_at FROM site_color_mapping WHERE site_key='newtown xd'").fetchone()
        self.assertEqual(earlier, after)
        # Another new site cannot shuffle the first new site's color.
        site_color('Different XD', db_path=self.database)
        self.assertEqual(first, site_color('Newtown XD', db_path=self.database))

    def test_site_name_normalization_and_dc_xd_not_merged(self):
        color = site_color('Port Blair XD', db_path=self.database)
        self.assertEqual(color, site_color('  PORT    BLAIR xd ', db_path=self.database))
        self.assertNotEqual(color, site_color('Port Blair DC', db_path=self.database))
        self.assertNotEqual(site_color('Vanaras XD', db_path=self.database),
                            site_color('varanasi XD', db_path=self.database))
        with closing(sqlite3.connect(self.database)) as con, con:
            count = con.execute("SELECT count(*) FROM site_color_mapping WHERE site_key LIKE 'port blair %'").fetchone()[0]
        self.assertEqual(count, 2)

    def test_startup_discovers_sites_from_region_mapping(self):
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute('CREATE TABLE site_mapping (site_key TEXT PRIMARY KEY, site TEXT)')
            con.executemany('INSERT INTO site_mapping(site_key,site) VALUES (?,?)',
                            [('new site north xd', 'New Site North XD'),
                             ('new site south dc', 'New Site South DC')])
        saved = ensure_site_colors(self.database)
        self.assertIn('new site north xd', saved)
        self.assertIn('new site south dc', saved)
        self.assertNotEqual(saved['new site north xd'], saved['new site south dc'])

    def test_existing_database_tables_are_untouched(self):
        with closing(sqlite3.connect(self.database)) as con, con:
            con.execute('CREATE TABLE summary_metrics (section TEXT, value REAL)')
            con.executemany('INSERT INTO summary_metrics VALUES (?,?)',
                            [('attendance', 84.7), ('roster', 51.5)])
        ensure_site_colors(self.database, ['New site XD'])
        with closing(sqlite3.connect(self.database)) as con, con:
            rows = con.execute('SELECT section,value FROM summary_metrics').fetchall()
            tables = {row[0] for row in con.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        self.assertEqual(rows, [('attendance', 84.7), ('roster', 51.5)])
        self.assertIn('site_color_mapping', tables)

    def test_color_separation_is_maximized_against_existing_palette(self):
        previous = set(ASSIGNED_SITE_COLORS.values())
        proposed = site_color('Brand-new mystery XD', db_path=self.database)
        own_lab = _oklab(proposed)
        old_labs = [_oklab(c) for c in previous]
        chosen_dist_sq = min(sum((a-b)**2 for a,b in zip(own_lab, old)) for old in old_labs)
        best_available_sq = max(
            min(sum((a-b)**2 for a,b in zip(candidate_lab, old)) for old in old_labs)
            for hex_color, candidate_lab in _candidate_colors() if hex_color not in previous
        )
        self.assertAlmostEqual(chosen_dist_sq, best_available_sq, places=11)
        self.assertGreater(chosen_dist_sq, .0025, 'New color unexpectedly similar to existing colors')

    def test_simultaneous_allocations_do_not_collide(self):
        ensure_site_colors(self.database)
        names = [f'Additional Depot {i} XD' for i in range(12)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda n: site_color(n, db_path=self.database), names))
        self.assertEqual(len(set(results)), len(results))
        self.assertEqual(len(ensure_site_colors(self.database)), 64 + len(names))

    def test_roster_legend_and_bars_use_the_saved_color(self):
        new_site = 'Vizianagaram XD'
        from_map = site_color_map([new_site], db_path=self.database)[new_site]
        record = dict(site_key=site_key(new_site), site=new_site, active_hc=122,
                      rostered_hc=100, roster_match=81, adoption_pct=81.9672,
                      adherence_pct=81.0)
        chart = roster_grouped_figure([record], date(2026, 10, 8), db_path=self.database)
        traces = chart.data
        self.assertEqual(traces[0].marker.color, from_map)
        self.assertEqual([traces[i].marker.color for i in (1,2,4)], list(site_shades(from_map)))
        self.assertEqual([float(traces[i].y[0]) for i in (1,2,4)], [122,100,81])
        self.assertEqual(site_color(new_site,db_path=self.database), from_map)

    def test_app_wires_separate_site_settings_from_session_reports(self):
        app = (Path(__file__).resolve().parent.parent / 'app.py').read_text(encoding='utf-8')
        self.assertIn('new_session_database()', app)
        self.assertIn('init_site_registry(SETTINGS_DB_PATH)', app)
        self.assertIn('refresh_sites_from_registry(DB_PATH, SETTINGS_DB_PATH)', app)
        self.assertIn('save_discovered_sites_to_registry(DB_PATH, SETTINGS_DB_PATH)', app)
        self.assertIn('ensure_site_colors(SETTINGS_DB_PATH)', app)
        self.assertIn('roster_grouped_figure(visible_rows, selected_day, db_path=SETTINGS_DB_PATH)',app)


if __name__=='__main__':
    unittest.main()
