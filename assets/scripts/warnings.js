const WARNING_CONFIG_URL = "config.json";

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
    }[char]));
}

function renderWarnings(warnings) {
    const container = document.getElementById("warning-list");
    if (!warnings.length) {
        container.innerHTML = `
            <article class="no-warning-card">
                <span class="status-mark">✓</span>
                <div><h2>当前未生效深圳市气象预警</h2><p>请继续关注天气变化和官方最新消息。</p></div>
            </article>`;
        return;
    }
    container.innerHTML = warnings.map(warning => `
        <article class="warning-card warning-${escapeHtml(warning.color || "default")}">
            ${warning.icon ? `<img class="warning-icon" src="${escapeHtml(warning.icon)}" alt="${escapeHtml(warning.title)}">` : ""}
            <div class="warning-content"><h2>${escapeHtml(warning.title)}</h2><p>${escapeHtml(warning.message)}</p></div>
            <dl class="warning-meta"><div><dt>发布时间</dt><dd>${escapeHtml(warning.published_at || "--")}</dd></div><div><dt>生效区域</dt><dd>${escapeHtml(warning.area || "深圳市")}</dd></div></dl>
        </article>`).join("");
}

async function initWarningsPage() {
    try {
        const response = await fetch(WARNING_CONFIG_URL, { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const config = await response.json();
        renderWarnings(Array.isArray(config.WARNINGS) ? config.WARNINGS : []);
        document.getElementById("warning-update").textContent = config.META?.updated_at
            ? `实况更新时间 ${config.META.updated_at} · 深圳市气象台`
            : "数据来源：深圳市气象台";
    } catch (error) {
        console.error("读取预警失败", error);
        document.getElementById("warning-list").innerHTML = '<p class="empty-state">预警数据暂时不可用，请稍后刷新。</p>';
        document.getElementById("warning-update").textContent = "暂时无法读取预警数据";
    }
}

initWarningsPage();
