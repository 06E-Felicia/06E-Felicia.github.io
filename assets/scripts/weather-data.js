// Shared snapshot reader. A failed or malformed response is never an empty forecast.
const WeatherData = (() => {
    const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value);
    async function load(required = [], timeoutMs = 15000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const response = await fetch('config.json', { cache: 'no-store', signal: controller.signal });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const config = await response.json();
            if (!isRecord(config)) throw new Error('天气快照格式异常');
            for (const key of required) {
                const value = config[key];
                const valid = key === 'FORECAST' || key === 'WARNINGS'
                    ? Array.isArray(value) && value.every(isRecord)
                    : isRecord(value) && Object.keys(value).length > 0;
                if (!valid) throw new Error(`天气快照缺少有效的 ${key}`);
            }
            return config;
        } finally {
            clearTimeout(timer);
        }
    }
    return { load };
})();
