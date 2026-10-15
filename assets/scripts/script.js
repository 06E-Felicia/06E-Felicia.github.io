const dialogs = [
    "瓦达西瓦Sorakado Ao酱~",
    "不可以随便戳我(生气)",
    "Hentai Hentai Hentai!",
    "我要去找主人告状了！",
    "再戳就为您自动下载原神",
    "你为啥跟我直接表白啊？！嘎啦game里不是这样！",
    "我不接受！！！",
    "所以说，不要停下来啊",
    "明明是我先来的",
    "不，不行，还不能笑，我要忍住",
    "为什么你这么熟练啊！",
    "原神，启动！",
    "为什么，会变成这样呢",
    "你白银觉得是我的锅，那就是我的锅，为什么你知道吗，因为白银说的话，就像是一个，癌症晚期患者说的话一样，他都已经这样了，你为什么不顺从他呢，你总要给别人最后时间一个好的回忆吧，最后的时光里。因为白银这个段位很尴尬，白银黄金，再往上一点，白金钻石，可能说，哎，有点实力，能操作一下，白银往下，黄铜，一到五，啊，人家说纯属玩游戏的，太垃圾了，自己也知道自己没什么实力。但白银，上不去下不来的这个段位，他觉得黄铜的人，不配，跟他一起玩，对吧黄铜是最垃圾的。但是呢，他想上去，他就上不去，所以这个分段是最尴尬的，没办法，卡在这里了，想操作，又操作不起来；掉下去吧，他又觉得不值得，对吧，我好不容易从黄铜打到白银了，我为什么还要掉下去呢。",
    "↑ ↑ ↑↑↑, ↓ ↓ ↓↓↓",
    "队友呢，救一下啊！",
    "我不明白！我就是不明白！",
    "你去了祭典吧，和我不认识的女生一起",
    "听好了：1月25日，世界模式就此陷落。每个陷落的章节都将迎来一场漩涡，为这些旋律带来全新的Beyond难度。",
    "你说得对，但是原神是一款由米哈游自主研发的开放世界冒险游戏",
    "所以，我不做人了，JOJO！",
    "大家，并没有那么脆弱，不是吗",
    "双星很难吗？我rsk12.66",
    "这么高的颜值，却这么「纯情」，也太犯规了吧！！",
    "Never gonna give you up, never gonna let you down.",
    "跟我签订契约，成为魔法少女吧！",
    "我们结婚吧，雪菜",
    "你走了，我们吃什么",
    "不要做那种令人悲伤的事啊！",
    "我依然是世一上",
    "我在此宣誓,无论疾病还是健康,无论快乐还是忧愁,无论富有还是贫穷,直到死亡将我们俩分开,希望能永远和盐在一起,希望能永远和砂糖在一起.这就是，爱的证明.我发誓我会永远爱着盐;我发誓我会永远爱着砂糖",
    "孤独畅饮 利群与青岛 她的烟她的酒 茅台味香气 时光飞逝酱香依旧 我怎么能喝啤的不行不行 少女终末醉驾 少女酒局 想要喝掉我的酒鬼少女 玛娜利亚的酒友 明日酱的牛栏山 从梦之蓝被拒绝开始的酒局 banddrink一次喝够 女孩的养鱼漫活 迷生窖 重返国窖：1573 安达与杏花村 舍监的酒友，我的情敌",
    "战至最后一刻，自刎归天！"
];

const DEFAULT_APP_CONFIG = {
    LIVE_DATA: {
        t: "--",
        time: "--",
        th: "--",
        tl: "--",
        r_day: "--",
        r_1h: "--",
        p: "--"
    },
    MANUAL_CONFIG: {
        low: "--",
        high: "--",
        humidity: "--",
        rainProb: "--",
        wind: "--",
        dir: "--",
        icon: "",
        bg: ""
    },
    ALERT_CONFIG: {
        enabled: false,
        title: "",
        image: "",
        message: ""
    },
    WARNINGS: [],
    THUNDER_ALERT_CONFIG: { enabled: false },
    THUNDER_MONITOR_CONFIG: { default_mode: "auto" },
    FORECAST: [],
    META: {}
};

let LIVE_DATA = { ...DEFAULT_APP_CONFIG.LIVE_DATA };
let MANUAL_CONFIG = { ...DEFAULT_APP_CONFIG.MANUAL_CONFIG };
let ALERT_CONFIG = { ...DEFAULT_APP_CONFIG.ALERT_CONFIG };
let WARNINGS = [...DEFAULT_APP_CONFIG.WARNINGS];
let lastAlertSignature = "";
let configRefreshing = false;
let updateAnnouncementDismissed = false;
let updateAnnouncementReturnFocus = null;

