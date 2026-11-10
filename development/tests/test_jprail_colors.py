"""Company color coverage, mode exclusions and actual full-catalogue rendering.

No traces or screenshot dumps. JPRAIL_COLOR_OUTPUT may point into a task temp
directory for small counts; JPRAIL_LIVE_BASEMAP enables real street tiles.
"""
import functools
import importlib.util
import json
import os
from pathlib import Path
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import unittest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'assets/data/jprail'
JR={'北海道旅客鉄道','東日本旅客鉄道','東海旅客鉄道','西日本旅客鉄道','四国旅客鉄道','九州旅客鉄道'}
OLD={'highspeed':'#ff0c00','main':'#ff8100','branch':'#c4b600','industrial':'#87491d','subway':'#0300c3','light_rail':'#00bd14','tram':'#d877b8','unclassified':'#343c39'}


class PaletteData(unittest.TestCase):
    def test_all_ordinary_operators_have_documented_non_monochrome_colors(self):
        data=json.loads((DATA/'operator-colors.json').read_text())
        network=json.loads((DATA/'network.geojson').read_text())['features']
        ops=data['operators'];self.assertEqual(len(ops),112)
        for op,record in ops.items():
            with self.subTest(operator=op):
                self.assertRegex(record['color'],r'^#[0-9A-Fa-f]{6}$')
                rgb=bytes.fromhex(record['color'][1:])
                self.assertGreater(max(rgb)-min(rgb),15,'ordinary railway must not silently retain a black/white placeholder')
                self.assertRegex(record['source'],r'^https?://')
                self.assertTrue(record['basis']);self.assertTrue(record['note']);self.assertTrue(record['checked'])
        self.assertEqual(data['jr']['color'],'#FF8100')
        self.assertEqual(data['shinkansen']['color'],'#FF0C00')
        self.assertEqual(data['aliases']['三国芦原線'],'えちぜん鉄道')
        for op in ['東京地下鉄','大阪市高速電気軌道','湘南モノレール','丹後海陸交通','ゆりかもめ']:
            self.assertNotIn(op,ops);self.assertIn(op,data['excludedOperators'])
        self.assertIn('山口線',data['excludedLines']['西武鉄道'])
        self.assertNotIn('西日本旅客鉄道',data['excludedLines'])
        self.assertIn('鉄道線',{f['properties']['name'] for f in network if f['properties']['operator']=='小田急箱根'})
        self.assertIn('鋼索線',data['excludedLines']['小田急箱根'])
        self.assertIn('世田谷線',data['excludedLines']['東急電鉄'])
        self.assertIn('富山港線',data['excludedLines']['富山地方鉄道'])
        known=set(ops)|JR|set(data['excludedOperators'])|set(data['aliases'])
        self.assertEqual({f['properties']['operator'] for f in network}-known,set())
        fixtures={'上信電鉄':'#004999','東葉高速鉄道':'#5AB55C','岳南電車':'#CF664D','青い森鉄道':'#2CBADC','ひたちなか海浜鉄道':'#FF9933'}
        for op,color in fixtures.items():self.assertEqual(ops[op]['color'],color)
        self.assertIn('第三方',ops['青い森鉄道']['note'])
        self.assertIn('不是公司官方',ops['北陸鉄道']['note'])


