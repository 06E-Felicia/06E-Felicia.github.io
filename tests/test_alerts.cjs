// Deterministic browser-logic tests. Fixtures never enter production config.json.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function browser(iso = '2026-05-20T12:05:00+08:00', stored = null, storageBlocked = false) {
    let clock = Date.parse(iso);
    const elements = new Map(), listeners = {}, intervals = [];
    const document = {
        activeElement: null, hidden: false, body: { style: {} },
        addEventListener: (type, callback) => { listeners[type] = callback; },
        getElementById: id => {
            if (!elements.has(id)) elements.set(id, element(id));
            return elements.get(id);
        },
        createElement: tag => element(tag),
        querySelectorAll: () => []
    };
    function element(id) {
        return { id, style: {}, textContent: '', hidden: false, isConnected: true,
            handlers: {}, children: [], classList: { remove() {} },
            addEventListener(type, callback) { this.handlers[type] = callback; },
            append(...children) { this.children.push(...children); },
            replaceChildren() { this.children = []; },
            removeAttribute(name) { delete this[name]; },
            querySelectorAll() { return []; },
            focus() { document.activeElement = this; }
        };
    }
    class TestDate extends Date {
        constructor(...args) { super(...(args.length ? args : [clock])); }
        static now() { return clock; }
    }
    const storage = new Map(stored ? [['shenzhen-thunder-mode-v1', stored]] : []);
    const context = vm.createContext({ Date: TestDate, Intl, document, window: { addEventListener() {} }, console,
        localStorage: {
            getItem(key) { if (storageBlocked) throw Error('blocked'); return storage.get(key); },
            setItem(key, value) { if (storageBlocked) throw Error('blocked'); storage.set(key, value); }
        },
        setInterval(fn, ms) { intervals.push({ fn, ms }); },
        fetch: async () => ({ ok: true, json: async () => snapshot() })
    });
    for (const file of ['thunder.js', 'script.js'])
        vm.runInContext(fs.readFileSync(`assets/scripts/${file}`, 'utf8'), context);
    function snapshot() {
        const date = iso.slice(0, 10);
        return { THUNDER_MONITOR_CONFIG: { default_mode: 'auto' },
            ALERT_CONFIG: { enabled: true, title: '测试深圳官方预警', message: '测试', image: '' },
            THUNDER_ALERT_CONFIG: { enabled: true, status: 'estimated_risk', event_id: 'test',
                generated_at: `${date}T12:05:00+08:00`, valid_until: `${date}T12:49:00+08:00`,
                settings: { default_mode: 'auto', speed_kmh: 50, data_ttl_minutes: 45,
                    target_latitude: 22.5431, target_longitude: 114.0579,
                    high_confidence_distance_km: 60, medium_confidence_distance_km: 150, radar_max_age_minutes: 45, arrival_grace_minutes: 30 },
                candidates: [{ city: '珠海', district: '珠海市', type: '雷电', confidence: '较高',
                    distance_km: 49.4, travel_minutes: 59, source_longitude: 113.5766, source_latitude: 22.271,
                    published_at: `${date}T11:20:00+08:00`, estimated_arrival: `${date}T12:19:00+08:00`,
                    expires_at: `${date}T12:49:00+08:00`, message: '<script>not executable</script>',
                    source_url: 'https://www.gd121.cn/yj/content.shtml?code=test' }], radar: {} }
        };
    }
    context.fixture = snapshot();
    vm.runInContext('applyRuntimeConfig(mergeConfig(fixture))', context);
    return {
        run: code => vm.runInContext(code, context),
        el: id => document.getElementById(id), context, storage, intervals, listeners,
        advance(ms) { clock += ms; },
        select(value) { const select = document.getElementById('thunder-mode'); select.value = value;
            select.handlers.change({ target: select }); }
    };
}

