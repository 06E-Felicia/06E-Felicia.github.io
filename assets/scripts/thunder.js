/* City-centre meridian projection at 50 km/h, not official radar tracking. */
const ThunderAlerts = (() => {
    let config = {}, defaultMode = "auto", returnFocus = null;
    let failedRadarImage = "";
    const modes = ["auto", "on", "off"];
    const overlay = () => document.getElementById("thunder-overlay");
    const text = (id, value) => { document.getElementById(id).textContent = value; };
    const formatTime = value => new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23"
    }).format(new Date(value));
    function active(now = new Date()) {
        const month = Number(new Intl.DateTimeFormat("en", {
            timeZone: "Asia/Shanghai", month: "numeric"
        }).format(now));
        return defaultMode === "on" || (defaultMode === "auto" && month >= 3 && month <= 5);
    }
    function fresh(now = new Date()) {
        const generated = Date.parse(config.generated_at), expiry = Date.parse(config.valid_until);
        return config.status !== "source_error" && Number.isFinite(generated)
            && generated <= now.getTime() && Number.isFinite(expiry) && expiry > now.getTime()
            && now.getTime() - generated <= (config.settings?.data_ttl_minutes || 45) * 60000;
    }
    function valid(now = new Date()) {
        const primary = config.candidates?.[0];
        // Only the centrally generated snapshot may authorize a popup.
        return config.enabled === true && active(now) && fresh(now) && !!primary && config.settings?.speed_kmh === 50
            && Number.isFinite(Date.parse(primary.estimated_arrival))
            && Date.parse(primary.expires_at) > now.getTime();
    }
    function update(value, settings = {}) {
        config = value || {};
        const requestedMode = settings.default_mode ?? config.settings?.default_mode ?? "auto";
        defaultMode = modes.includes(requestedMode) ? requestedMode : "off";
        refreshRadar();
    }
    function hide() {
        overlay().style.display = "none";
        if (returnFocus?.isConnected) returnFocus.focus();
        returnFocus = null;
    }
    function countdown(now = new Date()) {
        const remaining = Math.max(0, Math.ceil((Date.parse(config.candidates?.[0]?.estimated_arrival) - now.getTime()) / 1000));
        if (!Number.isFinite(remaining)) return;
        const hours = Math.floor(remaining / 3600), minutes = Math.floor(remaining % 3600 / 60), seconds = remaining % 60;
        text("thunder-countdown", remaining > 0
            ? `距估测抵达还有 ${hours ? hours + " 小时 " : ""}${minutes} 分 ${seconds} 秒`
            : `剩余 0 分 0 秒 · 已到估测时刻，进入 ${config.settings.arrival_grace_minutes} 分钟保留期`);
    }
    function show() {
        if (!valid()) { hide(); return false; }
        const primary = config.candidates[0], settings = config.settings;
        text("thunder-title", config.title || "上游雷暴抵达估测（非官方预警）");
        text("thunder-arrival", `若飑线向东推进，估测抵达：${formatTime(primary.estimated_arrival)}（北京时间）`);
        countdown();
        text("thunder-confidence", `距离可信度：${primary.confidence} · 投影距离约 ${primary.distance_km} km · 统一 50 km/h`);
        text("thunder-message", `${primary.city} · ${primary.district}发布${primary.type}预警。以${formatTime(primary.published_at)}为时间起点，加 ${primary.travel_minutes} 分钟。仅针对深圳参考点经线，不代表全市统一抵达时刻；不将不同城市的预警认定为同一条飑线。`);
        text("thunder-formula", `距离 = 6371.0088 × cos(${settings.target_latitude}°) × (${settings.target_longitude}° − 城市中心经度) × π/180；抵达 = 预警发布时间 + 距离 ÷ 50 km/h，耗时四舍五入到分钟。先选最近城市，再取该城市最新有效预警。距离 ≤${settings.high_confidence_distance_km} km 为较高、≤${settings.medium_confidence_distance_km} km 为中等，其余较低；未经统计校准。`);
        const evidence = document.getElementById("thunder-evidence");
        evidence.replaceChildren();
        config.candidates.forEach(candidate => {
            const article = document.createElement("article"), heading = document.createElement("h3");
            heading.textContent = `${candidate.city} · ${candidate.district} · ${candidate.type}`;
            const calculation = document.createElement("p");
            calculation.textContent = `城市中心近似坐标：${candidate.source_longitude}°E、${candidate.source_latitude}°N；沿经线投影到深圳参考纬度 ${settings.target_latitude}°N → 深圳 ${settings.target_longitude}°E。距离 ${candidate.distance_km} km ÷ 50 km/h ≈ ${candidate.travel_minutes} 分钟；${formatTime(candidate.published_at)} + 耗时 = ${formatTime(candidate.estimated_arrival)}；距离可信度 ${candidate.confidence}。`;
            const message = document.createElement("p"), link = document.createElement("a");
            message.textContent = candidate.message;
            link.textContent = "查看官方预警原文 ↗";
            if (candidate.source_url?.startsWith("https://www.gd121.cn/")) link.href = candidate.source_url;
            link.target = "_blank"; link.rel = "noopener";
            article.append(heading, calculation, message, link); evidence.append(article);
        });
        renderRadar();
        if (overlay().style.display !== "flex") returnFocus = document.activeElement;
        overlay().style.display = "flex";
        document.getElementById("thunder-close").focus();
        return true;
    }
    function renderRadar() {
        const settings = config.settings;
        const image = document.getElementById("thunder-img"), radar = config.radar || {};
        const radarAge = Date.now() - Date.parse(radar.observed_at);
        const radarValid = typeof radar.image === "string" && radar.image.startsWith("https://image.nmc.cn/")
            && radar.image !== failedRadarImage
            && Number.isFinite(radarAge) && radarAge >= -300000
            && radarAge <= settings.radar_max_age_minutes * 60000;
        image.hidden = !radarValid;
        image.onerror = () => { failedRadarImage = radar.image; image.hidden = true; text("thunder-radar-status", "雷达图片加载失败，请打开官方雷达页核验。"); };
        if (radarValid) { if (image.src !== radar.image) image.src = radar.image; }
        else image.removeAttribute("src");
        text("thunder-radar-status", radarValid ? `华南雷达 · ${formatTime(radar.observed_at)}（最新成功获取时次）`
            : "最新雷达暂时不可用，请打开官方雷达页核验。");
    }
    function refreshRadar() {
        if (overlay().style.display === "flex" && valid()) renderRadar();
    }
    function expire() {
        if (overlay().style.display === "flex" && !valid()) { hide(); return true; }
        if (overlay().style.display === "flex") countdown();
        return false;
    }
    overlay().addEventListener("keydown", event => {
        if (event.key === "Escape") { event.preventDefault(); closeThunderAlert(); }
        if (event.key !== "Tab") return;
        const controls = [...overlay().querySelectorAll("a[href], button, summary")]
            .filter(element => element.getClientRects().length > 0);
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    return { update, show, hide, valid, expire, refreshRadar };
})();
