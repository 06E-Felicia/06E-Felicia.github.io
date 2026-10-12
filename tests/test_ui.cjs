// Optional isolated browser regression for navigation and character dialogue.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch({ headless: true,
        ...(process.env.TEST_BROWSER_CHANNEL ? { channel: process.env.TEST_BROWSER_CHANNEL } : {}) });
    try {
        const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
        const page = await context.newPage(), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        const root = process.cwd(), fixture = JSON.parse(fs.readFileSync('config.json', 'utf8'));
        fixture.ALERT_CONFIG.enabled = false;
        fixture.THUNDER_ALERT_CONFIG = { enabled: false, candidates: [], radar: {} };
        await page.route('**/*', async route => {
            const url = new URL(route.request().url());
            if (url.origin !== 'http://127.0.0.1:14331') return route.abort();
            if (url.pathname === '/config.json') return route.fulfill({ json: fixture });
            const file = path.resolve(root, '.' + (url.pathname === '/' ? '/index.html' : url.pathname));
            if (!file.startsWith(root + path.sep) || !fs.existsSync(file)) return route.fulfill({ status: 404, body: '' });
            return route.fulfill({ path: file });
        });
        await page.goto('http://127.0.0.1:14331/');
        const dropdown = page.locator('.nav-bar .dropdown').first();
        const trigger = dropdown.locator('.nav-item'), link = dropdown.locator('.dropdown-menu a').first();
        await trigger.hover();
        await trigger.click();
        const triggerRect = await trigger.boundingBox();
        await page.mouse.move(triggerRect.x + triggerRect.width / 2, triggerRect.y + triggerRect.height + 5, { steps: 10 });
        await page.waitForTimeout(300); // Allow CSS transition across the old dead gap.
        assert.equal(await link.isVisible(), true, 'crossing the gap must not close the dropdown');
        await link.hover();
        assert.equal(await trigger.getAttribute('aria-expanded'), 'true');
        await page.mouse.move(900, 300);
        assert.equal(await link.isVisible(), true, 'menu remains pinned after mouse leaves');
        await page.mouse.click(900, 300);
        await link.waitFor({ state: 'hidden' });
        await trigger.focus();
        await page.keyboard.press('ArrowDown');
        assert.equal(await link.evaluate(el => document.activeElement === el), true);
        await page.keyboard.press('Escape');
        await link.waitFor({ state: 'hidden' });
        await trigger.hover();
        await link.click();
        await page.waitForURL('**/forecast.html');
        await page.goto('http://127.0.0.1:14331/');

        await page.evaluate(() => {
            currentIndex = dialogs.reduce((best, value, index) => value.length > dialogs[best].length ? index : best, 0);
            hasFinishedLoop = false;
            showRandomDialog();
        });
        function bubbleFits() {
            const bubble = document.getElementById('dialog-bubble'), rect = bubble.getBoundingClientRect();
            return rect.top >= 0 && rect.left >= 0 && rect.right <= innerWidth + 1 && rect.bottom <= innerHeight;
        }
        await page.waitForFunction(bubbleFits);
        await page.screenshot({ path: '/private/tmp/dialog-desktop.png', animations: 'disabled' });
        for (const viewport of [{ width: 1280, height: 520 }, { width: 390, height: 844 },
            { width: 390, height: 360 }, { width: 800, height: 320 }, { width: 320, height: 480 }]) {
            await page.setViewportSize(viewport);
            await page.waitForFunction(bubbleFits);
            const font = await page.locator('#dialog-bubble').evaluate(el => parseFloat(getComputedStyle(el).fontSize));
            assert.ok(font >= 12, 'keep text readable rather than shrinking without limit');
        }
        await page.screenshot({ path: '/private/tmp/dialog-mobile.png', animations: 'disabled' });
        await page.evaluate(() => {
            document.getElementById('dialog-text').textContent = '极长文本无空格'.repeat(1000);
            fitDialogBubble();
        });
        await page.waitForFunction(bubbleFits);
        const scroll = await page.locator('#dialog-text').evaluate(el => {
            el.scrollTop = el.scrollHeight;
            return { height: el.clientHeight, scrollHeight: el.scrollHeight, scrollTop: el.scrollTop };
        });
        assert.ok(scroll.scrollHeight > scroll.height && scroll.scrollTop > 0, 'extreme text is readable with internal scrolling');
        await page.setViewportSize({ width: 1280, height: 900 });
        await page.evaluate(() => { document.getElementById('dialog-text').textContent = '短句'; fitDialogBubble(); });
        assert.equal(await page.locator('#dialog-bubble').evaluate(el => getComputedStyle(el).fontSize), '15px');
        await page.setViewportSize({ width: 390, height: 844 });
        await page.reload();
        await page.locator('.nav-bar .dropdown > .nav-item').first().click();
        assert.equal(await page.locator('.nav-bar .dropdown .dropdown-menu a').first().isVisible(), true);
        assert.deepEqual(errors, []);
        console.log('PASS: pinned dropdown across gap, outside click/Escape/keyboard/link navigation/mobile click; longest dialogue + resize/short screens/readable scrolling.');
    } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
