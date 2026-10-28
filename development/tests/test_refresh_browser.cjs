// Isolated snapshots and deterministic clocks; never calls weather/flight providers.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const root = path.resolve(__dirname, '../..');
const origin = 'http://127.0.0.1:14332';

(async () => {
    const browser = await chromium.launch({ headless: true, channel: process.env.TEST_BROWSER_CHANNEL || 'chrome' });
    try {
        const context = await browser.newContext();
        await context.route('**/*', route => {
            const url = new URL(route.request().url());
            if (url.origin !== origin) return route.abort();
            const file = path.resolve(root, '.' + url.pathname);
            if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
            return route.fulfill({ path: file });
        });
        const page = await context.newPage(), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const weather = JSON.parse(fs.readFileSync('config.json', 'utf8'));
        weather.THUNDER_ALERT_CONFIG = { enabled: false };
        weather.ALERT_CONFIG = { enabled: true, title: '测试预警', message: '隔离测试', image: '' };
        let mode = 'success';
        await page.route('**/config.json', route => mode === 'failure'
            ? route.fulfill({ status: 503, body: '' })
            : route.fulfill({ json: mode === 'malformed' ? {} : weather }));
        await page.goto(origin + '/index.html');
        await page.waitForFunction(() => hasLoadedConfig);
        await page.locator('#update-close').click();
        const temperature = await page.locator('#t').innerText();
        for (const failure of ['failure', 'malformed']) {
            mode = failure;
            await page.evaluate(() => refreshPageConfig());
            assert.equal(await page.locator('#t').innerText(), temperature);
            assert.equal(await page.locator('#alert-overlay').isVisible(), true, 'failed refresh preserves displayed warning');
            assert.match(await page.locator('#weather-status').innerText(), /上次成功/);
        }
        await page.evaluate(() => closeAlert());
        await page.screenshot({ path: '/private/tmp/weather-refresh-desktop.png' });
        mode = 'success';
        weather.LIVE_DATA.t = '27.5°C';
        await page.evaluate(() => window.dispatchEvent(new Event('online')));
        await page.waitForFunction(() => document.getElementById('t').innerText === '27.5°C');
        assert.equal(await page.locator('#weather-status').isVisible(), false);
        mode = 'failure';
        await page.reload();
        await page.waitForFunction(() => !document.getElementById('weather-status').hidden);
        assert.equal(await page.locator('#t').innerText(), '--');
        assert.match(await page.locator('#weather-status').innerText(), /暂时无法读取/);

        for (const filename of ['forecast.html', 'warnings.html']) {
            mode = 'success';
            await page.setViewportSize({ width: 390, height: 844 });
            await page.goto(origin + '/' + filename);
            const trigger = page.locator('.dropdown > .nav-item');
            await trigger.click();
            assert.equal(await trigger.getAttribute('aria-expanded'), 'true');
            assert.ok(await page.locator('.dropdown-menu').evaluate(menu => {
                const rect = menu.getBoundingClientRect();
                return rect.left >= 0 && rect.right <= innerWidth;
            }), 'weather-page dropdown stays within the mobile viewport');
            if (filename === 'forecast.html') await page.screenshot({ path: '/private/tmp/weather-forecast-mobile.png' });
            await page.keyboard.press('ArrowDown');
            assert.equal(await page.locator('.dropdown-menu a').first().evaluate(a => a === document.activeElement), true);
            await page.keyboard.press('Escape');
            assert.equal(await trigger.getAttribute('aria-expanded'), 'false');
        }
        mode = 'malformed';
        await page.reload();
        await page.getByText('预警数据暂时不可用，请稍后刷新。', { exact: true }).waitFor();
        assert.equal(await page.locator('.no-warning-card').count(), 0, 'missing warnings must never mean no warnings');
        mode = 'success';
        weather.WARNINGS = [];
        await page.reload();
        await page.locator('.no-warning-card').waitFor();

        const flightPage = await context.newPage();
        flightPage.on('pageerror', error => errors.push(error.message));
        const snapshot = JSON.parse(fs.readFileSync('flightdata/docs/data/szx.json', 'utf8'));
        await flightPage.clock.install({ time: new Date(snapshot.generated_at * 1000) });
        let ready = false, dataRequests = 0, statusRequests = 0;
        await flightPage.route('**/flightdata/docs/data/status.json?*', route => {
            statusRequests++;
            return route.fulfill({ json: { airports: { SZX: { last_success_at: ready ? snapshot.generated_at : null } } } });
        });
        await flightPage.route('**/flightdata/docs/data/szx.json?*', route => {
            dataRequests++;
            return ready ? route.fulfill({ json: snapshot }) : route.fulfill({ status: 404, body: '' });
        });
        await flightPage.goto(origin + '/Flightdat.html');
        await flightPage.getByText('航班资料正在准备', { exact: true }).waitFor();
        assert.equal(dataRequests, 1, 'boot requests one snapshot');
        ready = true;
        await flightPage.clock.fastForward(60001);
        await flightPage.locator('#list .row').first().waitFor();
        assert.equal(dataRequests, 2, 'first available snapshot is discovered once');
        snapshot.generated_at += 60;
        await flightPage.clock.fastForward(60001);
        await flightPage.waitForFunction(() => document.getElementById('toastText').textContent.includes('数据已更新'));
        assert.equal(dataRequests, 3, 'new snapshot poll does not load twice');
        snapshot.generated_at += 60;
        await flightPage.locator('#btnReload').click();
        await flightPage.waitForFunction(() => document.getElementById('toastText').textContent.includes('不会启动抓取'));
        assert.equal(dataRequests, 4, 'manual refresh does not load twice');
        await flightPage.evaluate(() => Object.defineProperty(document, 'hidden', { configurable: true, value: true }));
        const before = statusRequests;
        await flightPage.clock.fastForward(60001);
        assert.equal(statusRequests, before, 'hidden tabs skip status polling');
        const resumed = flightPage.waitForResponse('**/flightdata/docs/data/status.json?*');
        await flightPage.evaluate(() => {
            Object.defineProperty(document, 'hidden', { configurable: true, value: false });
            document.dispatchEvent(new Event('visibilitychange'));
        });
        await resumed;
        assert.equal(statusRequests, before + 1, 'returning tabs check immediately');
        assert.deepEqual(errors, []);
        console.log('PASS: retained weather/warnings, offline recovery, cross-page mobile keyboard navigation, warning schema, one flight request per update, first capture and hidden-tab polling.');
    } finally {
        await browser.close();
    }
})().catch(error => { console.error(error); process.exitCode = 1; });
