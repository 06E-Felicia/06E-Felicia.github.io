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
    WARNINGS: []
};

let LIVE_DATA = { ...DEFAULT_APP_CONFIG.LIVE_DATA };
let MANUAL_CONFIG = { ...DEFAULT_APP_CONFIG.MANUAL_CONFIG };
let ALERT_CONFIG = { ...DEFAULT_APP_CONFIG.ALERT_CONFIG };
let WARNINGS = [...DEFAULT_APP_CONFIG.WARNINGS];

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
            : DEFAULT_APP_CONFIG.WARNINGS
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

    bubble.innerText = targetText;
    bubble.classList.add('active');

    if (dialogTimer) clearTimeout(dialogTimer);
    dialogTimer = setTimeout(() => {
        bubble.classList.remove('active');
        dialogTimer = null;
    }, 3000);
}

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

function checkAndShowAlert() {
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

    updateECForecastImage();
    checkAndShowAlert();
}

async function initPage() {
    const appConfig = await loadAppConfig();
    applyRuntimeConfig(appConfig);
    render();
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
