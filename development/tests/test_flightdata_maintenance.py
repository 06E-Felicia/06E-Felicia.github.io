"""Render the actual maintenance page without any upstream requests."""
import importlib.util
from pathlib import Path
import unittest
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Playwright required')
class MaintenanceTests(unittest.TestCase):
    def test_maintenance_is_static_responsive_and_makes_no_data_requests(self):
        from playwright.sync_api import sync_playwright
        html=(ROOT/'Flightdat.html').read_text()
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True)
            try:
                for javascript in [True,False]:
                    with self.subTest(javascript=javascript):
                        context=browser.new_context(java_script_enabled=javascript)
                        requests=[];errors=[]
                        def serve(route):
                            url=urlsplit(route.request.url);requests.append(url.path)
                            if url.hostname!='flightdat.local':route.abort();return
                            if url.path=='/Flightdat.html':
                                route.fulfill(content_type='text/html',body=html)
                            elif url.path=='/assets/styles/flightdata.css':
                                route.fulfill(content_type='text/css',body=(ROOT/url.path.lstrip('/')).read_text())
                            elif url.path=='/index.html':
                                route.fulfill(content_type='text/html',body='<h1>首页</h1>')
                            else:route.abort()
                        context.route('**/*',serve)
                        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                        page.goto('http://flightdat.local/Flightdat.html')
                        for width in [320,390,768,1440]:
                            page.set_viewport_size({'width':width,'height':900})
                            title=page.locator('#maintenance-title')
                            self.assertTrue(title.is_visible())
                            self.assertEqual(title.inner_text(),'维护中')
                            self.assertFalse(page.locator('.board').is_visible())
                            self.assertFalse(page.locator('.stats').is_visible())
                            self.assertFalse(page.locator('#btnReload').is_visible())
                            if javascript:
                                self.assertGreaterEqual(title.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)'),64)
                                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                        self.assertIn('维护中',page.title())
                        self.assertFalse(any('/data/' in p or p.endswith('.json') for p in requests))
                        self.assertEqual(errors,[])
                        page.locator('.site-nav a[href="index.html"]').click()
                        page.wait_for_url('**/index.html')
                        context.close()
            finally:browser.close()


if __name__=='__main__':unittest.main()
