import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from updater_common import load_config, log_error, save_config


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_list(value, default):
    if isinstance(value, list):
        return value
    return default


def _safe_find_text(element, class_name):
    """
    针对 Vue/React 异步渲染优化的文本提取
    使用 get_attribute('textContent') 可以抓取到尚未完全显示或被遮挡的文本
    """
    try:
        text = element.find_element(By.CLASS_NAME, class_name).get_attribute("textContent")
        return text.strip() if text else ""
    except Exception:
        return ""


def _extract_live_data(items, settings, targets, max_items=None):
    result = {}
    required_keys = set(targets.values())
    remaining_keys = set(required_keys)

    print(f"🔍 开始扫描元素，共发现 {len(items)} 个 stat-item")

    for index, item in enumerate(items):
        if max_items is not None and index >= max_items:
            break

        label_text = _safe_find_text(item, settings["label_class_name"])
        if not label_text:
            continue

        # 调试信息：打印网页上实际抓到的标签名
        target_key = targets.get(label_text)
        
        if target_key:
            value_text = _safe_find_text(item, settings["value_class_name"])
            if value_text:
                result[target_key] = value_text
                remaining_keys.discard(target_key)
                print(f"  ✅ 匹配成功: [{label_text}] -> {value_text}")
        
        # 提取数据时间（通常每个 item 里都有，取第一个即可）
        if "time" not in result:
            desc_text = _safe_find_text(item, settings["desc_class_name"])
            if desc_text and settings["time_prefix"] in desc_text:
                result["time"] = desc_text.replace(settings["time_prefix"], "", 1).strip()

        # 如果所有目标都找到了，提前结束循环
        if "time" in result and not remaining_keys:
            break

    return result


def get_runtime_settings(config):
    auto_cfg = config.get("AUTOUPDATE_CONFIG", {})
    return {
        "source_url": auto_cfg.get("source_url", "https://smca.fun/#/"),
        "wait_timeout": _safe_int(auto_cfg.get("wait_timeout", 30), 30),
        "page_load_timeout": _safe_int(auto_cfg.get("page_load_timeout", 30), 30),
        "script_timeout": _safe_int(auto_cfg.get("script_timeout", 30), 30),
        "max_items": _safe_int(auto_cfg.get("max_items", 200), 200),
        "targets": auto_cfg.get("targets", {
            "分钟气温": "temp_current",
            "最高气温": "temp_max",
            "最低气温": "temp_min",
            "日雨量": "rain_daily",
            "风速": "wind_speed",
            "风向": "wind_dir",
            "海平面气压": "pressure"
        }),
        "time_prefix": auto_cfg.get("time_prefix", "数据时间: "),
        "chrome_args": _safe_list(auto_cfg.get("chrome_args", ["--headless", "--no-sandbox", "--disable-dev-shm-usage"]), []),
        "wait_class_name": auto_cfg.get("wait_class_name", "stat-number"),
        "item_class_name": auto_cfg.get("item_class_name", "stat-item"),
        "label_class_name": auto_cfg.get("label_class_name", "stat-label"),
        "value_class_name": auto_cfg.get("value_class_name", "stat-number"),
        "desc_class_name": auto_cfg.get("desc_class_name", "stat-description"),
    }


def fetch_smca(config, settings):
    print("📡 正在启动浏览器获取实况数据...")
    opt = Options()
    opt.page_load_strategy = "normal"  # 确保页面资源加载完成
    for arg in settings["chrome_args"]:
        opt.add_argument(arg)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
    
    try:
        driver.set_page_load_timeout(settings["page_load_timeout"])
        driver.get(settings["source_url"])
        
        # 关键修改：不仅等待元素存在，还要等待数值里包含单位（代表 Vue 已完成数据填充）
        print(f"⏳ 等待页面渲染 (Timeout: {settings['wait_timeout']}s)...")
        wait = WebDriverWait(driver, settings["wait_timeout"])
        
        # 等待第一个 stat-number 包含数字或单位
        wait.until(lambda d: len(d.find_element(By.CLASS_NAME, settings["value_class_name"]).text.strip()) > 0)
        
        # 额外给 Vue 渲染留出 1 秒缓冲
        time.sleep(1)

        targets = settings["targets"]
        items = driver.find_elements(By.CLASS_NAME, settings["item_class_name"])
        res = _extract_live_data(items, settings, targets, settings["max_items"])

        if not res:
            print("⚠️ 提取结果为空，请检查 targets 映射是否与网页文字匹配。")
            log_error(config, "autoupdate.fetch_smca", "No live data extracted", driver.page_source[:1000])
        
        return res

    except Exception as e:
        print(f"❌ 抓取错误: {e}")
        log_error(config, "autoupdate.fetch_smca", str(e))
        return None
    finally:
        driver.quit()


def update_config(data):
    if not data: 
        print("⚠️ 未获取到有效数据，停止更新。")
        return

    config = load_config()
    # 深度对比，防止重复写入
    if config.get("LIVE_DATA") == data:
        print("ℹ️ LIVE_DATA 无变化，跳过写入。")
        return

    config["LIVE_DATA"] = data
    save_config(config)
    print(f"✅ LIVE_DATA 更新成功: {json.dumps(data, ensure_ascii=False)}")


if __name__ == "__main__":
    try:
        app_config = load_config()
    except Exception as e:
        print(f"❌ 读取配置失败: {e}")
        raise SystemExit(1)

    runtime_settings = get_runtime_settings(app_config)
    data = fetch_smca(app_config, runtime_settings)
    update_config(data)