let dialogTimer = null;
let currentIndex = 0;
let hasFinishedLoop = false;

function mergeConfig(fileConfig = {}) {
    return {
        LIVE_DATA: {
            ...DEFAULT_APP_CONFIG.LIVE_DATA,
            ...(fileConfig.LIVE_DATA || {})
        },
        MANUAL_CONFIG: {
            ...DEFAULT_APP_CONFIG.MANUAL_CONFIG,
            ...(fileConfig.MANUAL_CONFIG || {})
        },
        ALERT_CONFIG: {
            ...DEFAULT_APP_CONFIG.ALERT_CONFIG,
            ...(fileConfig.ALERT_CONFIG || {})
        },
        WARNINGS: Array.isArray(fileConfig.WARNINGS)
            ? fileConfig.WARNINGS
            : DEFAULT_APP_CONFIG.WARNINGS,
        THUNDER_ALERT_CONFIG: fileConfig.THUNDER_ALERT_CONFIG || DEFAULT_APP_CONFIG.THUNDER_ALERT_CONFIG,
        THUNDER_MONITOR_CONFIG: fileConfig.THUNDER_MONITOR_CONFIG || DEFAULT_APP_CONFIG.THUNDER_MONITOR_CONFIG,
        FORECAST: Array.isArray(fileConfig.FORECAST)
            ? fileConfig.FORECAST
            : DEFAULT_APP_CONFIG.FORECAST,
        META: fileConfig.META || DEFAULT_APP_CONFIG.META
    };
}

async function loadAppConfig() {
    try {
        const response = await fetch("config.json", { cache: "no-store" });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const fileConfig = await response.json();
        return mergeConfig(fileConfig);
    } catch (err) {
        console.error("读取 config.json 失败，已使用默认配置:", err);
        return mergeConfig();
    }
}

function applyRuntimeConfig(appConfig) {
    LIVE_DATA = appConfig.LIVE_DATA;
    MANUAL_CONFIG = appConfig.MANUAL_CONFIG;
    ALERT_CONFIG = appConfig.ALERT_CONFIG;
    WARNINGS = appConfig.WARNINGS;
    ThunderAlerts.update(appConfig.THUNDER_ALERT_CONFIG, appConfig.THUNDER_MONITOR_CONFIG);
}

function showRandomDialog() {
    const bubble = document.getElementById('dialog-bubble');
    let targetText = "";

    if (!hasFinishedLoop) {
        targetText = dialogs[currentIndex];
        currentIndex++;
        if (currentIndex >= dialogs.length) hasFinishedLoop = true;
    } else {
        const randomIdx = Math.floor(Math.random() * (dialogs.length - 1)) + 1;
        targetText = dialogs[randomIdx];
    }

    document.getElementById('dialog-text').textContent = targetText;
    bubble.classList.add('active');
    fitDialogBubble();

    if (dialogTimer) clearTimeout(dialogTimer);
    dialogTimer = setTimeout(() => {
        bubble.classList.remove('active');
        dialogTimer = null;
    }, Math.min(30000, Math.max(3000, targetText.length * 70)));
}

function fitDialogBubble() {
    const bubble = document.getElementById('dialog-bubble');
    if (!bubble?.classList.contains('active')) return;
    const content = document.getElementById('dialog-text');
    const viewportHeight = window.innerHeight, viewportWidth = window.innerWidth;
    const navBottom = document.querySelector('.nav-bar')?.getBoundingClientRect().bottom || 0;
    const safeTop = Math.min(Math.max(12, navBottom + 12), Math.max(12, viewportHeight - 120));
    const characterTop = document.querySelector('.floating-display')?.getBoundingClientRect().top;
    const anchorBottom = Number.isFinite(characterTop) ? viewportHeight - characterTop + 12 : 160;
    // Keep the bubble near the character, but let it move down on short screens.
    const bottom = Math.max(12, Math.min(anchorBottom, viewportHeight - safeTop - 120));
    const styles = getComputedStyle(bubble);
    // Computed 'auto' insets may resolve to pixels (even negative after resize).
    // Follow the same anchor breakpoint as CSS rather than inferring it from left.
    const side = parseFloat(viewportWidth <= 768 ? styles.right : styles.left) || 12;
    const preferredWidth = content.textContent.length > 100 ? 360 : 240;
    bubble.style.width = `${Math.max(40, Math.min(preferredWidth, viewportWidth - side - 12))}px`;
    bubble.style.maxWidth = bubble.style.width;
    bubble.style.bottom = `${bottom}px`;
    const padding = parseFloat(styles.paddingTop) + parseFloat(styles.paddingBottom);
    const maxTextHeight = Math.max(16, viewportHeight - safeTop - bottom - padding - 12);
    content.style.maxHeight = '';
    let fontSize = viewportWidth <= 480 ? 12 : viewportWidth <= 768 ? 13 : 15;
    bubble.style.fontSize = `${fontSize}px`;
    while (content.scrollHeight > maxTextHeight && fontSize > 12) {
        bubble.style.fontSize = `${--fontSize}px`;
    }
    content.style.maxHeight = `${Math.floor(maxTextHeight)}px`;
}

