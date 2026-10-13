// Optional end-to-end visual check: requires Playwright and Chromium.
// Serves files via intercepted requests, with an isolated synthetic warning.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({ headless: true,
        ...(process.env.TEST_BROWSER_CHANNEL ? { channel: process.env.TEST_BROWSER_CHANNEL } : {}) });
    try {
        const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
        await context.addInitScript(() => localStorage.setItem('shenzhen-thunder-mode-v1', 'off'));
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.clock.install({ time: new Date('2026-05-20T12:05:00+08:00') });
        const fixture = JSON.parse(fs.readFileSync('config.json', 'utf8'));
        fixture.THUNDER_MONITOR_CONFIG.default_mode = 'auto';
        fixture.ALERT_CONFIG = { enabled: true, title: '测试 · 深圳官方预警', message: '浏览器隔离测试，不是真实预警', image: '' };
        fixture.THUNDER_ALERT_CONFIG = {
            enabled: true, status: 'estimated_risk', event_id: 'test-browser',
            generated_at: '2026-05-20T12:05:00+08:00', valid_until: '2026-05-20T12:49:00+08:00',
            settings: fixture.THUNDER_MONITOR_CONFIG,
            candidates: [{ id: 'test', city: '珠海', district: '珠海市', type: '雷电',
                confidence: '较高', distance_km: 49.4, travel_minutes: 59,
                source_longitude: 113.5766, source_latitude: 22.271,
                published_at: '2026-05-20T11:20:00+08:00',
                estimated_arrival: '2026-05-20T12:19:00+08:00', expires_at: '2026-05-20T12:49:00+08:00',
                message: '隔离测试正文，不是真实预警。', source_url: 'https://www.gd121.cn/yj/content.shtml?code=test' }], radar: {}
        };
        const root = process.cwd();
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== 'http://127.0.0.1:14331') return route.abort();
            if (url.pathname === '/config.json') return route.fulfill({ json: fixture });
            const file = path.resolve(root, '.' + (url.pathname === '/' ? '/index.html' : url.pathname));
            if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
            await route.fulfill({ path: file });
        });
        await page.goto('http://127.0.0.1:14331/');
        await page.locator('#thunder-overlay').waitFor({ state: 'visible' });
        assert.equal(await page.locator('#thunder-mode, .thunder-control').count(), 0, 'no visitor switch');
        assert.match(await page.locator('#thunder-countdown').innerText(), /14 分/);
        await page.locator('.thunder-details summary').click();
        assert.match(await page.locator('#thunder-evidence').innerText(), /49.4 km ÷ 50 km\/h/);
        await page.screenshot({ path: '/private/tmp/thunder-desktop.png', animations: 'disabled' });
        await page.setViewportSize({ width: 390, height: 844 });
        await page.reload();
        await page.locator('#thunder-overlay').waitFor({ state: 'visible' });
        await page.locator('.thunder-details summary').click();
        await page.clock.runFor(1000);
        await page.screenshot({ path: '/private/tmp/thunder-mobile.png', animations: 'disabled' });
        const fits = await page.locator('.thunder-modal').evaluate(el => {
            const rect = el.getBoundingClientRect();
            return rect.left >= 0 && rect.right <= innerWidth && rect.bottom <= innerHeight
                && el.scrollWidth <= el.clientWidth;
        });
        assert.equal(fits, true, 'thunder modal must fit the mobile viewport');
        await page.locator('#thunder-close').click();
        assert.equal(await page.locator('#alert-overlay').isVisible(), true);
        await page.getByRole('button', { name: '我知道了 (点击关闭)' }).click();
        fixture.THUNDER_MONITOR_CONFIG.default_mode = 'off';
        fixture.THUNDER_ALERT_CONFIG.enabled = false;
        await page.evaluate(() => refreshPageConfig());
        assert.equal(await page.locator('#thunder-overlay').isVisible(), false);
        assert.equal(await page.locator('#alert-overlay').isVisible(), true);
        await page.getByRole('button', { name: '我知道了 (点击关闭)' }).click();
        fixture.THUNDER_MONITOR_CONFIG.default_mode = 'on';
        fixture.THUNDER_ALERT_CONFIG.enabled = true;
        await page.evaluate(() => refreshPageConfig());
        assert.equal(await page.locator('#thunder-overlay').isVisible(), true);
        await page.clock.runFor(14 * 60000);
        assert.equal(await page.locator('#thunder-overlay').isVisible(), true);
        assert.match(await page.locator('#thunder-countdown').innerText(), /0 分 0 秒.*30 分钟保留期/);
        await page.clock.runFor(30 * 60000);
        assert.equal(await page.locator('#thunder-overlay').isVisible(), false);
        assert.equal(await page.locator('#alert-overlay').isVisible(), true);
        assert.deepEqual(errors, []);
        console.log('PASS: desktop/mobile layout, no visitor controls, old local preference ignored, backend modes, popup queue, countdown + grace; no page JS errors.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
