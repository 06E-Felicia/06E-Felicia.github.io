"""Independent fare-boundary regressions and full-catalogue rendered-map audit.

JPRAIL_BASE_URL may point at Pages. Screenshots stay in memory; optional current
review image is overwritten at JPRAIL_REVIEW_IMAGE. No replay / browser traces.
"""
import functools
import io
import json
import math
import os
from pathlib import Path
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import importlib.util
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'assets/data/jprail'

class FareRegressions(unittest.TestCase):
    def test_independent_official_boundaries_and_exclusions(self):
        passes={p['id']:p for p in json.loads((DATA/'passes.json').read_text())['passes']}
        audit={p['id']:p for p in json.loads((DATA/'pass-audit.json').read_text())['records']}
        self.assertEqual(set(passes),set(audit))
        for id,p in passes.items():
            with self.subTest(id=id):
                self.assertTrue(audit[id]['sources'])
                self.assertTrue(audit[id]['finding'])
                self.assertEqual(p['audit']['status'],audit[id]['status'])
                self.assertEqual(bool(p['audit']['issues']),audit[id]['status']=='partial')
                self.assertTrue(all('bbox' not in s for s in p['selectors']),'fare boundaries must never come from rectangular clipping')
                self.assertEqual({s['name'] for s in p['stationPins']['stations'] if s['role']=='boundary'},set(audit[id]['boundaries']))
        # Expectations below are explicit readings of different official maps,
        # not auto-generated endpoint lists from the route under test.
        positive={'hokuriku-arch':{'亀岡','塩尻','猪谷','南小谷'},'hokuriku':{'黒部宇奈月温泉','猪谷','小浜'},'kansai-hokuriku':{'上越妙高','南小谷','猪谷','児島','新宮'},'tottori-matsue':{'東浜','出雲市','木次','根雨','郡家'},'kintetsu1':{'筒井','生駒','長田'},'kintetsu2':{'三本松'},'kawagoe':{'池袋','川越市'},'seibu-nagatoro':{'野上'},'north-kyushu':{'宇土','大分','熊本'},'south-kyushu':{'熊本','大分','八代','川内'}}
        negative={'hokuriku-arch':{'松本','高尾','園部','上越妙高','敦賀'},'japan':{'東京','新大阪','博多','上越妙高','猪谷','米原'},'hokuriku':{'上越妙高','富山','高岡'},'kansai-hokuriku':{'敦賀','高松','富山','金沢'},'kawagoe':{'川越'},'nikko-all':{'下今市'},'nikko-heritage':{'下今市'},'seibu-nagatoro':{'長瀞'},'hakone-kamakura':{'小田原','箱根湯本','強羅'},'sanyo-kyushu':{'博多','下関'},'alpine':{'猪谷','松本','塩尻'},'ise':{'新宮','亀山'}}
        for id,names in positive.items():self.assertTrue(names<=set(audit[id]['boundaries']),(id,names-set(audit[id]['boundaries'])))
        for id,names in negative.items():self.assertFalse(names&set(audit[id]['boundaries']),(id,names&set(audit[id]['boundaries'])))
        def all_ops(id):return {op for s in passes[id]['selectors'] for op in s['operators']}
        self.assertNotIn('江ノ島電鉄',all_ops('greater-tokyo'))
        arch_lines={line for s in passes['hokuriku-arch']['selectors'] if s['operators']==['東日本旅客鉄道'] for line in s.get('lineNames',[])}
        self.assertTrue({'中央線','篠ノ井線'}<=arch_lines)
        self.assertIn('ゆりかもめ',all_ops('greater-tokyo'))
        self.assertTrue({'智頭急行','WILLER　TRAINS','和歌山電鐵'}<=all_ops('kansai-wide'))
        self.assertNotIn('智頭急行',all_ops('kansai-hokuriku'))
        self.assertTrue({'万葉線','えちぜん鉄道','富山地方鉄道'}<=all_ops('hokuriku'))
        self.assertTrue(any(s[1:] == ['山陰線','東浜','出雲市'] for s in passes['tottori-matsue']['railOverrides']))
        intervals=json.loads((DATA/'pass-ranges-detail.json').read_text())
        forbidden={'hokuriku-arch':['並河','毛呂'],'tokyo-wide':['信濃境','小木津','高久','下野宮','石打','中軽井沢'],'kansai-mini':['朝霧','生瀬','馬堀','長滝'],'kintetsu1':['平端','白庭台','菜畑'],'kintetsu2':['赤目口','名張'],'north-kyushu':['松橋','牧'],'tottori-matsue':['西出雲','黒坂','下久野','河原','居組'],'hokuriku':['糸魚川','杉原','能登中島']}
        for id,names in forbidden.items():
            for name in names:self.assertFalse(any(k.endswith('|'+name) for k in intervals[id]['stationKeys']),(id,name,'range overrun'))
        stations=json.loads((DATA/'stations.json').read_text())
        self.assertTrue(any(s[0]=='上越妙高' and s[3]=='西日本旅客鉄道' for s in stations))
        self.assertTrue(any(s[0]=='上越妙高' and s[3]=='えちごトキめき鉄道' for s in stations))
        source=(ROOT/'assets/scripts/jprail-boundaries.js').read_text()
        self.assertNotIn('reaches(',source)

    def test_lod_keeps_the_same_interval_topology(self):
        detail=json.loads((DATA/'pass-ranges-detail.json').read_text());overview=json.loads((DATA/'pass-ranges.json').read_text())
        self.assertEqual(set(detail),set(overview))
        def lines(geometry):return [geometry['coordinates']] if geometry['type']=='LineString' else geometry['coordinates']
        for id,d in detail.items():
            with self.subTest(id=id):
                o=overview[id]
                self.assertEqual(d['stationKeys'],o['stationKeys'])
                self.assertEqual(len(d['features']),len(o['features']))
                for df,of in zip(d['features'],o['features']):
                    self.assertEqual(df['properties'],of['properties'])
                    dl,ol=lines(df['geometry']),lines(of['geometry'])
                    self.assertEqual(len(dl),len(ol))
                    for a,b in zip(dl,ol):
                        self.assertEqual(a[0],b[0]);self.assertEqual(a[-1],b[-1])
        # The old shortest-path extraction dropped the real Sawara alternative.
        s=next(f for f in detail['tohoku-hokkaido']['features'] if f['properties']['name']=='函館線')
        points=[p for line in lines(s['geometry']) for p in line]
        sawara=next(s for s in json.loads((DATA/'stations.json').read_text()) if s[0]=='渡島砂原')
        self.assertLess(min(math.hypot(p[0]-sawara[2],p[1]-sawara[1]) for p in points),.002)

