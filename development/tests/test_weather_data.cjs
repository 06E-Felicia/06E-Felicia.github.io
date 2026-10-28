// Network failures, schema errors and timeout cleanup without external services.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

(async () => {
    const context = vm.createContext({ AbortController, setTimeout, clearTimeout });
    vm.runInContext(fs.readFileSync('assets/scripts/weather-data.js', 'utf8'), context);
    const load = keys => vm.runInContext(`WeatherData.load(${JSON.stringify(keys)}, 20)`, context);
    for (const data of [null, [], {}, { WARNINGS: null }, { WARNINGS: [null] }]) {
        context.fetch = async () => ({ ok: true, json: async () => data });
        await assert.rejects(load(['WARNINGS']), /格式异常|WARNINGS/);
    }
    context.fetch = async () => ({ ok: true, json: async () => ({ WARNINGS: [] }) });
    assert.equal((await load(['WARNINGS'])).WARNINGS.length, 0, 'a verified empty array is valid');
    context.fetch = async () => ({ ok: false, status: 503 });
    await assert.rejects(load([]), /HTTP 503/);
    context.fetch = async () => ({ ok: true, json: async () => { throw new SyntaxError('bad JSON'); } });
    await assert.rejects(load([]), /bad JSON/);
    let signal;
    context.fetch = async (_, options) => {
        signal = options.signal;
        return { ok: true, json: () => new Promise((resolve, reject) => {
            signal.addEventListener('abort', () => reject(new Error('timeout')), { once: true });
        }) };
    };
    await assert.rejects(load([]), /timeout/, 'timeout also covers a stalled response body');
    assert.equal(signal.aborted, true);
    context.fetch = async (_, options) => {
        signal = options.signal;
        return { ok: true, json: async () => ({ WARNINGS: [] }) };
    };
    await load(['WARNINGS']);
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(signal.aborted, false, 'successful requests clear their timeout');
    console.log('PASS: weather schema, empty warnings, HTTP/JSON errors, body timeout and timer cleanup.');
})().catch(error => { console.error(error); process.exitCode = 1; });
