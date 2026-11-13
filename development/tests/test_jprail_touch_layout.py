"""Trackpad input paths and non-overlapping responsive JPRail layouts."""
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
from functools import partial
import importlib.util
import json
import math
import os
import unittest
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[2]

# Track painted circle centres and their real DOM canvas transforms. This
# catches independently transformed outer/inner rings during an animation.
RING_INK_PROBE=r'''(() => {
 for(const key of ['width','height']) {
  const d=Object.getOwnPropertyDescriptor(HTMLCanvasElement.prototype,key);
  Object.defineProperty(HTMLCanvasElement.prototype,key,{...d,set(v){this.circleInk=[];d.set.call(this,v);}});
 }
 const p=CanvasRenderingContext2D.prototype,arc=p.arc,begin=p.beginPath,stroke=p.stroke,clear=p.clearRect;
 p.clearRect=function(...a){this.canvas.circleInk=[];return clear.apply(this,a);};
 p.beginPath=function(...a){this.circlePath=[];return begin.apply(this,a);};
 p.arc=function(x,y,r,...a){const t=this.getTransform();(this.circlePath||=[]).push({x:t.a*x+t.c*y+t.e,y:t.b*x+t.d*y+t.f,r});return arc.call(this,x,y,r,...a);};
 p.stroke=function(...a){if(this.globalAlpha>0)(this.canvas.circleInk||=[]).push(...(this.circlePath||[]));return stroke.apply(this,a);};
})();'''

RING_FRAMES=r'''({station,radius,delta})=>new Promise(resolve=>{
 const frames=[],deadline=performance.now()+2500;
 const sample=()=>{
  const m=JPRail.map,b=m.getContainer().getBoundingClientRect(),p=m.latLngToContainerPoint([station[1],station[2]]),ref={x:b.x+p.x,y:b.y+p.y};
  const dots=[...m.getContainer().querySelectorAll('canvas')].flatMap(c=>{
   const box=c.getBoundingClientRect();
   return (c.circleInk||[]).map(d=>({x:box.x+d.x*box.width/c.width,y:box.y+d.y*box.height/c.height,r:d.r,c}));
  });
  const near=(r,point)=>dots.filter(d=>Math.abs(d.r-r)<.01||Math.abs(d.r-Math.round(r))<.01).sort((a,b)=>Math.hypot(a.x-point.x,a.y-point.y)-Math.hypot(b.x-point.x,b.y-point.y))[0];
  const outer=near(radius,ref),inner=outer&&near(3.4,outer);
  if(outer&&inner)frames.push({drift:Math.hypot(outer.x-inner.x,outer.y-inner.y),positionError:Math.hypot(outer.x-ref.x,outer.y-ref.y),sameCanvas:outer.c===inner.c});
  if(performance.now()<deadline&&(!JPRail.camera.whenIdle()||frames.length<3))requestAnimationFrame(sample);
  else resolve(frames);
 };
 const b=JPRail.map.getContainer().getBoundingClientRect();
 document.getElementById('map').dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:delta,clientX:b.x+b.width*.55,clientY:b.y+b.height*.45,bubbles:true,cancelable:true}));
 requestAnimationFrame(sample);
})'''