window.addEventListener('resize', fitDialogBubble);

function initDropdownMenus() {
    const items = [...document.querySelectorAll('.nav-bar .dropdown')];
    function closeMenus(except = null) {
        items.forEach(item => {
            if (item === except) return;
            item.classList.remove('is-open');
            item.querySelector('.nav-item').setAttribute('aria-expanded', 'false');
        });
    }
    items.forEach((item, index) => {
        const trigger = item.querySelector('.nav-item'), menu = item.querySelector('.dropdown-menu');
        menu.id ||= `nav-dropdown-${index}`;
        trigger.setAttribute('aria-controls', menu.id);
        trigger.setAttribute('aria-expanded', 'false');
        function openMenu() {
            closeMenus(item);
            item.classList.add('is-open');
            trigger.setAttribute('aria-expanded', 'true');
        }
        // No mouseleave handler: crossing the gap must not close the disclosure.
        item.addEventListener('mouseenter', openMenu);
        trigger.addEventListener('focus', openMenu);
        trigger.addEventListener('click', event => { event.preventDefault(); openMenu(); });
        trigger.addEventListener('keydown', event => {
            if (event.key === ' ' || event.key === 'ArrowDown') {
                event.preventDefault(); openMenu();
                menu.querySelector('a')?.focus();
            }
        });
        menu.addEventListener('click', event => { if (event.target.closest('a')) closeMenus(); });
        item.addEventListener('focusout', event => {
            if (!item.contains(event.relatedTarget)) closeMenus();
        });
    });
    document.addEventListener('click', event => {
        if (!event.target.closest('.nav-bar .dropdown')) closeMenus();
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        const opened = items.find(item => item.classList.contains('is-open'));
        if (opened) {
            // Focusing first avoids a focus handler reopening the dismissed menu.
            opened.querySelector('.nav-item').focus();
            closeMenus();
        }
    });
}

initDropdownMenus();

function generateECUrl(offsetHours = 0) {
    // 1. 获取基础时间（减去偏移量）
    let now = new Date(new Date().getTime() - offsetHours * 60 * 60 * 1000);

    let utcHours = now.getUTCHours();
    let cycle = "00";
    let targetDate = new Date(now); // 创建一个副本用于调整

    // 2. 判断逻辑优化
    if (utcHours >= 20) {
        cycle = "12";
    } else if (utcHours >= 8) {
        cycle = "00";
    } else {
        // 关键点：直接通过 Date 对象减去一天，它会自动处理月份和年份的跨度
        targetDate.setUTCDate(targetDate.getUTCDate() - 1);
        cycle = "12";
    }

    // 3. 从最终确定的 Date 对象中提取格式化字符串
    const utcYear = targetDate.getUTCFullYear();
    const utcMonth = String(targetDate.getUTCMonth() + 1).padStart(2, '0');
    const utcDay = String(targetDate.getUTCDate()).padStart(2, '0');

    const timeStr = `${utcYear}${utcMonth}${utcDay}${cycle}`;
    return `https://www.smca.fun/assets/image/NWP/ECMWF/Six_Elem/${timeStr}/1795565_${timeStr}.png`;
}

function updateECForecastImage() {
    const linkElement = document.getElementById('ec-link');
    const primaryUrl = generateECUrl(0);
    if (linkElement) linkElement.href = primaryUrl;
}

function showUpdateAnnouncement() {
    const overlay = document.getElementById('update-overlay');
    if (!overlay || updateAnnouncementDismissed) return false;
    if (overlay.style.display !== 'flex') updateAnnouncementReturnFocus = document.activeElement;
    document.getElementById('alert-overlay').style.display = 'none';
    ThunderAlerts.hide();
    overlay.style.display = 'flex';
    document.getElementById('update-close').focus();
    return true;
}

function closeUpdateAnnouncement() {
    updateAnnouncementDismissed = true;
    const overlay = document.getElementById('update-overlay');
    if (overlay) overlay.style.display = 'none';
    if (updateAnnouncementReturnFocus?.isConnected) updateAnnouncementReturnFocus.focus();
    updateAnnouncementReturnFocus = null;
    checkAndShowAlert();
}

