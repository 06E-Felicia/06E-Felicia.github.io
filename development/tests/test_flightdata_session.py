"""Offline auth-scope, no-secret-output and entitlement regressions."""
import base64
import contextlib
import html
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,MagicMock

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('fr24_session_test',ROOT/'flightdata/fr24_session.py')
session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)


def fixture():
    return {'cookies':[
        {'name':'session','value':'PRIVATE_TEST_TOKEN','domain':'.flightradar24.com','path':'/','secure':True,'httpOnly':True,'sameSite':'Lax','expires':-1},
        {'name':'google','value':'UNRELATED_TOKEN','domain':'.google.com','path':'/'},
        {'name':'trick','value':'EVIL_TOKEN','domain':'.flightradar24.com.evil.test','path':'/'},
        {'name':'cf_clearance','value':'CF_TEST_TOKEN','domain':'.flightradar24.com','path':'/'}],
        'origins':[{'origin':'https://www.flightradar24.com','localStorage':[{'name':'auth','value':'LOCAL_TEST_TOKEN'}]},
                   {'origin':'https://example.test','localStorage':[{'name':'private','value':'UNRELATED_TOKEN'}]}]}


class SessionTests(unittest.TestCase):
    def test_state_is_scoped_and_does_not_reuse_challenge_clearance(self):
        state,encoded=session.encode_state(fixture())
        self.assertEqual([c['name'] for c in state['cookies']],['session'])
        self.assertEqual([o['origin'] for o in state['origins']],['https://www.flightradar24.com'])
        self.assertEqual(session.decode_state(encoded),state)
        self.assertLess(len(encoded),session.MAX_SECRET_BYTES)
        raw=json.dumps(state)
        for token in ['UNRELATED_TOKEN','EVIL_TOKEN','CF_TEST_TOKEN']:
            self.assertNotIn(token,raw)

    def test_invalid_state_never_echoes_token_in_error(self):
        for value in ['PRIVATE_TEST_TOKEN',base64.b64encode(b'PRIVATE_TEST_TOKEN').decode(),'A'*50000]:
            with self.subTest(size=len(value)),self.assertRaises(session.SessionError) as error:
                session.decode_state(value)
            self.assertNotIn('PRIVATE_TEST_TOKEN',str(error.exception))

    def test_loads_optional_secret_without_creating_a_public_file(self):
        _,encoded=session.encode_state(fixture())
        with patch.dict(os.environ,{session.SECRET_NAME:encoded,'GITHUB_ACTIONS':'true'},clear=True):
            self.assertTrue(session.state_requested())
            self.assertEqual(session.load_state()['cookies'][0]['value'],'PRIVATE_TEST_TOKEN')
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'},clear=True):
            self.assertIsNone(session.load_state())

    def test_private_export_is_silent_and_permission_restricted(self):
        with tempfile.TemporaryDirectory(prefix='fr24-auth-test-') as temp:
            folder=Path(temp)/'.auth'
            with patch.multiple(session,AUTH_DIR=folder,STATE_FILE=folder/'state.json',SECRET_FILE=folder/'state.b64'):
                output=io.StringIO()
                with contextlib.redirect_stdout(output):
                    paths=session.save_private_state(fixture())
                self.assertEqual(output.getvalue(),'')
                self.assertEqual(folder.stat().st_mode&0o777,0o700)
                for path in paths:self.assertEqual(path.stat().st_mode&0o777,0o600)
                self.assertEqual(session.decode_state(paths[1].read_text())['cookies'][0]['value'],'PRIVATE_TEST_TOKEN')

    def test_browser_24h_entitlement_not_cookie_presence_is_the_gate(self):
        for hours in [None,0,12,'12','bad']:
            with self.subTest(hours=hours),self.assertRaises(session.SessionError):
                session.assert_24h({'props':{'meta':{'hoursRange':hours}}})
        self.assertEqual(session.assert_24h({'props':{'meta':{'hoursRange':24}}}),24)

    def test_authenticated_capture_disables_screenshots_and_secrets_are_not_packaged(self):
        spec=importlib.util.spec_from_file_location('auth_scraper_test',ROOT/'flightdata/scraper.py')
        scraper=importlib.util.module_from_spec(spec);spec.loader.exec_module(scraper)
        page=MagicMock()
        with patch.dict(os.environ,{session.SECRET_NAME:'present'},clear=True):
            scraper._debug_screenshot(page,{'iata':'SZX'},'failure',True)
        page.screenshot.assert_not_called()
        workflow=(ROOT/'.github/workflows/flightdata.yml').read_text()
        self.assertIn('FR24_STORAGE_STATE_B64: ${{ secrets.FR24_STORAGE_STATE_B64 }}',workflow)
        self.assertIn('flightdata/docs/data flightdata/data',workflow)
        self.assertNotIn('path: flightdata/.auth',workflow)
        self.assertIn('/flightdata/.auth/',(ROOT/'.gitignore').read_text())

    def test_capture_rejects_a_downgraded_session_before_pagination(self):
        spec=importlib.util.spec_from_file_location('auth_capture_test',ROOT/'flightdata/scraper.py')
        scraper=importlib.util.module_from_spec(spec);spec.loader.exec_module(scraper)
        first={'props':{'flights':[{'id':'not-captured'}],'meta':{'hoursRange':12}}}
        with patch.object(scraper,'fetch_board',return_value=first),patch.object(scraper,'fetch_next_board') as following:
            with self.assertRaises(scraper.session.SessionError):
                scraper.fetch_board_pages(MagicMock(),'arrivals',{'iata':'SZX'},
                    {'_require_authenticated_24h':True},False)
            following.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec('playwright'),'Playwright required for real-browser fixture')
    def test_real_browser_restores_scoped_cookie_and_checks_server_range(self):
        from playwright.sync_api import sync_playwright
        spec=importlib.util.spec_from_file_location('auth_browser_test',ROOT/'flightdata/scraper.py')
        scraper=importlib.util.module_from_spec(spec);spec.loader.exec_module(scraper)
        state,encoded=session.encode_state(fixture())
        requests=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True)
            try:
                for logged_in in [False,True]:
                    with self.subTest(logged_in=logged_in):
                        context=browser.new_context(storage_state=session.decode_state(encoded) if logged_in else None)
                        def respond(route):
                            has_session='session=PRIVATE_TEST_TOKEN' in route.request.headers.get('cookie','')
                            requests.append(has_session)
                            data={'props':{'airport':{'iata':'SZX'},'flights':[],
                                          'meta':{'hoursRange':24 if has_session else 12,
                                                  'date':1792454400,'hasMoreNextData':False}}}
                            body='<div id="app" data-page="'+html.escape(json.dumps(data),quote=True)+'"></div>'
                            route.fulfill(content_type='text/html',body=body)
                        context.route('**/*',respond)
                        cfg={'max_retries':1,'_require_authenticated_24h':True}
                        if logged_in:
                            pages=scraper.fetch_board_pages(context.new_page(),'arrivals',{'iata':'SZX'},cfg,False)
                            self.assertEqual(len(pages),1)
                            self.assertEqual(pages[0]['props']['meta']['hoursRange'],24)
                        else:
                            with self.assertRaises(scraper.session.SessionError):
                                scraper.fetch_board_pages(context.new_page(),'arrivals',{'iata':'SZX'},cfg,False)
                        context.close()
            finally:browser.close()
        self.assertIn(False,requests);self.assertIn(True,requests)


if __name__=='__main__':unittest.main()
