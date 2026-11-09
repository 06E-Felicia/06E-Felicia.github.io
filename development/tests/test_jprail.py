"""JPRail data and browser regression. Set JPRAIL_BASE_URL to check Pages."""
import functools
import importlib.util
import io
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
        detail=json.loads((ROOT/'assets/data/jprail/network-detail.geojson').read_text())
        self.assertEqual(len(detail['features']),len(network['features']))
        def nara_points(atlas):
            f=next(f for f in atlas['features'] if f['properties']['operator']=='近畿日本鉄道' and f['properties']['name']=='奈良線')
            return sum(map(len,f['geometry']['coordinates']))
        self.assertGreater(nara_points(detail),4*nara_points(network))
        boundaries=json.loads((ROOT/'assets/data/jprail/company-boundaries.json').read_text())['boundaries']
        self.assertTrue({'上越妙高','南小谷','米原','猪谷','新宮','熱海','亀山'}<={b['name'] for b in boundaries})
        operators={f['properties']['operator'] for f in network['features']}
        # JR and Seibu both have a Yamaguchi Line. Never borrow the private
        # railway's light-rail tag merely because a line name matches.
        yamaguchi=next(f for f in network['features'] if f['properties']['operator']=='西日本旅客鉄道' and f['properties']['name']=='山口線')
        self.assertNotIn(yamaguchi['properties']['grade'],('light_rail','tram','subway'))
        station_names={s[0] for s in json.loads((ROOT/'assets/data/jprail/stations.json').read_text())}
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
                self.assertTrue(p['stationPins']['source'].startswith('https://'))
                self.assertTrue(p['stationPins']['stations'])
                self.assertTrue(all(x['name'] in station_names for x in p['stationPins']['stations']))
                self.assertEqual(p['price']['currency'],'JPY')
                self.assertEqual([v['duration'] for v in p['price']['variants']],p['durations'])
                self.assertTrue(p['price']['source'].startswith('https://'))
                if p['status']=='current':
                    self.assertTrue(all(isinstance(v['amountJPY'],int) and v['amountJPY']>0 for v in p['price']['variants']))
                for selector in p['selectors']:
                    self.assertTrue(set(selector['operators'])<=operators)
                    if 'bbox' in selector:
                        w,s,e,n=selector['bbox'];self.assertLess(w,e);self.assertLess(s,n)

