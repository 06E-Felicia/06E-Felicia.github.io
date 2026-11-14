"""Independent route browsing, named main-line families and metro clipping.

No replay/trace files. JPRAIL_FILTER_REVIEW may name one final screenshot;
temporary browser images belong in the caller's system temp directory.
"""
import functools
import importlib.util
import json
import math
import os
from pathlib import Path
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'assets/data/jprail'


def choose_operators(page,values):
    """Set the serialized selection for non-UI catalogue regressions.

    The actual touch/keyboard checkbox path is covered separately below.
    """
    if isinstance(values,str):values=[values] if values else []
    page.locator('#railOperator').evaluate('''(el,values)=>{
      for(const value of values)if(![...el.options].some(o=>o.value===value))throw new Error('Missing operator '+value);
      for(const option of el.options)option.selected=values.includes(option.value);
      el.dispatchEvent(new Event('change',{bubbles:true}));
    }''',values)


class FilterData(unittest.TestCase):
    def test_metro_boundaries_are_station_nodes_in_both_levels(self):
        from collections import Counter
        data=json.loads((DATA/'metro-ranges.json').read_text())['metros']
        self.assertEqual(len(data),11)
        for metro,record in data.items():
            expected={}
            for level in ['overview','detail']:
                for feature in record[level]:
                    p=feature['properties'];key=p['operator'],p['name']
                    stations={(round(s[2],5),round(s[1],5)) for s in record['stations'] if (s[3],s[4])==key}
                    lines=feature['geometry']['coordinates'] if feature['geometry']['type']=='MultiLineString' else [feature['geometry']['coordinates']]
                    # Only graph leaves are outer limits. An internal branch
                    # junction is allowed to split a MultiLineString.
                    degrees=Counter()
                    for line in lines:
                        degrees[tuple(round(v,5) for v in line[0])]+=1
                        degrees[tuple(round(v,5) for v in line[-1])]+=1
                    ends={n for n,d in degrees.items() if d==1}
                    self.assertTrue(ends<=stations,(metro,key,ends-stations))
                    if level=='overview':expected[key]=ends
                    else:self.assertEqual(ends,expected[key],(metro,key,'LOD must not move boundaries'))
        chukyo=data['chukyo']['stations']
        west={s[0] for s in chukyo if s[3]=='西日本旅客鉄道' and s[4]=='東海道線' and s[5]}
        private={s[0] for s in chukyo if s[3]=='近江鉄道' and s[4]=='八日市線' and s[5]}
        shinkansen={s[0] for s in chukyo if s[3]=='東海旅客鉄道' and s[4]=='東海道新幹線' and s[5]}
        self.assertEqual(west,{'安土','米原'});self.assertEqual(private,{'八日市','武佐'})
        self.assertEqual(shinkansen,{'米原','豊橋'})

    def test_compiler_keeps_real_curves_and_stops_at_inside_stations(self):
        from development.scripts.build_jprail_metro_ranges import station_graph,station_paths
        feature={'type':'Feature','properties':{'operator':'fixture','name':'line'},'geometry':{'type':'LineString','coordinates':[[-2,0],[-.5,0],[0,.1],[.5,0],[2,0]]}}
        stations=[['outside west',0,-2,'fixture','line'],['west',0,-.5,'fixture','line'],['east',0,.5,'fixture','line'],['outside east',0,2,'fixture','line']]
        graph,anchors,coords=station_graph(feature,stations)
        selected,_=station_paths(graph,anchors,{'circles':[{'lng':0,'lat':0,'km':111.195}]})
        self.assertEqual(selected,{((-.5,0),(0,.1)),((0,.1),(.5,0))})

    def test_named_families_resolve_in_both_geometry_levels(self):
        data=json.loads((DATA/'line-filters.json').read_text())
        self.assertEqual(len(data['families']),28)
        self.assertEqual(len({f['id'] for f in data['families']}),28)
        self.assertEqual(len(data['metros']),11)
        for source in data['sources'].values():self.assertTrue(source.startswith('https://'))
        for filename in ['network.geojson','network-detail.geojson']:
            fs=json.loads((DATA/filename).read_text())['features']
            keys={(f['properties']['operator'],f['properties']['name']) for f in fs}
            transferred=[]
            for family in data['families']:
                self.assertTrue(any(f['properties']['name'] in family['jrNames'] and '旅客鉄道' in f['properties']['operator'] for f in fs),family['id'])
                self.assertTrue(set(family['sources'])<=data['sources'].keys())
                for pair in family['transfers']:
                    self.assertIn(tuple(pair),keys);transferred.append(tuple(pair))
            self.assertEqual(len(transferred),10)
            self.assertEqual(len(set(transferred)),10,'a transferred line must not be borrowed by two families')


