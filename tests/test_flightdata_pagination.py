"""Real Chrome pagination against intercepted fixtures; no FR24 network calls.

The fixture refuses direct page-2 HTML visits but allows its native link's
Inertia request, and deliberately leaves #app[data-page] stale after page 2.
"""
import html
import importlib.util
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://www.flightradar24.com/data/airports/szx/arrivals'


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Playwright required for real-browser fixtures')
class NativePaginationTests(unittest.TestCase):
    def test_native_json_then_full_document_and_refusal(self):
        from playwright.sync_api import sync_playwright
        spec = importlib.util.spec_from_file_location('flightdat_paging', ROOT/'flightdata/scraper.py')
        collector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector)

        def payload(number, final=False):
            return {'props': {'airport': {'iata': 'SZX'},
                    'flights': [{'id': f'page-{number}', 'scheduledTime': number}],
                    'meta': {'date': 123, 'nextPage': number+1, 'hasMoreNextData': not final}}}

        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='chrome', headless=True)
            try:
                for mode in ['normal', 'footer-overlay', 'denied']:
                    with self.subTest(mode=mode):
                        context = browser.new_context()
                        requested = []

                        def respond(route):
                            request = route.request
                            parsed = urlsplit(request.url)
                            if parsed.hostname != 'www.flightradar24.com' or parsed.path != urlsplit(BASE).path:
                                route.abort()
                                return
                            number = int(parse_qs(parsed.query).get('page', ['1'])[0])
                            requested.append((number, request.resource_type, request.headers.get('x-inertia')))
                            if number == 2:
                                if mode=='denied' or request.headers.get('x-inertia') != 'true':
                                    route.fulfill(status=403, content_type='text/html', body='<title>Just a moment...</title>')
                                else:
                                    route.fulfill(content_type='application/json', body=json.dumps(payload(2)))
                                return
                            data = payload(number, final=number == 3)
                            app = '<div id="app" data-page="'+html.escape(json.dumps(data), quote=True)+'"></div>'
                            link = '' if number == 3 else '<a id="later" href="'+BASE+'?date=123&amp;page=2">Later flights</a>'
                            script = '''<script>
                            const link=document.querySelector('#later');
                            if(link) link.onclick=async function(e){
                              e.preventDefault();
                              const response=await fetch(link.href,{headers:{'X-Inertia':'true'}});
                              if(!response.ok)return;
                              const next=await response.json();
                              // Real Inertia navigation does not rewrite the initial data-page attribute.
                              document.title='Page '+next.props.flights[0].id;
                              link.href=link.href.replace('page=2','page=3');
                              link.onclick=null;
                            };
                            </script>'''
                            # Reproduce a long SZX board with a sticky footer
                            # covering the link: pointer-click times out but
                            # native keyboard activation remains functional.
                            if mode=='footer-overlay' and number==1:
                                app+='<div style="height:18000px"></div>'
                                link+='<div style="position:fixed;inset:0;z-index:100;background:transparent"></div>'
                            route.fulfill(content_type='text/html', body=app+link+script)

                        context.route('**/*', respond)
                        page = context.new_page()
                        cfg = {'max_retries': 1, 'pages_per_board': 3, 'pagination_delay_ms': 0}
                        pages = collector.fetch_board_pages(page, 'arrivals', {'iata': 'SZX'}, cfg, False)
                        if mode=='denied':
                            self.assertEqual(len(pages), 1)
                            self.assertIn('HTTP 403', pages.warning)
                            self.assertEqual([n for n, _, _ in requested], [1, 2])
                        else:
                            self.assertIsNone(pages.warning)
                            self.assertEqual([p['props']['flights'][0]['id'] for p in pages], ['page-1', 'page-2', 'page-3'])
                            self.assertEqual([n for n, _, _ in requested], [1, 2, 3])
                            self.assertEqual(requested[1][1:], ('fetch', 'true'))
                            self.assertEqual(requested[2][1], 'document')
                        context.close()
            finally:
                browser.close()


if __name__ == '__main__':
    unittest.main()