(async () => {
    const b = browser();
    await b.run('initPage()');
    assert.equal(b.el('thunder-overlay').style.display, 'flex');
    assert.equal(b.el('alert-overlay').style.display, 'none');
    assert.match(b.el('thunder-countdown').textContent, /14 分 0 秒/);
    b.advance(61000); b.run('ThunderAlerts.expire()');
    assert.match(b.el('thunder-countdown').textContent, /12 分 59 秒/);
    assert.match(b.el('thunder-message').textContent, /59 分钟/);
    assert.equal(b.el('thunder-img').hidden, true);
    b.run('closeThunderAlert()');
    assert.equal(b.el('alert-overlay').style.display, 'flex');
    await b.run('refreshPageConfig()');
    assert.equal(b.el('thunder-overlay').style.display, 'none', 'same snapshot must not reopen');
    b.select('off');
    assert.equal(b.run('ThunderAlerts.valid()'), false);
    assert.equal(b.el('alert-overlay').style.display, 'flex');
    assert.equal(b.storage.get('shenzhen-thunder-mode-v1'), 'off');
    b.select('on');
    assert.equal(b.el('thunder-overlay').style.display, 'flex');
    b.advance(13 * 60000 - 1000); // Exactly 12:19:00 (zero remaining).
    b.intervals.find(timer => timer.ms === 1000).fn();
    assert.equal(b.el('thunder-overlay').style.display, 'flex');
    assert.match(b.el('thunder-countdown').textContent, /剩余 0 分 0 秒.*30 分钟保留期/);
    b.advance(30 * 60000);
    b.intervals.find(timer => timer.ms === 1000).fn();
    assert.equal(b.el('thunder-overlay').style.display, 'none');
    assert.equal(b.el('alert-overlay').style.display, 'flex');

    const october = browser('2026-10-12T12:05:00+08:00');
    october.run('checkAndShowAlert()');
    assert.equal(october.run('ThunderAlerts.valid()'), false);
    october.select('on');
    assert.equal(october.run('ThunderAlerts.valid()'), true);
    october.advance(3600000);
    assert.equal(october.run('ThunderAlerts.show()'), false, 'manual ON cannot revive expired data');
    assert.equal(browser(undefined, 'off').run('ThunderAlerts.valid()'), false);
    const blocked = browser(undefined, null, true);
    blocked.select('off');
    assert.equal(blocked.run('ThunderAlerts.valid()'), false, 'blocked storage still supports session mode');
    const stale = browser(); stale.advance(46 * 60000);
    assert.equal(stale.run('ThunderAlerts.valid()'), false);
    const future = browser(); future.context.fixture.THUNDER_ALERT_CONFIG.generated_at = '2026-05-20T13:00:00+08:00';
    future.run('applyRuntimeConfig(mergeConfig(fixture))');
    assert.equal(future.run('ThunderAlerts.valid()'), false);

    const radar = browser();
    radar.run('checkAndShowAlert()');
    radar.context.fixture.THUNDER_ALERT_CONFIG.radar = {
        image: 'https://image.nmc.cn/product/test.PNG', observed_at: '2026-05-20T12:00:00+08:00' };
    radar.run('applyRuntimeConfig(mergeConfig(fixture))');
    assert.equal(radar.el('thunder-img').src, 'https://image.nmc.cn/product/test.PNG');
    radar.context.fixture.THUNDER_ALERT_CONFIG.radar.image = 'https://image.nmc.cn/product/new.PNG';
    radar.run('applyRuntimeConfig(mergeConfig(fixture))');
    assert.equal(radar.el('thunder-img').src, 'https://image.nmc.cn/product/new.PNG', 'visible radar refreshes without reopening event');
    radar.el('thunder-img').onerror();
    assert.equal(radar.el('thunder-img').hidden, true);
    console.log('PASS: popup order, per-second countdown, 30-minute grace/expiry, unchanged snapshot, manual modes, storage, freshness.');
})().catch(error => { console.error(error); process.exitCode = 1; });