@unittest.skipUnless(importlib.util.find_spec('playwright'),'Playwright required')
class BrowserTests(unittest.TestCase):
    def assert_rail_strokes_visible(self,page):
        if not importlib.util.find_spec('PIL'):return
        # Compare rendered railway pixels with/without station labels. Exclude
        # station dots, which intentionally sit on the tracks. This catches
        # halos masking tracks even when their geometry remains intact.
        from PIL import Image,ImageDraw
        shown=Image.open(io.BytesIO(page.locator('#map').screenshot())).convert('RGB')
        page.evaluate('JPRail.map.getPane("railStations").style.visibility="hidden"')
        try:
            rails=Image.open(io.BytesIO(page.locator('#map').screenshot())).convert('RGB')
        finally:
            page.evaluate('JPRail.map.getPane("railStations").style.visibility=""')
        mask=Image.new('1',rails.size,1);draw=ImageDraw.Draw(mask)
        points=page.evaluate('[...JPRail.state.stationPool,...JPRail.state.pinnedStations.map(p=>p.station)].map(s=>{const p=JPRail.map.latLngToContainerPoint([s[1],s[2]]);return [p.x,p.y]})')
        for x,y in points:draw.ellipse((x-7,y-7,x+7,y+7),fill=0)
        total=lost=0
        for before,after,visible in zip(rails.getdata(),shown.getdata(),mask.getdata()):
            r,g,b=before
            if visible and r>240 and 110<g<145 and b<15:
                total+=1
                if sum(abs(a-b) for a,b in zip(before,after))>60:lost+=1
        self.assertGreater(total,200)
        self.assertLess(lost/total,.02,'station label halos must not break railway strokes')

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
                    if os.environ.get('JPRAIL_BROWSER_TIMEOUT_MS'):
                        page.set_default_timeout(int(os.environ['JPRAIL_BROWSER_TIMEOUT_MS']))
                        page.set_default_navigation_timeout(int(os.environ['JPRAIL_BROWSER_TIMEOUT_MS']))
                    page.goto(base+'/JPRail.html')
                    page.wait_for_function('window.JPRail?.state.stations.length>0')
                    page.wait_for_function('JPRail.state.stationLabels.count>0')
                    self.assertFalse(page.locator('#detailPanel').is_visible())
                    wide=page.locator('.map-section').bounding_box()['width']
                    workspace=page.locator('.workspace').bounding_box();section=page.locator('.map-section').bounding_box()
                    self.assertAlmostEqual(section['x']+section['width'],workspace['x']+workspace['width'],delta=1)
                    self.assertEqual(page.evaluate("JPRail.railStyle({properties:{grade:'main'}}).weight"),3)
                    self.assertEqual(page.evaluate("JPRail.railStyle({properties:{grade:'highspeed'}}).weight"),4)
                    page.set_viewport_size({'width':1800,'height':1120})
                    page.wait_for_function('Math.abs(JPRail.map.getSize().x-document.getElementById("map").clientWidth)<1')
                    section=page.locator('.map-section').bounding_box();workspace=page.locator('.workspace').bounding_box()
                    self.assertAlmostEqual(section['x']+section['width'],workspace['x']+workspace['width'],delta=1)
                    wide1800=section['width']
                    page.locator('[data-pass="japan"]').click()
                    self.assertAlmostEqual(wide1800-page.locator('.map-section').bounding_box()['width'],340,delta=1)
                    page.locator('#clearSelection').click()
                    self.assertAlmostEqual(page.locator('.map-section').bounding_box()['width'],wide1800,delta=1)
                    page.set_viewport_size({'width':1440,'height':960})
                    page.wait_for_function('Math.abs(JPRail.map.getSize().x-document.getElementById("map").clientWidth)<1')
                    page.locator('#resetView').click();page.wait_for_function('JPRail.camera.whenIdle()')
                    self.assertEqual(page.evaluate('JPRail.state.stationLabels.mode'),'主要枢纽')
                    initial=page.evaluate('JPRail.map.getZoom()')
                    self.assertGreater(initial,4)
                    page.evaluate('''() => {window.zoomEvents={start:0,end:0};JPRail.map.on('zoomstart',()=>zoomEvents.start++);JPRail.map.on('zoomend',()=>zoomEvents.end++);}''')
                    page.get_by_role('button',name='放大',exact=True).click()
                    page.wait_for_function('JPRail.camera.whenIdle()');page.wait_for_timeout(300)
                    self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),initial+.25,places=6)
                    self.assertEqual(page.evaluate('zoomEvents'),{'start':1,'end':1})
                    page.evaluate('zoomEvents={start:0,end:0}')
                    page.get_by_role('button',name='放大',exact=True).dblclick()
                    page.wait_for_function('JPRail.camera.whenIdle()');page.wait_for_timeout(300)
                    self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),initial+.75,places=6)
                    self.assertEqual(page.evaluate('zoomEvents'),{'start':1,'end':1})
                    wheel_start=page.evaluate('JPRail.map.getZoom()');page.evaluate('zoomEvents={start:0,end:0}')
                    page.evaluate('''() => new Promise(resolve=>{
                      const el=document.getElementById('map'),b=el.getBoundingClientRect();
                      const fire=()=>el.dispatchEvent(new WheelEvent('wheel',{deltaY:-20,clientX:b.x+b.width/2,clientY:b.y+b.height/2,bubbles:true,cancelable:true}));
                      fire();for(const t of [10,25,70,100,135])setTimeout(fire,t);setTimeout(resolve,150);
                    })''')
                    page.wait_for_function('JPRail.camera.whenIdle()');page.wait_for_timeout(300)
                    self.assertGreater(page.evaluate('JPRail.map.getZoom()'),wheel_start)
                    self.assertLessEqual(page.evaluate('JPRail.map.getZoom()')-wheel_start,.200001)
                    self.assertEqual(page.evaluate('zoomEvents'),{'start':1,'end':1})
                    page.locator('#resetView').click();page.wait_for_function('JPRail.camera.whenIdle()')
                    initial=page.evaluate('JPRail.map.getZoom()')
                    box=page.locator('#map').bounding_box()
                    page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
                    page.mouse.wheel(0,-700)
                    page.wait_for_function('(z)=>JPRail.map.getZoom()>z',arg=initial)
                    page.wait_for_function('JPRail.camera.whenIdle()')
                    self.assertLessEqual(page.evaluate('JPRail.map.getZoom()')-initial,.5)
                    page.locator('#resetView').click();page.wait_for_function('JPRail.camera.whenIdle()')
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
                    self.assertTrue(page.locator('#detailPanel').is_visible())
                    self.assertAlmostEqual(wide-page.locator('.map-section').bounding_box()['width'],300,delta=1)
                    page.wait_for_function('Math.abs(JPRail.map.getSize().x-document.getElementById("map").clientWidth)<1')
                    self.assertIn('¥50,000',page.locator('.price-section').inner_text())
                    self.assertIn('¥100,000',page.locator('.price-section').inner_text())
                    self.assertIn('¥53,000',page.locator('.price-section').inner_text())
                    page.locator('[data-pass="hokkaido"]').click()
                    self.assertEqual(page.evaluate('JPRail.state.selected'),'hokkaido')
                    self.assertEqual(page.locator('.pass-card[aria-pressed="true"]').count(),1)
                    self.assertTrue(page.evaluate("JPRail.state.displayed.every(f=>f.properties.operator==='北海道旅客鉄道')"))
                    self.assertTrue(page.locator('#infrastructure').is_disabled())
                    self.assertFalse(page.locator('#infrastructure').is_checked())
                    self.assertTrue(page.evaluate("[...JPRail.state.layers.values()].every(l=>l.getLayers().every(p=>p.options.color===JPRail.railStyle(p.feature).color&&!p.options.dashArray))"))
                    page.locator('#clearSelection').click()
                    self.assertFalse(page.locator('#detailPanel').is_visible())
                    self.assertAlmostEqual(page.locator('.map-section').bounding_box()['width'],wide,delta=1)
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
                    page.locator('[data-pass="hokuriku"]').click();page.wait_for_function('JPRail.camera.whenIdle()')
                    page.wait_for_function('JPRail.state.stationLabels.boundaryNames.includes("黒部宇奈月温泉")')
                    self.assertFalse(page.evaluate('JPRail.state.pinnedStations.some(p=>p.name==="上越妙高")'))
                    self.assertTrue(page.evaluate('["高山線","小浜線","IRいしかわ鉄道線"].every(n=>JPRail.state.displayed.some(f=>f.properties.name===n))'))
                    self.assertTrue(page.evaluate('JPRail.state.stationPool.some(s=>s[0]==="黒部宇奈月温泉")'))
                    self.assertTrue(page.evaluate('''() => {const p=JPRail.state.passes.find(p=>p.id==='hokuriku');return p.routeOverridesOnly&&p.routeFeatures.filter(f=>f.properties.grade==='highspeed').every(f=>(f.geometry.type==='LineString'?f.geometry.coordinates:f.geometry.coordinates.flat()).every(c=>c[0]<137.6));}'''))
                    self.assertTrue(page.evaluate('JPRail.state.boundaryMarkers.getLayers().every(l=>l.options.radius>=4)&&JPRail.state.boundaryMarkers.getLayers().some(l=>l.options.radius>=6)'))
                    page.locator('[data-pass="kansai-hokuriku"]').click();page.wait_for_function('JPRail.camera.whenIdle()')
                    self.assertTrue(page.evaluate('JPRail.state.pinnedStations.some(p=>p.name==="上越妙高"&&p.boundaryKind==="company")'))
                    page.wait_for_function('JPRail.state.stationLabels.companyNames.includes("上越妙高")')
                    self.assertIn('本券止于公司局界',page.locator('.company-boundary-note').inner_text())
                    page.locator('[data-pass="west-all"]').click()
                    self.assertTrue(page.evaluate('["上越妙高","南小谷","米原","猪谷","新宮"].every(n=>JPRail.state.pinnedStations.some(p=>p.name===n&&p.boundaryKind==="company"))'))
                    page.locator('[data-pass="japan"]').click()
                    page.locator('#railOperator').select_option('西日本旅客鉄道')
                    self.assertFalse(page.evaluate('JPRail.state.pinnedStations.some(p=>p.boundaryKind==="company")'),'filtering an internal JR company must not turn it into a pass boundary')
                    page.locator('#clearSelection').click();page.locator('#clearRailFilters').click()
                    page.locator('#passSearch').fill('近铁');self.assertEqual(page.locator('.pass-card').count(),4)
                    page.locator('[data-pass="kintetsu1"]').click();page.wait_for_function('JPRail.camera.whenIdle()')
                    self.assertTrue(page.evaluate('JPRail.state.pinnedStations.every(p=>JPRail.map.getBounds().contains([p.station[1],p.station[2]]))'))
                    page.wait_for_function('JPRail.state.detailStatus==="detail"')
                    self.assertEqual(len(page.evaluate('JPRail.state.pinnedStations')),9)
                    for zoom in (4,7,11,16):
                        page.evaluate('(z)=>{JPRail.map.setZoom(z,{animate:false});}',zoom)
                        page.wait_for_function('JPRail.camera.whenIdle()')
                        expected='detail' if zoom>=10 else 'overview'
                        self.assertEqual(page.evaluate('JPRail.state.detailStatus'),expected)
                        self.assertTrue(page.evaluate('(detail)=>JPRail.state.network===(detail?JPRail.state.detailNetwork:JPRail.state.overviewNetwork)',zoom>=10))
                        self.assertTrue(page.evaluate('(detail)=>[...JPRail.state.layers.values()][0].getLayers().every(l=>l.options.smoothFactor===(detail?.15:1))',zoom>=10))
                        page.wait_for_function('''() => {const shown=new Set(JPRail.state.stationLabels.pinnedNames),b=JPRail.map.getBounds();return JPRail.state.pinnedStations.filter(p=>b.contains([p.station[1],p.station[2]])).every(p=>shown.has(p.name));}''')
                        self.assertFalse(page.evaluate('JPRail.state.stationLabels.texts.some(t=>t.endsWith(" 界"))'))
                    self.assertEqual(page.locator('[data-boundary="近鉄奈良"]').inner_text(),'近鉄奈良')
                    self.assertTrue(page.evaluate('''() => {
                        const p=JPRail.state.passes.find(p=>p.id==='kintetsu1');
                        const points=fs=>fs.filter(f=>f.properties.name==='奈良線').reduce((n,f)=>n+(f.geometry.type==='LineString'?f.geometry.coordinates.length:f.geometry.coordinates.reduce((a,c)=>a+c.length,0)),0);
                        return points(p.routeFeatures)>4*points(p.overviewRouteFeatures);
                    }'''))
                    self.assertFalse(page.evaluate("JPRail.state.displayed.some(f=>f.properties.name==='生駒線')"))
                    page.locator('[data-pass="kintetsu5"]').click()
                    page.locator('#passSearch').fill('')
                    for pid,center,zoom in [('kintetsu5',[34.65,136.4],11),('japan',[35.68,139.76],12),('kyushu',[33.27,130.3],10.8)]:
                        page.locator('[data-pass="'+pid+'"]').click()
                        page.wait_for_function('JPRail.camera.whenIdle()')
                        page.evaluate('(v)=>JPRail.camera.setView(v[0],v[1])',[center,zoom])
                        page.wait_for_function('JPRail.camera.whenIdle()')
                        page.wait_for_function('JPRail.state.detailStatus==="detail"')
                        page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
                        with self.subTest(label_visibility=pid):self.assert_rail_strokes_visible(page)
                    page.locator('[data-pass="kintetsu5"]').click()
                    page.locator('#startDate').fill('2026-12-30');page.locator('#startDate').dispatch_event('change')
                    self.assertIn('2027-01-03',page.locator('#dateResult').inner_text())
                    self.assertTrue(page.evaluate("JPRail.state.displayed.every(f=>['近畿日本鉄道','伊賀鉄道'].includes(f.properties.operator))"))
                    page.locator('#closeDetail').click();self.assertIsNone(page.evaluate('JPRail.state.active'))
                    self.assertFalse(page.locator('#detailPanel').is_visible())
                    self.assertAlmostEqual(page.locator('.map-section').bounding_box()['width'],wide,delta=1)
                    page.locator('[data-focus="kintetsu5"]').click()
                    self.assertTrue(page.locator('#detailPanel').is_visible())
                    page.locator('#passSearch').fill('');page.locator('#showEnded').check()
                    page.locator('[data-pass="kansai-old"]').click();self.assertIn('历史票券',page.locator('#dateResult').inner_text())
                    page.locator('#stationSearch').fill('京都');page.wait_for_selector('[data-station]')
                    page.locator('[data-station]').first.click();page.wait_for_function('JPRail.map.getZoom()===13')
                    page.wait_for_function('JPRail.state.stationLabels.mode==="区域车站"')
                    page.evaluate('() => {JPRail.map.setZoom(16,{animate:false});}')
                    page.wait_for_function('JPRail.state.stationLabels.mode==="当前视野全部车站"')
                    self.assertTrue(page.evaluate('''() => {
                      const map=JPRail.map,size=map.getSize(),shown=new Set(JPRail.state.stationLabels.names);
                      return JPRail.state.stationPool.every(s=>{const p=map.latLngToContainerPoint([s[1],s[2]]);return p.x<0||p.y<0||p.x>size.x||p.y>size.y||shown.has(s[0]);});
                    }'''))
                    page.locator('#closeDetail').click()
                    page.locator('[data-pass="hokuriku"]').click()
                    for width,height in [(1440,660),(1800,1440),(1800,1800)]:
                        page.set_viewport_size({'width':width,'height':height})
                        page.wait_for_function('Math.abs(JPRail.map.getSize().x-document.getElementById("map").clientWidth)<1')
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollHeight-innerHeight'),1)
                        self.assertAlmostEqual(page.locator('.page-foot').bounding_box()['y']+page.locator('.page-foot').bounding_box()['height'],height,delta=1)
                        if height==1800:self.assertGreater(page.locator('#map').bounding_box()['height'],1100)
                    page.locator('.rail-legend summary').click();self.assertIn('主干线',page.locator('.rail-legend').inner_text())
                    for width in (320,390,768,1100):
                        page.set_viewport_size({'width':width,'height':844})
                        self.assertFalse(page.evaluate('document.documentElement.scrollWidth>innerWidth+1'))
                    page.locator('#aboutBtn').click();self.assertTrue(page.locator('#aboutDialog').is_visible())
                    page.locator('#closeAbout').click();self.assertEqual(errors,[])
                finally:browser.close()
        finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