@unittest.skipUnless(importlib.util.find_spec('playwright'),'Playwright required')
class TouchAndLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self,*a):pass
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(ROOT)))
        Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.pw=sync_playwright().start();cls.browser=cls.pw.chromium.launch(channel='chrome',headless=True)
        cls.base=os.environ.get('JPRAIL_BASE_URL',f'http://127.0.0.1:{cls.server.server_port}').rstrip('/')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop();cls.server.shutdown();cls.server.server_close()

    def page(self,**options):
        context=self.browser.new_context(**options)
        if not os.environ.get('JPRAIL_LIVE_BASEMAP'):
            context.route('**/*',lambda r:r.continue_() if urlsplit(r.request.url).hostname==urlsplit(self.base).hostname else r.abort())
        return context,context.new_page()

    def load(self,page,query=''):
        page.goto(self.base+'/JPRail.html'+query,wait_until='domcontentloaded')
        page.wait_for_function('window.JPRail?.state.stations.length>0')
        page.wait_for_function('JPRail.camera.whenIdle()')

    def settle(self,page):
        page.wait_for_function('JPRail.camera.whenIdle()')
        page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')

    def test_seikan_shared_track_company_interfaces_and_seishun18(self):
        context,page=self.page(viewport={'width':1440,'height':960})
        try:
            self.load(page)
            self.assertEqual(page.locator('.pass-card').evaluate_all('(xs)=>xs.slice(0,2).map(x=>x.dataset.pass)'),['japan','seishun18'])
            self.assertEqual(page.evaluate('JPRail.state.companyStations.length'),14)
            self.assertEqual(page.evaluate('JPRail.state.pinnedStations.length'),0)
            page.locator('#infrastructure').check()
            for z in [8,10.5,13]:
                page.evaluate('(z)=>JPRail.camera.setView([41.3,140.4],z)',z);self.settle(page)
                if z>=10:page.wait_for_function('JPRail.state.detailStatus==="detail"')
                self.assertTrue(page.evaluate('JPRail.map.hasLayer(JPRail.state.seikanOverlay)'))
                rows=page.evaluate('JPRail.state.seikanOverlay.getLayers().map(l=>[l.feature.properties.name,l.options.color,l.options.weight])')
                self.assertTrue(rows)
                self.assertTrue(all(n=='海峡線' and c.lower()=='#ff0c00' and w==4 for n,c,w in rows),rows)
                self.assertEqual(page.evaluate("JPRail.gradeOf({properties:{operator:'北海道旅客鉄道',name:'海峡線',kind:'2',grade:'main'}})"),'highspeed')
            page.locator('#resetView').click();self.settle(page)
            page.locator('[data-pass="japan"]').click();self.settle(page)
            self.assertEqual(page.evaluate('JPRail.state.companyStations.length'),14)
            self.assertFalse(page.evaluate("JPRail.state.pinnedStations.some(p=>p.name==='熱海'&&p.role==='boundary')"))
            page.locator('[data-junction="熱海"]').click();self.settle(page)
            self.assertTrue(page.evaluate("JPRail.state.stationLabels.pinSymbols.some(p=>p.name==='熱海'&&p.junction)"))
            self.assertNotIn('熱海',page.evaluate('JPRail.state.stationLabels.boundaryNames'))
            page.locator('[data-pass="kintetsu1"]').click();self.settle(page)
            self.assertEqual(page.evaluate('JPRail.state.companyStations.length'),0)
            page.locator('[data-pass="seishun18"]').click();self.settle(page)
            self.assertFalse(page.evaluate("JPRail.state.displayed.some(f=>f.properties.kind==='1'||f.properties.name==='海峡線'||f.properties.operator==='道南いさりび鉄道')"))
            self.assertIn('熱海',page.evaluate('JPRail.state.companyStations.map(p=>p.name)'))
            self.assertNotIn('東京',page.evaluate('JPRail.state.companyStations.map(p=>p.name)'),'Tokyo interface in this atlas is Shinkansen only')
            self.assertIn('¥10,000',page.locator('.price-section').inner_text())
            self.assertIn('¥12,050',page.locator('.price-section').inner_text())
            page.locator('#startDate').fill('2026-11-13');page.locator('#startDate').dispatch_event('change')
            self.assertIn('不在已公布季节',page.locator('#dateResult').inner_text())
            page.locator('#startDate').fill('2026-12-11');page.locator('#startDate').dispatch_event('change')
            self.assertNotIn('不在已公布季节',page.locator('#dateResult').inner_text())
        finally:context.close()

    def test_all_lines_clears_map_filters_and_restores_initial_view(self):
        for width,height in [(1440,900),(390,844)]:
            with self.subTest(viewport=(width,height)):
                context,page=self.page(viewport={'width':width,'height':height})
                try:
                    self.load(page)
                    initial=page.evaluate('''()=>({zoom:JPRail.map.getZoom(),center:JPRail.map.getCenter(),size:JPRail.map.getSize(),routes:JPRail.state.displayed.map(f=>f.properties.operator+'|'+f.properties.name).sort()})''')
                    self.assertEqual(page.locator('#resetView').inner_text(),'全部线路')
                    page.locator('[data-pass="japan"]').click();self.settle(page)
                    page.locator('#railGrade').select_option('branch')
                    page.locator('#railOperator').select_option('京王電鉄');self.settle(page)
                    page.locator('#stationSearch').fill('京都')
                    page.locator('[data-station]').first.click();self.settle(page)
                    page.evaluate('JPRail.camera.zoomBy(.25)')
                    page.locator('#resetView').click();self.settle(page)
                    self.assertIsNone(page.evaluate('JPRail.state.selected'))
                    self.assertIsNone(page.evaluate('JPRail.state.active'))
                    self.assertFalse(page.locator('#detailPanel').is_visible())
                    self.assertEqual(page.locator('#railGrade').input_value(),'')
                    self.assertEqual(page.locator('#railOperator').input_value(),'')
                    self.assertEqual(page.locator('#stationSearch').input_value(),'')
                    self.assertEqual(page.locator('.leaflet-popup').count(),0)
                    self.assertFalse(page.locator('#infrastructure').is_disabled())
                    self.assertFalse(page.locator('#infrastructure').is_checked())
                    self.assertEqual(page.evaluate('JPRail.state.pinnedStations.length'),0)
                    self.assertEqual(page.evaluate('JPRail.state.boundaryMarkers.getLayers().length'),page.evaluate('JPRail.state.companyStations.length'))
                    self.assertTrue(page.evaluate('''()=>['pass','passes','grade','operator'].every(k=>!new URL(location.href).searchParams.has(k))'''))
                    self.assertEqual(page.evaluate("JPRail.state.displayed.map(f=>f.properties.operator+'|'+f.properties.name).sort()"),initial['routes'])
                    self.assertEqual(page.evaluate('JPRail.map.getSize()'),initial['size'])
                    self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),initial['zoom'],places=6)
                    for key in ['lat','lng']:
                        self.assertAlmostEqual(page.evaluate('JPRail.map.getCenter()')[key],initial['center'][key],places=6)
                    # Reset also switches an explicitly enabled facility map
                    # back to the initial ordinary route layer, without a late zoom.
                    page.locator('#infrastructure').check()
                    page.locator('#resetView').click();self.settle(page)
                    self.assertFalse(page.locator('#infrastructure').is_checked())
                    page.wait_for_timeout(250)
                    self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),initial['zoom'],places=6)
                finally:context.close()

    def test_endpoint_rings_stay_concentric_during_zoom_and_pan(self):
        context,page=self.page(viewport={'width':1440,'height':960})
        try:
            page.add_init_script(RING_INK_PROBE)
            self.load(page,'?pass=hokuriku')
            total=0;largest=0
            for name in ['黒部宇奈月温泉','猪谷','三国港']:
                pin=page.evaluate('(n)=>JPRail.state.pinnedStations.find(p=>p.name===n)',name)
                radius=6.5 if pin['role']=='boundary' else 4.5
                page.evaluate('(s)=>JPRail.camera.setView([s[1],s[2]],11)',pin['station']);self.settle(page)
                for delta in [-140,100,-80]:
                    frames=page.evaluate(RING_FRAMES,{'station':pin['station'],'radius':radius,'delta':delta})
                    self.assertGreaterEqual(len(frames),3,(name,delta))
                    self.assertTrue(all(f['sameCanvas'] for f in frames),(name,delta,'rings must share their real paint transform'))
                    drift=max(f['drift'] for f in frames);largest=max(largest,drift);total+=len(frames)
                    self.assertLess(drift,.5,(name,delta))
                    self.assertLess(max(f['positionError'] for f in frames),2.5,(name,delta))
                # The standard button and a real drag preserve the same pairing.
                page.get_by_role('button',name='放大',exact=True).click();self.settle(page)
                b=page.locator('#map').bounding_box();x=b['x']+b['width']/2;y=b['y']+b['height']/2
                page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+25,y+20,steps=5);page.mouse.up();self.settle(page)
                frames=page.evaluate(RING_FRAMES,{'station':pin['station'],'radius':radius,'delta':0})
                self.assertTrue(frames);self.assertLess(max(f['drift'] for f in frames),.5)
            self.assertTrue(page.evaluate('JPRail.state.boundaryMarkers.getLayers().every(l=>l.options.stroke===false&&l.options.fillOpacity===0)'))
            print('endpoint ring frames:',total,'max offset:',round(largest,6),flush=True)
        finally:context.close()

    def test_chromium_pinch_has_larger_gain_without_replaying_input(self):
        context,page=self.page(viewport={'width':1440,'height':900})
        try:
            self.load(page)
            page.evaluate("() => {window.events={start:0,end:0};JPRail.map.on('zoomstart',()=>events.start++);JPRail.map.on('zoomend',()=>events.end++);}")
            def gesture(ctrl,values):
                page.evaluate('''([ctrl,values])=>new Promise(resolve=>{
                  JPRail.camera.setView([36,136],8);events={start:0,end:0};const el=document.getElementById('map'),b=el.getBoundingClientRect();
                  window.cancelled=[];values.forEach((deltaY,i)=>setTimeout(()=>{const e=new WheelEvent('wheel',{ctrlKey:ctrl,deltaY,clientX:b.x+b.width*.6,clientY:b.y+b.height*.6,bubbles:true,cancelable:true});el.dispatchEvent(e);cancelled.push(e.defaultPrevented);},i*20));setTimeout(resolve,values.length*20);
                })''',[ctrl,values]);self.settle(page)
                self.assertTrue(page.evaluate('cancelled.every(Boolean)'))
                zoom=page.evaluate('JPRail.map.getZoom()');page.wait_for_timeout(250);self.assertEqual(page.evaluate('JPRail.map.getZoom()'),zoom)
                self.assertEqual(page.evaluate('events'),{'start':1,'end':1})
                return zoom-8
            ordinary=gesture(False,[-10]*8);pinch=gesture(True,[-10]*8)
            self.assertAlmostEqual(ordinary,.1,places=6);self.assertAlmostEqual(pinch,.8,places=6)
            self.assertAlmostEqual(pinch/ordinary,8,places=6)
            self.assertAlmostEqual(gesture(True,[-20,-10,-5,5,10,20]),0,places=6)
            self.assertAlmostEqual(gesture(True,[-12,-8,-4,-2,-1]),.27,places=6)
            page.evaluate('JPRail.camera.setView([36,136],17.95)')
            box=page.locator('#map').bounding_box();page.mouse.move(box['x']+box['width']*.5,box['y']+box['height']*.5)
            page.evaluate("document.getElementById('map').dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:-100,bubbles:true,cancelable:true}))")
            self.settle(page);self.assertEqual(page.evaluate('JPRail.map.getZoom()'),18)
            page.evaluate("() => {JPRail.camera.setView([36,136],8);events={start:0,end:0};window.nativeInputs=[];document.getElementById('map').addEventListener('wheel',e=>nativeInputs.push({ctrl:e.ctrlKey,dy:e.deltaY,prevented:e.defaultPrevented}));}")
            box=page.locator('#map').bounding_box()
            context.new_cdp_session(page).send('Input.synthesizePinchGesture',{'x':box['x']+box['width']*.6,'y':box['y']+box['height']*.6,'scaleFactor':1.5,'relativeSpeed':400,'gestureSourceType':'mouse'})
            self.settle(page);inputs=page.evaluate('nativeInputs')
            self.assertGreater(len(inputs),0)
            self.assertTrue(all(e['ctrl'] and e['prevented'] for e in inputs))
            self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()-8'),-sum(e['dy'] for e in inputs)/100,places=5)
            self.assertEqual(page.evaluate('events'),{'start':1,'end':1})
            self.assertEqual(page.evaluate('visualViewport.scale'),1)
        finally:context.close()

    def test_native_desktop_gesture_uses_scale_once(self):
        context,page=self.page(viewport={'width':1440,'height':900})
        try:
            # Emulate Safari's desktop event capability, not its UA string.
            page.add_init_script("window.ongesturestart=null;Object.defineProperty(navigator,'maxTouchPoints',{get:()=>0});")
            self.load(page)
            page.evaluate('''() => new Promise(resolve=>{
              JPRail.camera.setView([36,136],8);const el=document.getElementById('map'),b=el.getBoundingClientRect();
              const send=(type,scale)=>{const e=new Event(type,{bubbles:true,cancelable:true});Object.assign(e,{scale,clientX:b.x+b.width*.6,clientY:b.y+b.height*.6});el.dispatchEvent(e);};
              send('gesturestart',1);[1.1,1.3,1.2,1.5].forEach((scale,i)=>setTimeout(()=>{send('gesturechange',scale);el.dispatchEvent(new WheelEvent('wheel',{ctrlKey:true,deltaY:-20,bubbles:true,cancelable:true}));},i*25));setTimeout(()=>{send('gestureend',1.5);resolve()},110);
            })''');self.settle(page)
            self.assertAlmostEqual(page.evaluate('JPRail.map.getZoom()'),8+math.log2(1.5),places=6)
            z=page.evaluate('JPRail.map.getZoom()');page.wait_for_timeout(300);self.assertEqual(page.evaluate('JPRail.map.getZoom()'),z)
        finally:context.close()

    def test_desktop_map_gets_height_and_details_never_float_over_it(self):
        context,page=self.page(viewport={'width':1440,'height':900})
        try:
            self.load(page)
            for width,height in [(1440,900),(1680,1050),(1100,844),(961,700)]:
                with self.subTest(size=(width,height)):
                    page.set_viewport_size({'width':width,'height':height});page.locator('[data-pass="hokuriku"]').click();self.settle(page)
                    m=page.locator('.map-frame').bounding_box();d=page.locator('#detailPanel').bounding_box()
                    self.assertLessEqual(page.locator('.masthead').bounding_box()['height'],72)
                    self.assertLessEqual(page.locator('.station-density').bounding_box()['height'],15)
                    self.assertLessEqual(page.locator('.precision-note').bounding_box()['height'],20)
                    self.assertGreaterEqual(m['height'],height-260)
                    self.assertLessEqual(m['x']+m['width'],d['x']+1)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollHeight-innerHeight'),1)
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth-innerWidth'),1)
                    page.locator('#closeDetail').click();self.settle(page)
                    self.assertFalse(page.locator('#detailPanel').is_visible())
        finally:context.close()

    def test_mobile_details_are_below_map_and_selection_returns_to_map(self):
        context,page=self.page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,device_scale_factor=1)
        try:
            self.load(page)
            for width,height in [(320,640),(390,844),(768,1024),(844,390),(960,700)]:
                with self.subTest(size=(width,height)):
                    page.set_viewport_size({'width':width,'height':height});self.settle(page)
                    before=page.locator('.map-frame').bounding_box()['height']
                    page.locator('[data-pass="hokuriku"]').click();self.settle(page)
                    m=page.locator('.map-frame').bounding_box();d=page.locator('#detailPanel').bounding_box();cat=page.locator('.catalog').bounding_box()
                    self.assertAlmostEqual(m['height'],before,delta=1)
                    self.assertLessEqual(abs(m['y']),2)
                    self.assertGreaterEqual(d['y'],m['y']+m['height'])
                    self.assertLessEqual(d['y']+d['height'],cat['y']+1)
                    self.assertLessEqual(d['height'],height*.5+1)
                    self.assertEqual(page.locator('#detailPanel').evaluate('(e)=>getComputedStyle(e).position'),'static')
                    self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth-innerWidth'),1)
                    # The centre of the map remains a map hit target, not the
                    # description sheet, on portrait and landscape phones.
                    self.assertTrue(page.evaluate('''() => {const b=document.getElementById('map').getBoundingClientRect(),e=document.elementFromPoint(b.x+b.width*.5,b.y+Math.min(b.height*.5,innerHeight*.5));return !e.closest('#detailPanel')&&Boolean(e.closest('#map'));}'''))
                    page.locator('#closeDetail').click();self.settle(page);self.assertFalse(page.locator('#detailPanel').is_visible())
                    page.locator('[data-focus="hokuriku"]').click();self.settle(page)
                    self.assertTrue(page.locator('#detailPanel').is_visible());page.locator('#clearSelection').click();self.settle(page)
            if os.environ.get('JPRAIL_REVIEW_IMAGE'):
                page.set_viewport_size({'width':390,'height':844});page.locator('[data-pass="hokuriku"]').click();self.settle(page);page.wait_for_timeout(600);page.screenshot(path=os.environ['JPRAIL_REVIEW_IMAGE'])
        finally:context.close()

if __name__=='__main__':unittest.main()
