"""Offline Flightdat integration: no requests to FR24 or photo services."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'flightdata/docs/data'


class FlightdataIntegrationTests(unittest.TestCase):
    def test_root_entry_and_deployment_relative_data_path(self):
        home=(ROOT/'index.html').read_text()
        page=(ROOT/'Flightdat.html').read_text()
        self.assertIn('href="Flightdat.html" class="nav-item"',home)
        self.assertIn('href="index.html">← 返回首页',page)
        self.assertIn('const DATA_BASE = "./flightdata/docs/data/"',page)
        self.assertNotIn('const DATA_BASE = "./data/"',page)
        self.assertNotIn('发布目录为 /docs',page)
        self.assertTrue((ROOT/'.nojekyll').is_file())

    def test_five_airport_snapshots_and_stats_are_consistent(self):
        index=json.loads((DATA/'index.json').read_text())
        status=json.loads((DATA/'status.json').read_text())
        self.assertEqual(index['refresh_hours'],2)
        self.assertEqual({a['iata'] for a in index['airports']},{'SZX','PEK','PVG','CAN','HKG'})
        for airport in index['airports']:
            code=airport['iata'];d=json.loads((DATA/f'{code.lower()}.json').read_text())
            self.assertEqual(d['airport']['iata'],code)
            self.assertEqual(len(d['flights']),d['stats']['total'])
            self.assertEqual(len(d['today']),d['today_stats']['total'])
            self.assertIn(code,status['airports'])
            self.assertTrue(all(f['board'] in ('arrivals','departures') for f in d['flights']))
            self.assertTrue(all(f.get('is_special_livery') or f.get('is_foreign') or f.get('is_four_engine')
                                or f.get('is_widebody') or f.get('is_cargo') or f.get('is_bizjet') for f in d['flights']))

    def collector(self):
        spec=importlib.util.spec_from_file_location('flightdata_collector_test',ROOT/'flightdata/scraper.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        return m

    def test_plain_domestic_widebody_is_featured_but_not_a_special_type(self):
        m=self.collector();cfg=m.load_config()
        for code in ['A333','A359','B77W','B789']:
            with self.subTest(code=code):
                raw={'id':'test-'+code,'flightNumber':'CZ9999','scheduledTime':m.now_ts(),
                     'aircraft':{'type':code,'registration':'B-TEST'},
                     'airline':{'name':'China Southern Airlines','iata':'CZ'}}
                f=m.build_flight(raw,'arrivals',cfg,{},{});s=m.stats_of([f])
                self.assertTrue(f['is_widebody']);self.assertTrue(m.is_displayed(f))
                for key in ['is_special_livery','is_foreign','is_four_engine','is_cargo','is_bizjet','is_special_type']:
                    self.assertFalse(f[key],key)
                self.assertEqual(s['special'],1);self.assertEqual(s['widebody'],1);self.assertEqual(s['special_type'],0)
        f=m.build_flight({**raw,'aircraft':{'type':'A320'}},'arrivals',cfg,{},{})
        self.assertFalse(m.is_displayed(f),'plain domestic narrowbody remains outside the featured list')

    def test_offline_capture_keeps_plain_widebody_in_snapshot_and_history(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0];cfg['airports']=[ap]
        raw={'id':'offline-widebody','flightNumber':'CZ9999','scheduledTime':m.now_ts(),
             'aircraft':{'type':'A333','registration':'B-TEST'},
             'airline':{'name':'China Southern Airlines','iata':'CZ'}}
        wide=m.build_flight(raw,'arrivals',cfg,{},{})
        narrow=m.build_flight({**raw,'id':'offline-narrowbody','aircraft':{'type':'A320'}},'arrivals',cfg,{},{})
        with tempfile.TemporaryDirectory(prefix='flightdat-offline-') as temporary:
            root=Path(temporary)
            with patch.multiple(m,DATA_DIR=root/'cache',SITE_DATA_DIR=root/'public',STATUS_PATH=root/'public/status.json',PHOTO_CACHE_PATH=root/'cache/photos.json'), \
                    patch.object(m,'load_config',return_value=cfg), \
                    patch.object(m,'collect_all',return_value={ap['iata']:([wide,narrow],None)}), \
                    patch.object(m,'attach_photos'):
                self.assertEqual(m.run(),0)
            d=json.loads((root/'public'/f"{ap['iata'].lower()}.json").read_text())
            self.assertEqual([f['id'] for f in d['flights']],['offline-widebody'])
            self.assertEqual(d['stats']['scanned_total'],2)
            self.assertEqual(d['stats']['special'],1)
            history=json.loads((root/'cache'/f"history_{ap['iata'].lower()}.json").read_text())
            self.assertIn('offline-widebody',history['flights'])

    def test_imported_collector_and_configuration_are_self_contained(self):
        source=(ROOT/'flightdata/scraper.py').read_text()
        ast.parse(source)
        self.assertIn('Path(__file__).resolve().parent',source)
        self.assertFalse((ROOT/'flightdata/.git').exists())
        cfg=json.loads((ROOT/'flightdata/config.json').read_text())
        self.assertIn('06E-Felicia/06E-Felicia.github.io',cfg['photos']['user_agent'])
        self.assertTrue((ROOT/'flightdata/data/photos.json').is_file())
        self.assertIn('/爬FR24/',(ROOT/'.gitignore').read_text())

    def test_workflow_is_rooted_and_reuses_the_existing_site_publisher(self):
        flights=(ROOT/'.github/workflows/flightdata.yml').read_text()
        weather=(ROOT/'.github/workflows/update.yml').read_text()
        self.assertIn('name: 更新航班数据',flights)
        self.assertIn("cron: '5 */2 * * *'",flights)
        self.assertIn('python flightdata/scraper.py',flights)
        self.assertIn('git add flightdata/docs/data flightdata/data',flights)
        for workflow in [flights,weather]:
            self.assertIn('group: weather-update-${{ github.ref }}',workflow)
        self.assertIn("workflows: ['更新航班数据']",weather)
        self.assertIn('head_repository.full_name == github.repository',weather)
        self.assertIn("conclusion == 'failure'",weather)
        self.assertIn("path: '.'",weather)
        self.assertNotIn('deploy-pages',flights)


if __name__=='__main__':unittest.main()
