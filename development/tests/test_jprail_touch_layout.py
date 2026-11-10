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