@unittest.skipUnless(importlib.util.find_spec('playwright') and importlib.util.find_spec('PIL'),'Playwright and Pillow required')
class RenderedCatalogue(unittest.TestCase):
    def test_every_pass_and_continuous_zoom(self):
        from playwright.sync_api import sync_playwright
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=os.environ.get('JPRAIL_BASE_URL',f'http://127.0.0.1:{server.server_port}').rstrip('/')
        live=bool(os.environ.get('JPRAIL_LIVE_BASEMAP'))
        records=[];errors=[]
        try:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(channel='chrome',headless=True)
                context=browser.new_context(viewport={'width':1600,'height':1040},reduced_motion='no-preference')
                if not live:context.route('**/*',lambda r:r.continue_() if urlsplit(r.request.url).hostname==urlsplit(base).hostname else r.abort())
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/JPRail.html?audit=20261110',wait_until='domcontentloaded')
                page.wait_for_function('window.JPRail?.state.stations.length>10000')
                if live:page.wait_for_function('JPRail.state.basemap.status==="ready"',timeout=60000)
                # View culling may omit off-screen chunks, but may never
                # invent a join or lose a source segment crossing the view.
                self.assertTrue(page.evaluate('''() => {
                  const line=Array.from({length:400},(_,i)=>[130+i/1000,35+Math.sin(i)/1000]),f={type:'Feature',properties:{},geometry:{type:'LineString',coordinates:line}},box=[130.126,34.99,130.129,35.01],w=JPRail.windowFeature(f,box);
                  const pairs=ls=>ls.flatMap(l=>l.slice(1).map((p,i)=>JSON.stringify([l[i],p]))),original=new Set(pairs([line])),actual=new Set(pairs(w.geometry.coordinates));
                  const required=line.slice(1).flatMap((p,i)=>Math.max(p[0],line[i][0])>=box[0]&&Math.min(p[0],line[i][0])<=box[2]?[JSON.stringify([line[i],p])]:[]);
                  const crossing=JPRail.windowFeature({type:'Feature',properties:{},geometry:{type:'LineString',coordinates:[[130,35],[140,35]]}},[134,34,136,36]);
                  return w.sourceFeature===f&&[...actual].every(s=>original.has(s))&&required.every(s=>actual.has(s))&&crossing.geometry.coordinates[0].length===2;
                }'''))
                # One input path, continuously accumulated target, no lost inputs,
                # no post-release snap. Event count is not a gesture lock.
                page.evaluate('''() => {window.cameraGaps=[];window.zoomEvents={start:0,end:0};JPRail.map.on('zoomstart',()=>zoomEvents.start++);JPRail.map.on('zoomend',()=>zoomEvents.end++);JPRail.map.on('zoom',e=>{if(!e.continuousWheel)return;requestAnimationFrame(()=>{const a=JPRail.map.getContainer().getBoundingClientRect();for(const c of JPRail.map.getPane('railRoutes').querySelectorAll('canvas')){const b=c.getBoundingClientRect(),gap=Math.max(b.left-a.left,b.top-a.top,a.right-b.right,a.bottom-b.bottom);if(gap>1&&cameraGaps.length<12)cameraGaps.push({zoom:JPRail.map.getZoom(),gap});}});});}''')
                def reset(z=8):
                    page.evaluate('(z)=>{JPRail.camera.setView([35.5,136],z);zoomEvents={start:0,end:0};}',z)
                    page.wait_for_function('JPRail.camera.whenIdle()')
                def wheel(events,mode=0):
                    page.evaluate('''([events,mode])=>new Promise(resolve=>{
                      const el=document.getElementById('map'),b=el.getBoundingClientRect();
                      for(const [deltaY,time] of events)setTimeout(()=>el.dispatchEvent(new WheelEvent('wheel',{deltaY,deltaMode:mode,clientX:b.x+b.width*.6,clientY:b.y+b.height*.6,bubbles:true,cancelable:true})),time);
                      setTimeout(resolve,events.at(-1)[1]+1);
                    })''',[events,mode])
                    page.wait_for_function('JPRail.camera.whenIdle()')
                for label,ev,expected in [('single',[[-100,0]],.125),('slow',[[-40,i*140] for i in range(5)],.25),('sustained',[[-40,i*20] for i in range(30)],1.5),('fast',[[-100,i*5] for i in range(10)],1.25),('reverse',[[-40,i*25] for i in range(10)]+[[40,250+i*25] for i in range(10)],0),('inertia',[[-v,i*16] for i,v in enumerate([60,40,25,15,10,6,3,2,1,.5,.2])],.203375)]:
                    reset();wheel(ev)
                    self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),8+expected,places=6,msg=label)
                    settled=page.evaluate('JPRail.map.getZoom()');page.wait_for_timeout(250)
                    self.assertEqual(page.evaluate('JPRail.map.getZoom()'),settled,label)
                    if label in ['single','sustained','fast','inertia']:self.assertEqual(page.evaluate('zoomEvents'),{'start':1,'end':1},label)
                reset();wheel([[-3,0]],1);self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),8.06,places=6)
                reset();wheel([[-1,0]],2);self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),8.2,places=6)
                reset(18);wheel([[-100,0]]);self.assertEqual(page.evaluate('JPRail.map.getZoom()'),18)
                reset(4);wheel([[100,0]]);self.assertEqual(page.evaluate('JPRail.map.getZoom()'),4)
                reset();page.get_by_role('button',name='放大',exact=True).dblclick();page.wait_for_function('JPRail.camera.whenIdle()');self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),8.5,places=6)
                page.locator('#map').focus();page.keyboard.press('+');page.wait_for_function('JPRail.camera.whenIdle()');self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),8.75,places=6)
                reset();box=page.locator('#map').bounding_box();page.mouse.move(box['x']+box['width']*.6,box['y']+box['height']*.6);page.mouse.wheel(0,-100);page.wait_for_function('JPRail.map.getZoom()>8');page.wait_for_function('JPRail.camera.whenIdle()');self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),8.125,places=6);self.assertEqual(page.evaluate('zoomEvents'),{'start':1,'end':1})
                self.assertEqual(page.evaluate('cameraGaps'),[],'the actual painted railway canvas must cover the viewport during a gesture')
                context2=browser.new_context(reduced_motion='reduce');context2.route('https://**',lambda r:r.abort());p2=context2.new_page();p2.goto(f'http://127.0.0.1:{server.server_port}/JPRail.html');p2.wait_for_function('window.JPRail?.state.stations.length>0');p2.evaluate('JPRail.camera.setView([36,136],8)');p2.get_by_role('button',name='放大',exact=True).click();p2.wait_for_function('JPRail.camera.whenIdle()');self.assertEqual(p2.evaluate('JPRail.map.getZoom()'),8.25);context2.close()
                page.locator('#showEnded').check()
                ids=page.evaluate('JPRail.state.passes.map(p=>p.id)')
                self.assertEqual(len(ids),54)
                for id in ids:
                    with self.subTest(pass_id=id):
                        page.locator('[data-pass="'+id+'"]').click();page.wait_for_function('JPRail.camera.whenIdle()')
                        page.wait_for_function('JPRail.state.stationLabels.pinnedNames.length>0')
                        self.assertEqual(page.evaluate('JPRail.state.selected'),id)
                        self.assertEqual(page.locator('.pass-card[aria-pressed="true"]').count(),1)
                        info=page.evaluate('''() => {const p=JPRail.state.passes.find(p=>p.id===JPRail.state.selected);return {pins:p.stationPins.stations.length,resolved:JPRail.state.pinnedStations.length,features:JPRail.state.displayed.length,issues:p.audit.issues,boundaries:JPRail.state.pinnedStations.filter(p=>p.role==='boundary').map(p=>p.name)};}''')
                        self.assertEqual(info['pins'],info['resolved'])
                        self.assertGreater(info['features'],0)
                        if info['issues']:self.assertIn('尚有未核实',page.locator('#passDetail').inner_text())
                        self.assertLessEqual(page.evaluate('document.documentElement.scrollHeight-innerHeight'),1)
                        self.assertTrue(page.evaluate('JPRail.map.getPane("railRoutes").style.zIndex>JPRail.map.getPane("railBase").style.zIndex'))
                        # Overview, regional, detailed view for EVERY product.
                        center=page.evaluate('JPRail.map.getCenter()');views=0
                        for z in [4,8,13]:
                            page.evaluate('([c,z])=>JPRail.camera.setView(c,z)',[center,z]);page.wait_for_function('JPRail.camera.whenIdle()');self.check_labels(page)
                            self.check_rendered_layers(page)
                            views+=1
                        # Actually raster-check every selected operator/line
                        # group at a point on its railway, not just at a city's
                        # centre or an empty bounding-box centre.
                        groups=page.evaluate("JPRail.state.displayed.map(f=>{const lines=f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates,line=lines.reduce((a,b)=>a.length>b.length?a:b);return line[Math.floor(line.length/2)];})")
                        paint_samples=0
                        for point in groups:
                            page.evaluate('(p)=>JPRail.camera.setView([p[1],p[0]],13)',point)
                            page.wait_for_function('JPRail.camera.whenIdle()');page.wait_for_function('JPRail.state.detailStatus===\"detail\"');self.check_labels(page);self.check_rendered_layers(page)
                            paint_samples+=self.check_paint(page);views+=1
                        # Every official boundary/end station is visited at close
                        # zoom; duplicates at one physical location are grouped.
                        pins=page.evaluate('JPRail.state.pinnedStations.map(p=>p.station)');seen=set()
                        for s in pins:
                            key=(round(s[1],2),round(s[2],2))
                            if key in seen:continue
                            seen.add(key);page.evaluate('(s)=>JPRail.camera.setView([s[1],s[2]],15)',s);page.wait_for_function('JPRail.camera.whenIdle()');self.check_labels(page);self.check_rendered_layers(page);views+=1
                        # Exercise each grade and each actual operator, including
                        # genuine empty intersections, without inventing edges.
                        operators=page.evaluate('[...new Set(JPRail.state.passCoverage.map(f=>f.properties.operator))]')
                        for op in operators:
                            page.locator('#railOperator').select_option(op)
                            self.assertTrue(page.evaluate('(op)=>JPRail.state.displayed.every(f=>f.properties.operator===op)',op))
                        page.locator('#railOperator').select_option('')
                        for grade in ['highspeed','main','branch']:
                            page.locator('#railGrade').select_option(grade);self.assertTrue(page.evaluate('(g)=>JPRail.state.displayed.every(f=>JPRail.gradeOf(f)===g)',grade))
                        page.locator('#railGrade').select_option('')
                        page.locator('#closeDetail').click();self.assertFalse(page.locator('#detailPanel').is_visible());page.locator('[data-focus="'+id+'"]').click();self.assertTrue(page.locator('#detailPanel').is_visible())
                        # An actual drag after rebuilding layers must not leave
                        # a cached view hole or reset the selected product.
                        box=page.locator('#map').bounding_box();x=box['x']+box['width']*.6;y=box['y']+box['height']*.6
                        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+65,y+30,steps=4);page.mouse.up();page.wait_for_timeout(120);self.check_rendered_layers(page)
                        self.assertEqual(page.evaluate('JPRail.state.selected'),id)
                        print('rendered',id,'views',views,'samples',paint_samples,flush=True)
                        records.append({'id':id,'views':views,'operators':len(operators),'pins':info['pins'],'paintSamples':paint_samples,'sourceAudit':'partial' if info['issues'] else 'verified'})
                self.assertEqual(errors,[])
                self.assertEqual(len(records),54)
                if live:self.check_hokuriku_land(page)
                if os.environ.get('JPRAIL_REVIEW_IMAGE'):
                    page.locator('[data-pass="hokuriku"]').click();page.wait_for_function('JPRail.camera.whenIdle()');page.wait_for_timeout(1000);page.screenshot(path=os.environ['JPRAIL_REVIEW_IMAGE'])
                browser.close()
        finally:server.shutdown();server.server_close()
        # Machine-readable current run output belongs in the task temp directory.
        if os.environ.get('JPRAIL_AUDIT_OUTPUT'):Path(os.environ['JPRAIL_AUDIT_OUTPUT']).write_text(json.dumps(records,ensure_ascii=False,indent=2))
        print('catalogue rendered:',len(records),'products;',sum(r['views'] for r in records),'views;',sum(r['pins'] for r in records),'pin visits')

    def check_hokuriku_land(self,page):
        # A projection-only assertion missed a stale GL framebuffer after the
        # detail panel changed width. Check the actual painted coastline too.
        from PIL import Image
        page.locator('[data-pass="hokuriku"]').click();page.wait_for_function('JPRail.camera.whenIdle()');page.wait_for_timeout(1200)
        page.evaluate("['railRoutes','railStations','railBoundaries'].forEach(p=>JPRail.map.getPane(p).style.visibility='hidden')")
        try:
            point=page.evaluate("() => {const s=JPRail.state.stations.find(s=>s[0]==='金沢'&&s[3]==='西日本旅客鉄道'),p=JPRail.map.latLngToContainerPoint([s[1],s[2]]);return [p.x,p.y];}")
            img=Image.open(io.BytesIO(page.locator('#map').screenshot())).convert('RGB');x,y=map(round,point)
            water=sum(max(abs(a-b) for a,b in zip(img.getpixel((x+dx,y+dy)),(194,200,202)))<4 for dx in range(-5,6) for dy in range(-5,6))
            self.assertLess(water/121,.2,'Kanazawa station must be on the painted land, not on a stale displaced coastline')
        finally:page.evaluate("['railRoutes','railStations','railBoundaries'].forEach(p=>JPRail.map.getPane(p).style.visibility='')")

    def check_paint(self,page):
        from PIL import Image
        sample=page.evaluate('''() => {
          const map=JPRail.map,size=map.getSize(),el=map.getContainer(),rect=el.getBoundingClientRect();
          const ui=[...el.closest('.map-frame').querySelectorAll('.leaflet-control,.map-layer-controls,.map-state,.basemap-status,.map-note,.rail-legend')].map(e=>{const b=e.getBoundingClientRect();return [b.left-rect.left-4,b.top-rect.top-4,b.right-rect.left+4,b.bottom-rect.top+4]});
          const blocked=new Set(),points=[],colors=new Set();
          for(const s of [...JPRail.state.stationPool,...JPRail.state.pinnedStations.map(p=>p.station)]){
            const p=map.latLngToContainerPoint([s[1],s[2]]);
            if(p.x< -10||p.y< -10||p.x>size.x+10||p.y>size.y+10)continue;
            for(let x=Math.floor((p.x-8)/16);x<=Math.floor((p.x+8)/16);x++)for(let y=Math.floor((p.y-8)/16);y<=Math.floor((p.y+8)/16);y++)blocked.add(x+','+y);
          }
          for(const f of JPRail.state.displayed){
            colors.add(JPRail.railStyle(f).color);
            const lines=f.geometry.type==='LineString'?[f.geometry.coordinates]:f.geometry.coordinates;
            for(const line of lines){
              // Sample real segments and their interior, not label dots alone.
              for(let i=1;i<line.length;i++){
                const a=map.latLngToContainerPoint([line[i-1][1],line[i-1][0]]),b=map.latLngToContainerPoint([line[i][1],line[i][0]]);
                if(Math.max(a.x,b.x)<15||Math.min(a.x,b.x)>size.x-15||Math.max(a.y,b.y)<15||Math.min(a.y,b.y)>size.y-15)continue;
                const p=a.add(b).divideBy(2),x=p.x,y=p.y;
                if(x<15||y<15||x>size.x-15||y>size.y-15||blocked.has(Math.floor(x/16)+','+Math.floor(y/16))||ui.some(b=>x>b[0]&&x<b[2]&&y>b[1]&&y<b[3]))continue;
                points.push([x,y]);
              }
            }
          }
          const step=Math.max(1,Math.ceil(points.length/1500));return {points:points.filter((_,i)=>i%step===0),colors:[...colors]};
        }''')
        if len(sample['points'])<3:return 0
        screenshot=Image.open(io.BytesIO(page.locator('#map').screenshot())).convert('RGB')
        colors=[tuple(bytes.fromhex(c[1:])) for c in sample['colors']];found=0;miss=[]
        for x,y in sample['points']:
            x,y=round(x),round(y)
            visible=any(max(abs(a-b) for a,b in zip(screenshot.getpixel((x+dx,y+dy)),color))<35 for color in colors for dx,dy in [(0,0),(-1,0),(1,0),(0,-1),(0,1),(-2,0),(2,0),(0,-2),(0,2)])
            if visible:found+=1
            else:miss.append([x,y])
        self.assertGreaterEqual(found/len(sample['points']),.96,{'pass':page.evaluate('JPRail.state.selected'),'zoom':page.evaluate('JPRail.map.getZoom()'),'samples':len(sample['points']),'missing':miss[:8]})
        return len(sample['points'])

    def check_labels(self,page):
        page.wait_for_function('''() => {const shown=new Set(JPRail.state.stationLabels.pinnedNames),b=JPRail.map.getBounds();return JPRail.state.pinnedStations.filter(p=>b.contains([p.station[1],p.station[2]])).every(p=>shown.has(p.name));}''')
        self.assertFalse(page.evaluate('JPRail.state.stationLabels.texts.some(t=>t.endsWith(" 界")||t.endsWith(" 限"))'))
        self.assertTrue(page.evaluate('''() => {const s=JPRail.state.stationLabels,hit=(a,b)=>a[0]<b[2]&&a[2]>b[0]&&a[1]<b[3]&&a[3]>b[1];return s.pinnedBoxes.filter(p=>p.role==='boundary').every(p=>!s.uiBoxes.some(b=>hit(p.box,b))&&!s.pinnedBoxes.some(q=>q!==p&&hit(p.box,q.box)));}'''),'true boundary names must remain readable, not merely counted under controls or other labels')

    def check_rendered_layers(self,page):
        page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
        page.wait_for_function('''() => {const m=JPRail.map,g=JPRail.streets.getMap();if(!g)return true;const a=g.getCanvas().getBoundingClientRect(),r=m.getContainer().getBoundingClientRect(),s=m.getSize();return [[.25,.25],[.75,.75]].every(([x,y])=>{const p=L.point(s.x*x,s.y*y),ll=m.containerPointToLatLng(p),q=g.project([ll.lng,ll.lat]);return Math.hypot(q.x+a.x-r.x-p.x,q.y+a.y-r.y-p.y)<2;});}''')
        self.assertTrue(page.evaluate('''() => {if(JPRail.state.detailStatus!=='detail')return true;const m=JPRail.map,c=m.getPane('railRoutes').querySelector('canvas');if(!c)return true;const a=c.getBoundingClientRect(),r=m.getContainer().getBoundingClientRect(),corners=[[a.left-r.left,a.top-r.top],[a.right-r.left,a.bottom-r.top]];return corners.every(p=>JPRail.state.paintBounds.pad(.002).contains(m.containerPointToLatLng(p)));}'''),'prepared geometry must cover the actual padded raster after pan, ready for the next continuous zoom')
        self.assertTrue(page.evaluate('''() => {const layers=[...JPRail.state.layers.values()].flatMap(l=>l.getLayers()),view=JPRail.map.getBounds();const actual=new Set(layers.map(l=>l.feature));return JPRail.state.displayed.every(f=>{window.auditBounds ||= new WeakMap();if(!auditBounds.has(f))auditBounds.set(f,L.geoJSON(f).getBounds());return !view.intersects(auditBounds.get(f))||actual.has(f);});}'''),'visible rail geometry must be retained after pan/LOD/filter')

if __name__=='__main__':unittest.main()
