"""Offline Flightdat integration: no requests to FR24 or photo services."""
import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

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
        self.assertGreater(index['refresh_hours'],0)  # Saved snapshots may predate the current schedule.
        self.assertAlmostEqual(json.loads((ROOT/'flightdata/config.json').read_text())['refresh_hours']*60,10)
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

    def raw_flight(self, m, fid='offline-arrival'):
        return {'id':fid,'flightNumber':'CZ9999','scheduledTime':m.now_ts(),
                'aircraft':{'type':'A333','registration':'B-TEST'},
                'airline':{'name':'China Southern Airlines','iata':'CZ'}}

    def test_blocked_pagination_and_departures_do_not_discard_arrivals(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0]
        cfg['pages_per_board']=3
        first={'props':{'airport':{'iata':ap['iata']},'flights':[self.raw_flight(m)],
                        'meta':{'hasMoreNextData':True,'nextPage':2,'date':m.now_ts()}}}
        blocked=m.SourceAccessError('Just a moment...；源站显示访问验证')
        with patch.object(m,'fetch_board',side_effect=[first,blocked]) as fetch, \
                patch.object(m,'fetch_next_board',side_effect=blocked) as next_board:
            flights,_=m.collect_airport(MagicMock(),cfg,ap,{},{},False)
        self.assertEqual(fetch.call_count,2);next_board.assert_called_once()
        self.assertEqual([f['id'] for f in flights],['offline-arrival'])
        self.assertTrue(flights.boards['arrivals']['ok'])
        self.assertTrue(flights.boards['arrivals']['partial'])
        self.assertFalse(flights.boards['departures']['ok'])
        self.assertIn('第 2 页',flights.errors['arrivals'])
        self.assertIn('Just a moment',flights.errors['departures'])

    def test_failed_arrivals_does_not_skip_departures(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0]
        first={'props':{'flights':[self.raw_flight(m)],'meta':{}}}
        with patch.object(m,'fetch_board',side_effect=[m.SourceAccessError('HTTP 403'),first]):
            flights,_=m.collect_airport(MagicMock(),cfg,ap,{},{},False)
        self.assertEqual(len(flights),1)
        self.assertEqual(flights[0]['board'],'departures')
        self.assertIn('HTTP 403',flights.errors['arrivals'])
        self.assertTrue(flights.boards['departures']['ok'])

    def pagination_fixture(self,m):
        cfg=m.load_config();ap=cfg['airports'][1];iata=ap['iata'].lower()
        previous={'props':{'airport':{'iata':ap['iata']},'flights':[self.raw_flight(m,'p1')],
                           'meta':{'nextPage':2,'hasMoreNextData':True}}}
        page=MagicMock();page.url=f'https://www.flightradar24.com/data/airports/{iata}/arrivals'
        href=f'/data/airports/{iata}/arrivals?date=123&page=2'
        page.locator.return_value.evaluate_all.return_value=[href]
        response=MagicMock();response.status=200;response.url=url='https://www.flightradar24.com'+href
        response.request.resource_type='xhr'
        page.expect_response.return_value.__enter__.return_value.value=response
        return cfg,ap,previous,page,response,url

    def test_native_pagination_accepts_json_and_full_html_not_stale_dom(self):
        import html
        m=self.collector()
        for content_type in ['application/json','text/html']:
            with self.subTest(content_type=content_type):
                cfg,ap,previous,page,response,url=self.pagination_fixture(m)
                following={'props':{'flights':[self.raw_flight(m,'p2')],'meta':{'nextPage':3,'hasMoreNextData':True}}}
                response.headers={'content-type':content_type}
                response.text.return_value=(json.dumps(following) if content_type=='application/json' else
                    '<div id="app" data-page="'+html.escape(json.dumps(following),quote=True)+'"></div>')
                result=m.fetch_next_board(page,'arrivals',ap,cfg,False,previous)
                self.assertEqual(result['props']['flights'][0]['id'],'p2')
                self.assertEqual(result['props']['airport']['iata'],ap['iata'])
                page.goto.assert_not_called();page.get_attribute.assert_not_called()
                page.locator.return_value.first.press.assert_called_once_with('Enter',timeout=12000,no_wait_after=True)
                page.locator.return_value.first.click.assert_not_called()
                matcher=page.expect_response.call_args.args[0]
                self.assertTrue(matcher(response))
                response.url=url.replace('page=2','page=1');self.assertFalse(matcher(response))
                response.url=url.replace('www.flightradar24.com','unrelated.example');self.assertFalse(matcher(response))

    def test_native_pagination_refuses_duplicate_or_missing_flights(self):
        m=self.collector()
        for payload in [None,{},'duplicate','blocked']:
            with self.subTest(payload=payload):
                cfg,ap,previous,page,response,_=self.pagination_fixture(m)
                response.headers={'content-type':'application/json'}
                response.text.return_value=json.dumps(previous if payload=='duplicate' else {'props':payload})
                if payload=='blocked':response.status=403
                with self.assertRaises(RuntimeError):
                    m.fetch_next_board(page,'arrivals',ap,cfg,False,previous)
                page.goto.assert_not_called()

    def test_ci_uses_full_chrome_and_never_silently_downgrades(self):
        m=self.collector();pw=MagicMock()
        pw.chromium.launch.side_effect=RuntimeError('Chrome missing')
        with patch.dict(m.os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(RuntimeError,'拒绝静默降级'):
                m._launch_browser(pw,False,None,'chrome')
        self.assertEqual(pw.chromium.launch.call_count,1)
        workflow=(ROOT/'.github/workflows/flightdata.yml').read_text()
        self.assertIn('playwright install --with-deps chrome',workflow)
        self.assertIn('PLAYWRIGHT_CHANNEL: chrome',workflow)
        self.assertIn('xvfb-run -a python flightdata/scraper.py --headed --debug',workflow)
        source=(ROOT/'flightdata/scraper.py').read_text()
        self.assertNotIn('Chrome/131.0.0.0',source)
        self.assertNotIn('ctx.add_init_script(STEALTH_JS)',source)

    def test_source_refusal_stops_retries_and_retains_exact_cause(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0]
        for status in [401,403,429]:
            with self.subTest(status=status):
                page=MagicMock();page.goto.return_value.status=status
                with patch.object(m,'_wait_for_island') as wait:
                    with self.assertRaisesRegex(m.SourceAccessError,f'HTTP {status}'):
                        m.fetch_board(page,'arrivals',ap,cfg,False)
                self.assertEqual(page.goto.call_count,1);wait.assert_not_called()
        page=MagicMock();page.goto.return_value.status=200
        page.title.return_value='Just a moment...'
        with patch.object(m,'_wait_for_island',return_value=None):
            with self.assertRaisesRegex(m.SourceAccessError,'访问验证'):
                m.fetch_board(page,'arrivals',ap,cfg,False)
        self.assertEqual(page.goto.call_count,1)

    def test_short_valid_data_island_and_empty_board_are_valid(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0]
        data={'props':{'flights':[],'airport':{'iata':ap['iata'],'name':'A &quot; B'}}}
        page=MagicMock();page.goto.return_value.status=200
        page.get_attribute.return_value=json.dumps(data)
        self.assertLess(len(page.get_attribute.return_value),1000)
        self.assertEqual(m.fetch_board(page,'arrivals',ap,cfg,False),data)
        page.wait_for_timeout.assert_called_once()  # no retry or island polling wait

    def test_partial_run_publishes_available_flights_and_honest_status(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0];cfg['airports']=[ap]
        arrival=m.build_flight(self.raw_flight(m),'arrivals',cfg,{},{})
        old_departure=m.build_flight(self.raw_flight(m,'old-departure'),'departures',cfg,{},{})
        flights=m.AirportFlights([arrival],errors={'departures':'Just a moment...'},
                                boards={'arrivals':{'ok':True},'departures':{'ok':False}})
        with tempfile.TemporaryDirectory(prefix='flightdat-partial-') as temporary:
            root=Path(temporary)
            with patch.multiple(m,DATA_DIR=root/'cache',SITE_DATA_DIR=root/'public',STATUS_PATH=root/'public/status.json',PHOTO_CACHE_PATH=root/'cache/photos.json'), \
                    patch.object(m,'load_config',return_value=cfg), \
                    patch.object(m,'collect_all',return_value={ap['iata']:(flights,None)}), \
                    patch.dict(m.os.environ,{'FLIGHTDATA_CHECKED_AT':str(int(m.time.time())-90)}), \
                    patch.object(m,'attach_photos'):
                m.write_json(root/'cache'/f"history_{ap['iata'].lower()}.json",{'flights':{'old-departure':old_departure}})
                self.assertEqual(m.run(),0)
            status=json.loads((root/'public/status.json').read_text())
            self.assertTrue(status['ok']);self.assertTrue(status['partial'])
            self.assertEqual(status['successes'],1)
            self.assertGreaterEqual(status['collection_started_at']-status['schedule_checked_at'],90)
            self.assertAlmostEqual(status['refresh_hours']*60,10)
            self.assertIn('Just a moment',status['airports'][ap['iata']]['errors']['departures'])
            snapshot=json.loads((root/'public'/f"{ap['iata'].lower()}.json").read_text())
            self.assertEqual([f['id'] for f in snapshot['flights']],['offline-arrival'])
            self.assertEqual({f['id'] for f in snapshot['today']},{'offline-arrival','old-departure'})
            self.assertTrue(next(f for f in snapshot['today'] if f['id']=='old-departure')['from_history'])

    def test_total_failure_or_browser_failure_keeps_old_snapshot_and_timestamp(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0];cfg['airports']=[ap]
        failed=m.AirportFlights(errors={'departures':'Just a moment...'},boards={'departures':{'ok':False}})
        for startup_error in [False,True]:
            with self.subTest(startup_error=startup_error), tempfile.TemporaryDirectory(prefix='flightdat-failure-') as temporary:
                root=Path(temporary);old_time=m.day_window(m.now_ts())[1]+1
                old={'generated_at':old_time,'generated_at_iso':'old-time','flights':[{'id':'keep-me'}],'stats':{'total':1}}
                with patch.multiple(m,DATA_DIR=root/'cache',SITE_DATA_DIR=root/'public',STATUS_PATH=root/'public/status.json',PHOTO_CACHE_PATH=root/'cache/photos.json'), \
                        patch.object(m,'load_config',return_value=cfg), \
                        patch.object(m,'collect_all',side_effect=RuntimeError('browser executable missing') if startup_error else None,
                                     return_value={ap['iata']:(failed,None)}):
                    snapshot=root/'public'/f"{ap['iata'].lower()}.json"
                    m.write_json(snapshot,old);before=snapshot.read_bytes()
                    self.assertEqual(m.run(),1)
                    self.assertEqual(snapshot.read_bytes(),before)
                status=json.loads((root/'public/status.json').read_text())
                self.assertFalse(status['ok']);self.assertEqual(status['successes'],0)
                state=status['airports'][ap['iata']]
                self.assertEqual(state['last_success_at'],old_time)
                self.assertIn('browser executable missing' if startup_error else 'Just a moment',state['error'])
                if startup_error:self.assertNotIn('Cloudflare',state['error'])

    def test_snapshot_accumulates_the_entire_day_without_a_one_hour_cutoff(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0]
        now=int(m.datetime.fromisoformat('2026-10-19T15:42:00+08:00').timestamp())
        def flight(fid,offset,estimate=None):
            raw={**self.raw_flight(m,fid),'flightNumber':fid,'scheduledTime':now+offset}
            if estimate is not None:raw['estimatedTime']=now+estimate
            return m.build_flight(raw,'arrivals',cfg,{},{})
        current=[flight('old-1210',-12720),flight('too-old',-3601),flight('boundary',-3600),
                 flight('recent',-1200),flight('future',1800),flight('delayed',-12000,1200),
                 flight('tomorrow',12*3600)]
        cached=flight('history-recent',-3000)
        expected={'old-1210','too-old','boundary','recent','future','delayed','history-recent'}
        with tempfile.TemporaryDirectory(prefix='flightdat-lookback-') as temporary:
            root=Path(temporary)
            with patch.multiple(m,DATA_DIR=root,SITE_DATA_DIR=root/'public',PHOTO_CACHE_PATH=root/'photos.json'), \
                    patch.object(m,'now_ts',return_value=now):
                history=root/f"history_{ap['iata'].lower()}.json"
                m.write_json(history,{'flights':{cached['id']:cached}})
                latest=m.build_latest(cfg,ap,current,None,m.time.time(),len(current))
                self.assertEqual({f['id'] for f in latest['today']},expected)
                self.assertEqual({f['id'] for f in latest['flights']},expected-{'history-recent'}|{'tomorrow'})
                self.assertEqual(latest['today_stats']['total'],len(expected))
                self.assertEqual(latest['stats']['scanned_total'],len(current))
                self.assertEqual(latest['service_day'],'2026-10-19')
                self.assertIn('old-1210',m.read_json(history,{})['flights'])
                # Re-reading an old flight must not reset its operation time.
                again=m.build_latest(cfg,ap,current,None,m.time.time(),len(current))
                self.assertIn('old-1210',{f['id'] for f in again['today']})

    def test_next_day_first_failed_capture_clears_yesterday_without_faking_success(self):
        m=self.collector();cfg=m.load_config();ap=cfg['airports'][0];cfg['airports']=[ap]
        first=int(m.datetime.fromisoformat('2026-10-19T15:42:00+08:00').timestamp())
        next_day=int(m.datetime.fromisoformat('2026-10-20T00:10:00+08:00').timestamp())
        old=m.build_flight({**self.raw_flight(m),'scheduledTime':first},'arrivals',cfg,{},{})
        with tempfile.TemporaryDirectory(prefix='flightdat-rollover-') as temporary:
            root=Path(temporary)
            with patch.multiple(m,DATA_DIR=root/'cache',SITE_DATA_DIR=root/'public',STATUS_PATH=root/'public/status.json',PHOTO_CACHE_PATH=root/'cache/photos.json'), \
                    patch.object(m,'load_config',return_value=cfg):
                with patch.object(m,'now_ts',return_value=first):
                    snapshot=m.build_latest(cfg,ap,[old],None,m.time.time())
                    m.write_json(root/'public'/f"{ap['iata'].lower()}.json",snapshot)
                with patch.object(m.time,'time',return_value=next_day), \
                        patch.object(m,'collect_all',side_effect=RuntimeError('source unavailable')):
                    self.assertEqual(m.run(),1)
                cache=m.read_json(root/'cache'/f"history_{ap['iata'].lower()}.json",{})
                snapshot=m.read_json(root/'public'/f"{ap['iata'].lower()}.json",{})
                self.assertEqual(cache['service_day'],'2026-10-20');self.assertEqual(cache['flights'],{})
                self.assertEqual(snapshot['today'],[]);self.assertEqual(snapshot['flights'],[])
                self.assertEqual(snapshot['generated_at'],first)
                status=m.read_json(root/'public/status.json',{})
                self.assertFalse(status['ok']);self.assertEqual(status['airports'][ap['iata']]['last_success_at'],first)
                # Even if the source re-sends last night's flight after
                # midnight, it must not resurrect the previous day's cache.
                new=m.build_flight({**self.raw_flight(m,'new-day'),'scheduledTime':next_day},'arrivals',cfg,{},{})
                with patch.object(m,'now_ts',return_value=next_day):
                    latest=m.build_latest(cfg,ap,[old,new],None,m.time.time())
                self.assertEqual([f['id'] for f in latest['today']],['new-day'])
                self.assertEqual([f['id'] for f in latest['flights']],['new-day'])

    def test_invalid_estimate_falls_back_to_scheduled_time(self):
        m=self.collector()
        for estimate in [None,'bad',-1,0]:
            with self.subTest(estimate=estimate):
                self.assertEqual(m.flight_event_time({'estimated_ts':estimate,'scheduled_ts':123}),123)
        self.assertEqual(m.flight_event_time({}),0)

    def test_confirmed_landing_uses_clear_three_character_label(self):
        m=self.collector();cfg=m.load_config()
        for state in ['landed','arrived']:
            f=m.build_flight({**self.raw_flight(m),'status':{'name':state}},'arrivals',cfg,{},{})
            self.assertEqual(f['status_cn'],'已落地')
            self.assertEqual(len(f['status_cn']),3)

    def test_workflow_is_rooted_and_reuses_the_existing_site_publisher(self):
        flights=(ROOT/'.github/workflows/flightdata.yml').read_text()
        weather=(ROOT/'.github/workflows/update.yml').read_text()
        self.assertIn('name: 更新航班数据',flights)
        self.assertIn("cron: '8,18,28,38,48,58 * * * *'",flights)
        self.assertIn('python3 flightdata/schedule.py',flights)
        self.assertIn("if: needs.collect.outputs.should_run == 'true'",flights)
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