@unittest.skipUnless(importlib.util.find_spec('playwright'),'Playwright required')
class FilterBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.pw=sync_playwright().start();cls.browser=cls.pw.chromium.launch(channel='chrome',headless=True)
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
        from collections import defaultdict
        cls.source_stations=defaultdict(list)
        for st in json.loads((DATA/'stations.json').read_text()):cls.source_stations[st[0],st[3],st[4]].append(st)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop();cls.server.shutdown();cls.server.server_close()

    def page(self,width=1440,height=960,query=''):
        context=self.browser.new_context(viewport={'width':width,'height':height})
        context.route('**/*',lambda r:r.continue_() if urlsplit(r.request.url).hostname=='127.0.0.1' else r.abort())
        page=context.new_page();self.errors=[];page.on('pageerror',lambda e:self.errors.append(str(e)))
        page.goto(self.base+'/JPRail.html'+query,wait_until='domcontentloaded')
        page.wait_for_function('window.JPRail?.state.stations.length>0');self.settle(page)
        self.addCleanup(context.close)
        return page

    @staticmethod
    def in_metro(st,metro):
        return any(math.hypot((st[2]-c['lng'])*111.195*math.cos(math.radians(c['lat'])),(st[1]-c['lat'])*111.195)<=c['km']+1e-8 for c in metro['circles'])

    def settle(self,page):
        page.wait_for_function('JPRail.camera.whenIdle()')
        page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')

    def test_operator_union_pass_exclusion_and_url_round_trip(self):
        page=self.page(query='?pass=hokuriku')
        self.assertTrue(page.locator('#detailPanel').is_visible())
        page.locator('#railOperatorPicker>summary').click()
        for op in ['東日本旅客鉄道','東海旅客鉄道','近畿日本鉄道']:
            page.locator('[data-rail-operator="'+op+'"]').check()
        self.settle(page)
        expected=['東日本旅客鉄道','東海旅客鉄道','近畿日本鉄道']
        self.assertEqual(set(page.evaluate('JPRail.state.routeFilters.operators')),set(expected))
        self.assertIsNone(page.evaluate('JPRail.state.selected'))
        self.assertIsNone(page.evaluate('JPRail.state.active'))
        self.assertFalse(page.locator('#detailPanel').is_visible())
        self.assertEqual(page.evaluate('JPRail.state.pinnedStations.length'),0)
        self.assertTrue(page.evaluate('(ops)=>{const key=f=>f.properties.operator+"|"+f.properties.name;const want=JPRail.state.network.features.filter(f=>ops.includes(f.properties.operator)&&JPRail.railColors.isRailway(f)).map(key).sort();return JSON.stringify(want)===JSON.stringify(JPRail.state.displayed.map(key).sort())}',expected))
        self.assertIn('3 家',page.locator('#railOperatorValue').inner_text())
        page.keyboard.press('Escape');self.assertFalse(page.locator('#railOperatorPicker').evaluate('e=>e.open'))
        page.reload();page.wait_for_function('window.JPRail?.state.stations.length>0');self.settle(page)
        self.assertEqual(set(page.evaluate('JPRail.state.routeFilters.operators')),set(expected))
        page.locator('[data-pass="japan"]').click();self.settle(page)
        self.assertEqual(page.evaluate('JPRail.state.routeFilters.operators'),[])
        self.assertEqual(page.evaluate('JPRail.state.selected'),'japan')
        page.locator('#railMetro').select_option('tokyo');self.settle(page)
        self.assertIsNone(page.evaluate('JPRail.state.selected'))
        self.assertFalse(page.locator('#detailPanel').is_visible())
        page.locator('#resetView').click();self.settle(page)
        self.assertTrue(page.evaluate('''()=>['pass','grade','operator','excludeOperator','metro','line'].every(k=>!new URL(location.href).searchParams.has(k))'''))
        page.locator('#railOperatorPicker>summary').click()
        page.locator('[data-operator-group="private"]').click();self.settle(page)
        self.assertEqual(page.locator('[data-rail-operator]:checked').count(),112)
        page.locator('[data-rail-operator="近畿日本鉄道"]').uncheck();self.settle(page)
        self.assertLess(len(page.url),400,'bulk operator selection must not create an oversized URL')
        page.reload();page.wait_for_function('window.JPRail?.state.stations.length>0');self.settle(page)
        self.assertEqual(page.locator('[data-rail-operator]:checked').count(),111)
        self.assertFalse(page.locator('[data-rail-operator="近畿日本鉄道"]').is_checked())
        self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>f.properties.operator==="近畿日本鉄道")'))
        self.assertEqual(self.errors,[])

    def test_grey_context_is_visible_for_filters_and_passes(self):
        import io
        from PIL import Image,ImageChops
        page=self.page(query='?metro=chukyo')
        from development.tests.test_jprail_audit import RenderedCatalogue
        checker=RenderedCatalogue('test_every_pass_and_continuous_zoom')
        for mode in ['metro','pass']:
            if mode=='pass':page.locator('[data-pass="hokuriku"]').click();self.settle(page)
            page.evaluate('JPRail.camera.setView([35.125,136.12],13)');self.settle(page)
            page.wait_for_function('JPRail.state.detailStatus==="detail"')
            checker.check_rendered_layers(page)
            self.assertTrue(page.evaluate('''()=>{
             const c=JPRail.map.getPane('railContext').querySelector('canvas'),data=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
             let found=0;for(let i=0;i<data.length;i+=4)if(Math.abs(data[i]-163)<=2&&Math.abs(data[i+1]-173)<=2&&Math.abs(data[i+2]-183)<=2&&Math.abs(data[i+3]-153)<=2)found++;
             return found>100;
            }'''))
            shown=Image.open(io.BytesIO(page.locator('#map').screenshot())).convert('RGB')
            page.evaluate('JPRail.map.getPane("railContext").style.visibility="hidden"')
            plain=Image.open(io.BytesIO(page.locator('#map').screenshot())).convert('RGB')
            page.evaluate('JPRail.map.getPane("railContext").style.visibility=""')
            changed=sum(max(pixel)>8 for pixel in ImageChops.difference(shown,plain).getdata())
            self.assertGreater(changed,100,'context must be visible outside the opaque matching paths')
        page.locator('#resetView').click();self.settle(page)
        self.assertIsNone(page.evaluate('JPRail.state.contextLayer'))
        self.assertEqual(page.evaluate('JPRail.state.paintContextFeatures.length'),0)
        self.assertEqual(self.errors,[])

    def test_metro_keeps_shinkansen_as_context_and_preserves_station_data(self):
        page=self.page(query='?metro=tokyo&grade=highspeed')
        self.assertEqual(page.locator('#railGrade').input_value(),'highspeed')
        self.assertEqual(page.evaluate('JPRail.state.displayed.length'),0)
        self.assertTrue(page.evaluate('JPRail.state.paintContextFeatures.some(f=>f.properties.kind==="1")'))
        self.assertTrue(page.evaluate('JPRail.routeFilters.metroStations("tokyo").some(s=>s[4].includes("新幹線"))'))
        self.assertTrue(page.evaluate('JPRail.state.stations.some(s=>s[0]==="岐阜羽島"&&s[4]==="東海道新幹線")'))
        page.locator('#stationSearch').fill('岐阜羽島')
        page.wait_for_selector('[data-station]')
        self.assertGreater(page.locator('[data-station]').count(),0)
        page.locator('#resetView').click();self.settle(page)
        page.locator('#railGrade').select_option('highspeed');self.settle(page)
        self.assertTrue(page.evaluate('JPRail.state.displayed.some(f=>f.properties.kind==="1")'))
        page.locator('#railMetro').select_option('tokyo');self.settle(page)
        self.assertEqual(page.locator('#railGrade').input_value(),'highspeed')
        self.assertEqual(page.evaluate('JPRail.state.displayed.length'),0)
        self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>f.properties.kind==="1")'))
        self.assertTrue(page.evaluate('JPRail.state.paintContextFeatures.some(f=>f.properties.kind==="1")'))
        page.locator('#railGrade').select_option('');self.settle(page)
        self.assertGreater(page.evaluate('JPRail.state.displayed.length'),0)
        self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>f.properties.kind==="1")'))
        page.locator('[data-pass="japan"]').click();self.settle(page)
        self.assertTrue(page.evaluate('JPRail.state.displayed.some(f=>f.properties.kind==="1")'))
        self.assertEqual(self.errors,[])

    def test_all_mainline_families_and_transferred_sections(self):
        page=self.page();page.locator('#railGrade').select_option('main')
        config=json.loads((DATA/'line-filters.json').read_text())
        fs=json.loads((DATA/'network.geojson').read_text())['features']
        for family in config['families']:
            with self.subTest(family=family['id']):
                page.locator('#railLine').select_option(family['id']);self.settle(page)
                actual={tuple(row) for row in page.evaluate('JPRail.state.displayed.map(f=>[f.properties.operator,f.properties.name])')}
                expected={(f['properties']['operator'],f['properties']['name']) for f in fs if f['properties']['name'] in family['jrNames'] and '旅客鉄道' in f['properties']['operator']}
                expected|={tuple(pair) for pair in family['transfers']}
                self.assertEqual(actual,expected)
                self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>f.properties.kind==="1")'))
        # Formal line names, not the OSM "main" tag: San-in must be included;
        # the unrelated private Yamaguchi line must not become JR local rail.
        page.locator('#railLine').select_option('sanin');self.settle(page)
        self.assertEqual({f[1] for f in page.evaluate('JPRail.state.displayed.map(f=>[f.properties.operator,f.properties.name])')},{'山陰線'})
        page.locator('#railLine').select_option('hokuriku');self.settle(page)
        self.assertEqual(page.locator('#railResults .rail-result-line').count(),1)
        self.assertIn('IRいしかわ鉄道',page.locator('#railResults').text_content())
        choose_operators(page,['IRいしかわ鉄道','ハピラインふくい']);self.settle(page)
        self.assertEqual(page.evaluate('JPRail.state.displayed.length'),2)
        page.locator('#railGrade').select_option('private');self.settle(page)
        self.assertEqual(page.evaluate('JPRail.state.displayed.length'),2,'transferred lines remain private under current ownership')
        choose_operators(page,'');page.locator('#railGrade').select_option('branch');self.settle(page)
        self.assertTrue(page.evaluate('JPRail.state.displayed.some(f=>f.properties.name==="山手線")'))
        self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>f.properties.operator==="西武鉄道")'))
        self.assertEqual(self.errors,[])

    def test_every_metro_has_bounded_routes_stations_and_real_paint(self):
        page=self.page();config=json.loads((DATA/'line-filters.json').read_text())
        from development.tests.test_jprail_audit import RenderedCatalogue
        checker=RenderedCatalogue('test_every_pass_and_continuous_zoom')
        counts={}
        for metro in config['metros']:
            page.locator('#railMetro').select_option(metro['id']);self.settle(page)
            self.assertIn('着色在车站收尾',page.locator('#railFilterNote').inner_text())
            rows=page.evaluate('''()=>({stations:JPRail.state.stationPool.map(s=>[s[0],s[2],s[1],s[3],s[4]]),routes:JPRail.state.displayed.length})''')
            self.assertGreater(rows['routes'],0);self.assertGreater(len(rows['stations']),10)
            for name,x,y,op,line in rows['stations']:
                original=[st for st in self.source_stations[(name,op,line)] if self.in_metro(st,metro)]
                self.assertTrue(original,(metro['id'],name,op,line))
                self.assertLess(min(math.hypot(st[2]-x,st[1]-y) for st in original),.0018)
            self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>!JPRail.railColors.isRailway(f))'))
            self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>f.properties.kind==="1")'))
            self.assertEqual(page.evaluate('JPRail.state.pinnedStations.length'),0)
            checker.check_rendered_layers(page)
            if metro['id'] in ['tokyo','keihanshin','kitakyushu-fukuoka']:
                point=page.evaluate('''()=>{const lines=JPRail.state.displayed.flatMap(f=>f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates),line=lines.reduce((a,b)=>a.length>b.length?a:b);return line[Math.floor(line.length/2)];}''')
                page.evaluate('(p)=>JPRail.camera.setView([p[1],p[0]],13)',point);self.settle(page)
                page.wait_for_function('JPRail.state.detailStatus==="detail"')
                self.assertFalse(page.evaluate('JPRail.state.displayed.some(f=>f.properties.kind==="1")'))
                checker.check_rendered_layers(page)
                samples=checker.check_paint(page);self.assertGreater(samples,0)
            counts[metro['id']]=rows['routes']
        choose_operators(page,'北海道旅客鉄道');self.settle(page)
        self.assertEqual(page.evaluate('JPRail.state.displayed.length'),0)
        self.assertIn('请调整筛选',page.locator('#mapState').inner_text())
        self.assertEqual(self.errors,[])
        print('metro route groups:',json.dumps(counts),flush=True)

    def test_picker_search_keyboard_and_mobile_map_space(self):
        for width,height in [(1440,960),(1100,800),(390,844),(320,640)]:
            with self.subTest(viewport=(width,height)):
                page=self.page(width,height)
                page.locator('#railOperatorPicker>summary').click()
                page.locator('#railOperatorSearch').fill('JR东日本')
                visible=page.locator('#railOperatorList label:visible')
                self.assertEqual(visible.count(),1)
                self.assertIn('东日本',visible.inner_text())
                visible.locator('input').check();self.settle(page)
                menu=page.locator('.operator-menu').bounding_box()
                self.assertGreaterEqual(menu['x'],0);self.assertLessEqual(menu['x']+menu['width'],width)
                self.assertEqual(page.evaluate('document.documentElement.scrollWidth-innerWidth'),0)
                page.keyboard.press('Escape');self.assertFalse(page.locator('#railOperatorPicker').evaluate('e=>e.open'))
                self.assertGreater(page.locator('#map').bounding_box()['height'],300)
                page.locator('.rail-results>summary').click()
                results=page.locator('#railResults').bounding_box()
                self.assertGreaterEqual(results['x'],0);self.assertLessEqual(results['x']+results['width'],width)
                page.locator('.rail-results>summary').click()
                page.locator('#railGrade').select_option('main');page.locator('#railLine').select_option('tohoku')
                page.locator('#railMetro').select_option('sendai');self.settle(page)
                self.assertGreater(page.evaluate('JPRail.state.displayed.length'),0)
                self.assertTrue(page.evaluate('JPRail.state.displayed.every(f=>f.properties.operator==="東日本旅客鉄道")'))
                if os.environ.get('JPRAIL_FILTER_REVIEW') and width==1440:
                    page.locator('#clearRailFilters').click();page.locator('#railGrade').select_option('main');page.locator('#railLine').select_option('hokuriku');self.settle(page)
                    page.screenshot(path=os.environ['JPRAIL_FILTER_REVIEW'])
                self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main()