document.getElementById('update-overlay')?.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); closeUpdateAnnouncement(); return; }
    if (event.key !== 'Tab') return;
    const controls = [...document.getElementById('update-overlay').querySelectorAll('a[href], button')]
        .filter(element => element.getClientRects().length > 0);
    if (!controls.length) return;
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

function checkAndShowAlert() {
    if (showUpdateAnnouncement()) return;
    document.getElementById('alert-overlay').style.display = 'none';
    if (!ThunderAlerts.show()) showShenzhenAlert();
}

function closeThunderAlert() {
    ThunderAlerts.hide();
    showShenzhenAlert();
}

function showShenzhenAlert() {
    if (showUpdateAnnouncement()) return;
    const overlay = document.getElementById('alert-overlay');
    if (!ALERT_CONFIG.enabled || !ALERT_CONFIG.title || !ALERT_CONFIG.message) {
        overlay.style.display = 'none';
        return;
    }
    document.getElementById('alert-title').innerText = ALERT_CONFIG.title;
    document.getElementById('alert-img').src = ALERT_CONFIG.image;
    document.getElementById('alert-msg').innerText = ALERT_CONFIG.message;
    overlay.style.display = 'flex';
}

function closeAlert() {
    document.getElementById('alert-overlay').style.display = 'none';
}

function render() {
    if (MANUAL_CONFIG.bg) {
        document.body.style.backgroundImage = `url('${MANUAL_CONFIG.bg}')`;
    }
    document.getElementById('ui-icon').src = MANUAL_CONFIG.icon || "";
    document.getElementById('ui-low').innerText = MANUAL_CONFIG.low;
    document.getElementById('ui-high').innerText = MANUAL_CONFIG.high;
    document.getElementById('ui-hum').innerText = MANUAL_CONFIG.humidity;
    document.getElementById('ui-rain-pre').innerText = MANUAL_CONFIG.rainProb;
    document.getElementById('ui-wind').innerText = MANUAL_CONFIG.wind;
    document.getElementById('ui-dir').innerText = MANUAL_CONFIG.dir;
    document.getElementById('t').innerText = LIVE_DATA.t;
    document.getElementById('r_day').innerText = LIVE_DATA.r_day;
    document.getElementById('r_1h').innerText = LIVE_DATA.r_1h;
    document.getElementById('p').innerText = LIVE_DATA.p;
    document.getElementById('ltime').innerText = "UPDATE: " + LIVE_DATA.time;

}

async function initPage() {
    // The announcement is independent of weather fetching. Updated snapshots
    // wait behind it; closing the card displays the latest valid alert queue.
    showUpdateAnnouncement();
    const appConfig = await loadAppConfig();
    applyRuntimeConfig(appConfig);
    render();
    lastAlertSignature = alertSignature(appConfig);
    checkAndShowAlert();
    // Re-read the static snapshot while a visitor keeps the page open.
    setInterval(refreshPageConfig, 5 * 60 * 1000);
    setInterval(() => {
        if (ThunderAlerts.expire()) showShenzhenAlert();
    }, 1000);
    setInterval(() => ThunderAlerts.refreshRadar(), 30 * 1000);
    // Timers may be throttled in background tabs; recheck immediately on return.
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && ThunderAlerts.expire()) showShenzhenAlert();
        ThunderAlerts.refreshRadar();
    });
}

function alertSignature(appConfig) {
    const thunder = ThunderAlerts.valid() ? (appConfig.THUNDER_ALERT_CONFIG.event_id || "") : "";
    return JSON.stringify([thunder, appConfig.ALERT_CONFIG]);
}

async function refreshPageConfig() {
    if (configRefreshing) return;
    configRefreshing = true;
    try {
        const appConfig = await loadAppConfig();
        applyRuntimeConfig(appConfig);
        render();
        const signature = alertSignature(appConfig);
        if (signature !== lastAlertSignature) {
            lastAlertSignature = signature;
            checkAndShowAlert();
        }
    } finally {
        configRefreshing = false;
    }
}

window.onload = initPage;
// 切换头像菜单显示
function toggleAvatarMenu(event) {
    event.stopPropagation(); // 阻止冒泡
    const menu = document.getElementById('avatar-menu');
    menu.classList.toggle('active');
}

// 点击页面其他地方关闭菜单
document.addEventListener('click', function () {
    const menu = document.getElementById('avatar-menu');
    if (menu) menu.classList.remove('active');
});
