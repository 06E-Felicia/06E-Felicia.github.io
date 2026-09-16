const FORECAST_CONFIG_URL = "config.json";

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[char]));
}

function renderForecast(forecast) {
    const container = document.getElementById("forecast-list");
    if (!forecast.length) {
        container.innerHTML = '<p class="empty-state">暂未获取到预报数据，请稍后刷新。</p>';
        return;
    }
    container.innerHTML = forecast.map((day, index) => `
        <article class="forecast-day ${index === 0 ? "is-first" : ""}">
            <div class="forecast-date"><strong>${escapeHtml(day.date)}</strong><span>${escapeHtml(day.weekday)}</span></div>
            <img class="forecast-day-icon" src="${escapeHtml(day.icon)}" alt="${escapeHtml(day.weather)}">
            <div class="forecast-summary"><p>${escapeHtml(day.weather)}</p><span>${escapeHtml(day.wind)} · 湿度 ${escapeHtml(day.humidity)}</span></div>
            <div class="forecast-temperature"><b>${escapeHtml(day.high)}</b><span>${escapeHtml(day.low)}</span></div>
        </article>`).join("");
}

async function initForecastPage() {
    try {
        const response = await fetch(FORECAST_CONFIG_URL, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const config = await response.json();
        renderForecast(Array.isArray(config.FORECAST) ? config.FORECAST : []);
        document.getElementById("forecast-update").textContent = config.META?.forecast_updated_at
            ? `更新于 ${config.META.forecast_updated_at} · 深圳市气象台`
            : "数据来源：深圳市气象台";
    } catch (error) {
        console.error("读取一周预报失败", error);
        document.getElementById("forecast-list").innerHTML = '<p class="empty-state">预报数据暂时不可用，请稍后刷新。</p>';
        document.getElementById("forecast-update").textContent = "暂时无法读取预报数据";
    }
}

initForecastPage();
