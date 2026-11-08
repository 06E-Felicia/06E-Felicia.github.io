"""JPRail data and browser regression. Set JPRAIL_BASE_URL to check Pages."""
import functools
import importlib.util
import json
import os
from pathlib import Path
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import unittest
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[2]

class CatalogueTests(unittest.TestCase):
    def test_sources_and_geometry_selectors_are_consistent(self):
        data=json.loads((ROOT/'assets/data/jprail/passes.json').read_text())
        network=json.loads((ROOT/'assets/data/jprail/network.geojson').read_text())
        operators={f['properties']['operator'] for f in network['features']}
        # JR and Seibu both have a Yamaguchi Line. Never borrow the private
        # railway's light-rail tag merely because a line name matches.
        yamaguchi=next(f for f in network['features'] if f['properties']['operator']=='西日本旅客鉄道' and f['properties']['name']=='山口線')
        self.assertNotIn(yamaguchi['properties']['grade'],('light_rail','tram','subway'))
        ids=[p['id'] for p in data['passes']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertGreater(len(operators),100)
        for p in data['passes']:
            with self.subTest(pass_id=p['id']):
                self.assertTrue(p['source'].startswith('https://'))
                for field in ('scope','sales','use','trains','eligibility','checked'):
                    self.assertTrue(p[field])
                self.assertEqual(p['precision'],'schematic')
                self.assertTrue(p['selectors'])
                for selector in p['selectors']:
                    self.assertTrue(set(selector['operators'])<=operators)
                    if 'bbox' in selector:
                        w,s,e,n=selector['bbox'];self.assertLess(w,e);self.assertLess(s,n)

@unittest.skipUnless(importlib.util.find_spec('playwright'),'Playwright required')
class BrowserTests(unittest.TestCase):
    def test_map_pass_filters_dates_station_search_and_mobile(self):
        from playwright.sync_api import sync_playwright
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=os.environ.get('JPRAIL_BASE_URL',f'http://127.0.0.1:{server.server_port}').rstrip('/')
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                try:
                    context=browser.new_context(viewport={'width':1440,'height':960})
                    context.route('**/*',lambda r:r.continue_() if urlsplit(r.request.url).hostname==urlsplit(base).hostname else r.abort())
                    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(base+'/JPRail.html')
                    page.wait_for_function('window.JPRail?.state.stations.length>0')
                    empty=page.evaluate('JPRail.state.passes.filter(p=>!JPRail.coverageFeatures(JPRail.state.network,p).length).map(p=>p.id)')
                    self.assertEqual(empty,[],'every selectable product must produce a visible route overlay')
                    self.assertTrue(page.evaluate("['highspeed','main','branch'].every(g=>JPRail.state.network.features.some(f=>JPRail.gradeOf(f)===g))"))
                    # At country zoom the infrastructure server has no tiles;
                    # retain the atlas until a detailed zoom can replace it.
                    page.locator('#infrastructure').check()
                    self.assertTrue(page.evaluate('JPRail.map.hasLayer([...JPRail.state.layers.values()][0])'))
                    page.evaluate('() => {JPRail.map.setZoom(8,{animate:false});}')
                    self.assertFalse(page.evaluate('JPRail.map.hasLayer([...JPRail.state.layers.values()][0])'))
                    # A pass replaces the entire visible route layer. Switching
                    # passes must not retain the previous pass or the full map.
                    page.locator('[data-pass="japan"]').click()
                    page.locator('[data-pass="hokkaido"]').click()
                    self.assertEqual(page.evaluate('JPRail.state.selected'),'hokkaido')
                    self.assertEqual(page.locator('.pass-card[aria-pressed="true"]').count(),1)
                    self.assertTrue(page.evaluate("JPRail.state.displayed.every(f=>f.properties.operator==='北海道旅客鉄道')"))
                    self.assertTrue(page.locator('#infrastructure').is_disabled())
                    self.assertFalse(page.locator('#infrastructure').is_checked())
                    self.assertTrue(page.evaluate("[...JPRail.state.layers.values()].every(l=>l.getLayers().every(p=>p.options.color===JPRail.railStyle(p.feature).color&&!p.options.dashArray))"))
                    page.locator('#clearSelection').click()
                    page.locator('#railOperator').select_option('東日本旅客鉄道')
                    self.assertGreater(page.evaluate('JPRail.state.displayed.length'),0)
                    self.assertTrue(page.evaluate("JPRail.state.displayed.every(f=>f.properties.operator==='東日本旅客鉄道')"))
                    for grade,color in (('main','#ff8100'),('branch','#c4b600')):
                        page.locator('#railGrade').select_option(grade)
                        self.assertGreater(page.evaluate('JPRail.state.displayed.length'),0)
                        self.assertTrue(page.evaluate('(g)=>JPRail.state.displayed.every(f=>JPRail.gradeOf(f)===g)',grade))
                        self.assertTrue(page.evaluate('(c)=>[...JPRail.state.layers.values()][0].getLayers().every(p=>p.options.color===c)',color))
                    page.locator('#railGrade').select_option('highspeed')
                    self.assertTrue(page.evaluate("JPRail.state.displayed.length>0&&JPRail.state.displayed.every(f=>JPRail.gradeOf(f)==='highspeed'&&f.properties.operator==='東日本旅客鉄道')"))
                    page.locator('#railOperator').select_option('private')
                    self.assertEqual(page.evaluate('JPRail.state.displayed.length'),0)
                    self.assertEqual(page.evaluate('[...JPRail.state.layers.values()][0].getLayers().length'),0)
                    page.locator('#clearRailFilters').click()
                    page.locator('#passSearch').fill('近铁');self.assertEqual(page.locator('.pass-card').count(),4)
                    page.locator('[data-pass="kintetsu5"]').click()
                    page.locator('#startDate').fill('2026-12-30');page.locator('#startDate').dispatch_event('change')
                    self.assertIn('2027-01-03',page.locator('#dateResult').inner_text())
                    self.assertTrue(page.evaluate("JPRail.state.displayed.every(f=>['近畿日本鉄道','伊賀鉄道'].includes(f.properties.operator))"))
                    page.locator('#closeDetail').click();self.assertIsNone(page.evaluate('JPRail.state.active'))
                    page.locator('#passSearch').fill('');page.locator('#showEnded').check()
                    page.locator('[data-pass="kansai-lite"]').click();self.assertIn('历史票券',page.locator('#dateResult').inner_text())
                    page.locator('#stationSearch').fill('京都');page.wait_for_selector('[data-station]')
                    page.locator('[data-station]').first.click();page.wait_for_function('JPRail.map.getZoom()===13')
                    page.locator('#closeDetail').click()
                    page.locator('.rail-legend summary').click();self.assertIn('主干线',page.locator('.rail-legend').inner_text())
                    for width in (320,390,768,1100):
                        page.set_viewport_size({'width':width,'height':844})
                        self.assertFalse(page.evaluate('document.documentElement.scrollWidth>innerWidth+1'))
                    page.locator('#aboutBtn').click();self.assertTrue(page.locator('#aboutDialog').is_visible())
                    page.locator('#closeAbout').click();self.assertEqual(errors,[])
                finally:browser.close()
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
