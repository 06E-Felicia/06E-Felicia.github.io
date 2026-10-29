"""Offline access-refusal regressions; never contact FR24 or use real sessions."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]


def collector():
    spec = importlib.util.spec_from_file_location('flightdat_access_test', ROOT/'flightdata/scraper.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AccessTests(unittest.TestCase):
    def test_first_pagination_denial_stops_every_later_board_and_airport(self):
        m = collector(); cfg = m.load_config()
        first = {'props': {'airport': {'iata': 'SZX'}, 'meta': {
            'hasMoreNextData': True, 'nextPage': 2, 'date': m.now_ts(), 'hoursRange': 24},
            'flights': [{'id': 'keep-first-page', 'flightNumber': 'CZ1234', 'scheduledTime': m.now_ts(),
                         'aircraft': {'type': 'A333'}, 'airline': {'name': 'China Southern Airlines', 'iata': 'CZ'}}]}}
        denied = m.SourceAccessError('HTTP 403', status=403)
        api = ModuleType('playwright.sync_api'); api.sync_playwright = MagicMock()
        browser = MagicMock()
        with patch.dict(sys.modules, {'playwright.sync_api': api}), \
                patch.object(m.session, 'load_state', return_value=None), \
                patch.object(m, '_launch_browser', return_value=browser), \
                patch.object(m, 'read_json', return_value={}), patch.object(m, 'write_json'), \
                patch.object(m, 'fetch_board', return_value=first) as fetch, \
                patch.object(m, 'fetch_next_board', side_effect=denied) as following:
            results = m.collect_all(cfg, True, False)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(following.call_count, 1)
        self.assertEqual(len(results), 7)
        szx = results['SZX'][0]
        self.assertEqual([f['id'] for f in szx], ['keep-first-page'])
        self.assertIs(szx.access_refusal, denied)
        self.assertTrue(szx.boards['arrivals']['partial'])
        self.assertEqual(szx.boards['arrivals']['http_status'], 403)
        self.assertTrue(szx.boards['departures']['skipped'])
        for code, (flights, _) in results.items():
            if code == 'SZX': continue
            self.assertEqual(flights, [])
            self.assertTrue(all(b['skipped'] for b in flights.boards.values()))
        browser.close.assert_called_once()

    def test_partial_refusal_keeps_data_and_does_not_block_the_next_run(self):
        m = collector(); cfg = m.load_config(); cfg['airports'] = cfg['airports'][:1]
        airport = cfg['airports'][0]
        flight = m.build_flight({'id': 'available', 'flightNumber': 'CZ1234',
            'scheduledTime': m.now_ts(), 'aircraft': {'type': 'A333'}}, 'arrivals', cfg, {}, {})
        denied = m.SourceAccessError('HTTP 403', status=403)
        flights = m.AirportFlights([flight], errors={'arrivals': 'HTTP 403'},
            boards={'arrivals': {'ok': True, 'partial': True, 'access_denied': True},
                    'departures': {'ok': False, 'skipped': True}})
        flights.access_refusal = denied
        with tempfile.TemporaryDirectory(prefix='flightdat-access-') as tmp:
            root = Path(tmp)
            with patch.multiple(m, DATA_DIR=root/'cache', SITE_DATA_DIR=root/'public',
                                STATUS_PATH=root/'public/status.json', PHOTO_CACHE_PATH=root/'cache/photos.json'), \
                    patch.object(m, 'load_config', return_value=cfg), \
                    patch.object(m, 'collect_all', return_value={'SZX': (flights, 24)}) as collect, \
                    patch.object(m, 'attach_photos'):
                self.assertEqual(m.run(), 1)
                status = json.loads(m.STATUS_PATH.read_text())
                self.assertFalse(status['ok']); self.assertTrue(status['partial'])
                self.assertEqual(status['successes'], 1)
                self.assertEqual(status['complete_airports'], 0)
                self.assertTrue(status['access_denied'])
                self.assertNotIn('retry_not_before',status)
                self.assertEqual(json.loads((root/'public/szx.json').read_text())['flights'][0]['id'], 'available')
                # Legacy future cooldowns must not block direct CLI runs.
                status['retry_not_before'] = m.now_ts()+21600
                m.write_json(m.STATUS_PATH, status)
                self.assertEqual(m.run(), 1)
                self.assertEqual(collect.call_count, 2)
                self.assertNotIn('retry_not_before',json.loads(m.STATUS_PATH.read_text()))

    def test_preflight_refusal_records_error_without_cooldown(self):
        m = collector(); cfg = m.load_config(); cfg['airports'] = cfg['airports'][:1]
        with tempfile.TemporaryDirectory(prefix='flightdat-preflight-') as tmp:
            root = Path(tmp)
            with patch.multiple(m, DATA_DIR=root/'cache', SITE_DATA_DIR=root/'public',
                                STATUS_PATH=root/'public/status.json', PHOTO_CACHE_PATH=root/'cache/photos.json'), \
                    patch.object(m, 'load_config', return_value=cfg), \
                    patch.object(m, 'collect_all', side_effect=m.SourceAccessError('HTTP 429', status=429, retry_after=4000)):
                self.assertEqual(m.run(), 1)
                status = json.loads(m.STATUS_PATH.read_text())
                self.assertEqual(status['successes'], 0)
                self.assertEqual(status['access_status'], 429)
                self.assertNotIn('retry_not_before',status)

    def test_retry_after_and_credential_free_error_metadata(self):
        m = collector()
        response = SimpleNamespace(status=429, headers={'retry-after': '7200', 'set-cookie': 'DO_NOT_STORE'})
        denied = m.access_error(response, 'HTTP 429')
        self.assertEqual(denied.retry_after, 7200)
        self.assertEqual(m.refusal_info(denied)['http_status'], 429)
        self.assertNotIn('DO_NOT_STORE', json.dumps(m.refusal_info(denied)))
        for bad in ['bad', '-10', 'NaN']:
            response.headers['retry-after'] = bad
            self.assertEqual(m.access_error(response, 'HTTP 429').retry_after, 0)

    def test_response_classification_never_exports_headers_or_bodies(self):
        m=collector()
        request=SimpleNamespace(resource_type='fetch',headers={'x-inertia':'true',
             'cookie':'PRIVATE_COOKIE','authorization':'PRIVATE_AUTH','x-custom':'PRIVATE_CUSTOM'})
        response=SimpleNamespace(status=403,request=request,headers={'cf-mitigated':'challenge',
             'server':'cloudflare','content-type':'text/html; charset=UTF-8',
             'set-cookie':'PRIVATE_SET_COOKIE','x-custom':'PRIVATE_SERVER_VALUE'})
        diagnostics=m.access_response_diagnostics(response)
        self.assertEqual(diagnostics['kind'],'cloudflare_challenge')
        self.assertEqual(diagnostics['request_type'],'fetch')
        self.assertTrue(diagnostics['inertia_request'])
        self.assertNotIn('PRIVATE_',json.dumps(diagnostics))
        response.headers={'server':'cloudflare','content-type':'application/json'}
        self.assertEqual(m.access_response_diagnostics(response)['kind'],'forbidden_json_response')
        response.status=401
        self.assertEqual(m.access_response_diagnostics(response)['kind'],'authentication_required')
        response.status=429
        self.assertEqual(m.access_response_diagnostics(response)['kind'],'rate_limited')
        response.status=403;response.headers={'server':'cloudflare'}
        self.assertEqual(m.access_response_diagnostics(response)['kind'],'unclassified_access_refusal',
                         'Cloudflare server alone does not prove a challenge')

    @unittest.skipUnless(importlib.util.find_spec('playwright'), 'Playwright required for timeout type')
    def test_document_fallback_only_for_interaction_timeout_never_refusal(self):
        from playwright.sync_api import TimeoutError as BrowserTimeout
        m = collector(); args = (MagicMock(), 'arrivals', {'iata': 'SZX'}, {}, False, {})
        with patch.object(m, 'fetch_next_native', side_effect=m.SourceAccessError('HTTP 403')), \
                patch.object(m, 'fetch_next_document') as document:
            with self.assertRaises(m.SourceAccessError): m.fetch_next_board(*args)
            document.assert_not_called()
        with patch.object(m, 'fetch_next_native', side_effect=BrowserTimeout('renderer timeout')), \
                patch.object(m, 'fetch_next_document', return_value={'verified': True}) as document:
            self.assertEqual(m.fetch_next_board(*args), {'verified': True})
            document.assert_called_once()

    @unittest.skipUnless(importlib.util.find_spec('playwright'), 'Playwright required for timeout type')
    def test_timeout_after_a_request_or_403_never_issues_a_second_request(self):
        from playwright.sync_api import TimeoutError as BrowserTimeout
        m=collector();base='https://www.flightradar24.com/data/airports/szx/arrivals'
        target=base+'?page=2';request=SimpleNamespace(url=target,resource_type='fetch')
        response=SimpleNamespace(url=target,request=request,status=403,headers={})
        for got_response in [False,True]:
            with self.subTest(got_response=got_response):
                page=MagicMock();page.url=base
                page.locator.return_value.evaluate_all.return_value=[target]
                page.expect_response.return_value.__enter__.return_value.value=response
                def press(*args,**kwargs):
                    handlers={call.args[0]:call.args[1] for call in page.on.call_args_list}
                    handlers['request'](request)
                    if got_response:handlers['response'](response)
                    raise BrowserTimeout('site handler timed out')
                page.evaluate.side_effect=press
                with patch.object(m,'fetch_next_document') as document:
                    with self.assertRaises(m.SourceAccessError if got_response else RuntimeError):
                        m.fetch_next_board(page,'arrivals',{'iata':'SZX'},{'pagination_delay_ms':0},False,
                                           {'props':{'meta':{'nextPage':2}}})
                    document.assert_not_called()


if __name__ == '__main__': unittest.main()
