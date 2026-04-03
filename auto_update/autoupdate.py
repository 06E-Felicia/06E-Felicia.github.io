import json
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
    try:
        return element.find_element(By.CLASS_NAME, class_name).text.strip()
    except Exception:
        return ""


def _extract_live_data(items, settings, targets, max_items=None):
    result = {}
    required_keys = set(targets.values())
    remaining_keys = set(required_keys)

    for index, item in enumerate(items):
        if max_items is not None and index >= max_items:
            break

        label_text = _safe_find_text(item, settings["label_class_name"])
        if not label_text:
            continue

        target_key = targets.get(label_text)
        if target_key and target_key not in result:
            value_text = _safe_find_text(item, settings["value_class_name"])
            if value_text:
                result[target_key] = value_text
                remaining_keys.discard(target_key)

        if "time" not in result:
            desc_text = _safe_find_text(item, settings["desc_class_name"])
            if desc_text:
                result["time"] = desc_text.replace(settings["time_prefix"], "", 1).strip()

        if "time" in result and not remaining_keys:
            break

    return result


def get_runtime_settings(config):
    auto_cfg = config.get("AUTOUPDATE_CONFIG", {})
    return {
        "source_url": auto_cfg.get("source_url", "https://smca.fun/#/"),
        "wait_timeout": _safe_int(auto_cfg.get("wait_timeout", 120), 120),
        "page_load_timeout": _safe_int(auto_cfg.get("page_load_timeout", 30), 30),
        "script_timeout": _safe_int(auto_cfg.get("script_timeout", 30), 30),
        "max_items": _safe_int(auto_cfg.get("max_items", 200), 200),
        "targets": auto_cfg.get("targets", {}),
        "time_prefix": auto_cfg.get("time_prefix", "数据时间: "),
        "chrome_args": _safe_list(auto_cfg.get("chrome_args", []), []),
        "wait_class_name": auto_cfg.get("wait_class_name", "stat-number"),
        "item_class_name": auto_cfg.get("item_class_name", "stat-item"),
        "label_class_name": auto_cfg.get("label_class_name", "stat-label"),
        "value_class_name": auto_cfg.get("value_class_name", "stat-number"),
        "desc_class_name": auto_cfg.get("desc_class_name", "stat-description"),
    }


def fetch_smca(config, settings):
    print("📡 正在获取实况数据...")
    opt = Options()
    opt.page_load_strategy = "eager"
    for arg in settings["chrome_args"]:
        opt.add_argument(arg)
    
    # GitHub Actions 环境建议写法
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
    
    try:
        driver.set_page_load_timeout(settings["page_load_timeout"])
        driver.set_script_timeout(settings["script_timeout"])

        driver.get(settings["source_url"])
        wait = WebDriverWait(driver, settings["wait_timeout"])
        wait.until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, settings["wait_class_name"])
            )
        )
        
        targets = settings["targets"]
        # 获取所有数据项，限制扫描范围并在目标齐全后提前结束。
        items = driver.find_elements(By.CLASS_NAME, settings["item_class_name"])
        res = _extract_live_data(items, settings, targets, settings["max_items"])

        if not res:
            log_error(
                config,
                "autoupdate.fetch_smca",
                "No live data extracted from page",
                driver.page_source[:1000],
            )
        return res
    except Exception as e:
        print(f"❌ 抓取错误: {e}")
        page_snapshot = ""
        try:
            page_snapshot = driver.page_source[:1000]
        except Exception:
            pass
        log_error(config, "autoupdate.fetch_smca", str(e), page_snapshot)
        return None
    finally:
        driver.quit()

def update_config(data):
    if not data: 
        print("⚠️ 未获取到有效数据，停止更新。")
        return

    config = load_config()
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
        log_error(None, "autoupdate.load_config", str(e))
        raise SystemExit(1)

    runtime_settings = get_runtime_settings(app_config)
    data = fetch_smca(app_config, runtime_settings)
    update_config(data)