@unittest.skipUnless(importlib.util.find_spec('playwright'),'Playwright required')
class PaletteBrowser(unittest.TestCase):
    def test_every_operator_and_every_pass_uses_the_palette_on_real_layers(self):
        from playwright.sync_api import sync_playwright
        from development.tests.test_jprail_audit import RenderedCatalogue
        checks=RenderedCatalogue('test_every_pass_and_continuous_zoom')
        palette=json.loads((DATA/'operator-colors.json').read_text())
        def canonical(op):return palette['aliases'].get(op,op)
        def ordinary(op,name):return (canonical(op) in JR or canonical(op) in palette['operators']) and name not in palette['excludedLines'].get(canonical(op),[])
        def expected(op,name,kind,grade):
            if ordinary(op,name):
                if kind=='1':return '#ff0c00'
                if canonical(op) in JR:return '#ff8100'
                return palette['operators'][canonical(op)]['color'].lower()
            return OLD.get(grade or ('highspeed' if kind=='1' else 'unclassified'),OLD['unclassified'])
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=os.environ.get('JPRAIL_BASE_URL',f'http://127.0.0.1:{server.server_port}').rstrip('/')
        errors=[];counts={'operators':0,'passes':0,'views':0,'paintSamples':0}
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport={'width':1600,'height':1040})
                if not os.environ.get('JPRAIL_LIVE_BASEMAP'):
                    context.route('**/*',lambda r:r.continue_() if urlsplit(r.request.url).hostname==urlsplit(base).hostname else r.abort())
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/JPRail.html');page.wait_for_function('window.JPRail?.state.stations.length>10000')
                if os.environ.get('JPRAIL_LIVE_BASEMAP'):page.wait_for_function('JPRail.state.basemap.status==="ready"',timeout=60000)
                def settle():
                    page.wait_for_function('JPRail.camera.whenIdle()')
                    page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                def verify_layers():
                    rows=page.evaluate('[...JPRail.state.layers.values()].flatMap(l=>l.getLayers().map(p=>[p.feature.properties.operator,p.feature.properties.name,p.feature.properties.kind,p.feature.properties.grade,p.options.color]))')
                    self.assertGreater(len(rows),0)
                    for op,name,kind,grade,color in rows:self.assertEqual(color.lower(),expected(op,name,kind,grade),(op,name))
                    visible=page.evaluate('JPRail.state.displayed.map(f=>[f.properties.operator,f.properties.name,f.properties.kind,f.properties.grade,JPRail.railStyle(f).color])')
                    for op,name,kind,grade,color in visible:self.assertEqual(color.lower(),expected(op,name,kind,grade),(op,name))
                    keys={('shinkansen' if kind=='1' else 'jr' if canonical(op) in JR else 'operator:'+canonical(op)) if ordinary(op,name) else 'other:'+(grade or 'unclassified') for op,name,kind,grade,_ in visible}
                    self.assertEqual(set(page.evaluate('JPRail.state.colorLegend.map(i=>i.id)')),keys)
                    checks.check_rendered_layers(page)
                options=page.locator('#railOperator option').evaluate_all('(xs)=>xs.map(x=>x.value)')
                self.assertEqual(set(options)-{'','jr','private'},JR|set(palette['operators']))
                self.assertNotIn('三国芦原線',options)
                for op in sorted(JR|set(palette['operators'])):
                    page.locator('#railOperator').select_option(op);settle();verify_layers()
                    self.assertTrue(page.evaluate('(op)=>JPRail.state.displayed.every(f=>JPRail.railColors.isRailway(f)&&JPRail.railColors.operatorOf(f.properties.operator)===op)',op))
                    counts['operators']+=1;counts['views']+=1
                page.locator('#clearRailFilters').click();page.locator('#showEnded').check()
                ids=page.evaluate('JPRail.state.passes.map(p=>p.id)')
                self.assertEqual(len(ids),54)
                for id in ids:
                    with self.subTest(pass_id=id):
                        page.locator('[data-pass="'+id+'"]').click();settle();verify_layers()
                        self.assertEqual(page.evaluate('JPRail.state.selected'),id)
                        self.assertEqual(page.locator('.pass-card[aria-pressed="true"]').count(),1)
                        self.assertFalse(page.locator('#infrastructure').is_checked())
                        self.assertTrue(page.locator('#infrastructure').is_disabled())
                        self.assertTrue(page.locator('#passDetail').is_visible())
                        counts['views']+=1
                        # A real point on a longest source line, rather than an
                        # empty bounding-box centre, exercises the detailed LOD.
                        point=page.evaluate('''()=>{const lines=JPRail.state.displayed.flatMap(f=>f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates),line=lines.reduce((a,b)=>a.length>b.length?a:b);return line[Math.floor(line.length/2)];}''')
                        page.evaluate('(p)=>JPRail.camera.setView([p[1],p[0]],13)',point);settle()
                        page.wait_for_function('JPRail.state.detailStatus==="detail"');verify_layers()
                        counts['paintSamples']+=checks.check_paint(page);counts['views']+=1
                        page.locator('#railGrade').select_option('branch');settle()
                        self.assertTrue(page.evaluate('JPRail.state.displayed.every(f=>JPRail.gradeOf(f)==="branch")'))
                        page.locator('#railGrade').select_option('');settle()
                        counts['passes']+=1
                page.locator('#railOperator').select_option('東急電鉄');settle()
                # Selecting a company outside a pass gives an explicit empty
                # intersection, never an unrelated company-colored full map.
                if not page.evaluate('JPRail.state.displayed.length'):
                    self.assertEqual(page.evaluate('[...JPRail.state.layers.values()][0].getLayers().length'),0)
                    page.locator('.rail-legend summary').click()
                    self.assertIn('没有匹配',page.locator('#railLegendItems').inner_text())
                    page.locator('.rail-legend summary').click()
                page.locator('#clearSelection').click();page.locator('#railOperator').select_option('東葉高速鉄道');settle()
                self.assertEqual({r[0] for r in page.evaluate('JPRail.state.displayed.map(f=>[f.properties.operator])')},{'東葉高速鉄道'})
                page.locator('.rail-legend summary').click()
                self.assertIn('東葉高速鉄道',page.locator('#railLegendItems').inner_text())
                self.assertNotIn('東京地下鉄',page.locator('#railLegendItems').inner_text())
                if os.environ.get('JPRAIL_REVIEW_IMAGE'):
                    page.locator('#clearRailFilters').click();page.locator('[data-pass="hokuriku"]').click();settle()
                    if os.environ.get('JPRAIL_LIVE_BASEMAP'):
                        page.wait_for_function('JPRail.streets.getMap().areTilesLoaded()',timeout=60000)
                        page.evaluate('JPRail.streets.getMap().triggerRepaint()')
                    page.wait_for_timeout(800)
                    checks.check_labels(page)
                    page.screenshot(path=os.environ['JPRAIL_REVIEW_IMAGE'])
                self.assertEqual(errors,[])
                browser.close()
        finally:server.shutdown();server.server_close()
        if os.environ.get('JPRAIL_COLOR_OUTPUT'):Path(os.environ['JPRAIL_COLOR_OUTPUT']).write_text(json.dumps(counts))
        print('palette rendering:',json.dumps(counts),flush=True)


if __name__=='__main__':unittest.main()
