import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

from updater_common import load_config, log_error, save_config


def get_runtime_settings(config):
    auto_cfg = config.get("AUTOUPDATE_CONFIG", {})
    return {
        "source_url": auto_cfg.get("source_url", "https://smca.fun/#/"),
        "wait_timeout": int(auto_cfg.get("wait_timeout", 15)),
        "targets": auto_cfg.get("targets", {}),
        "time_prefix": auto_cfg.get("time_prefix", "数据时间: "),
        "chrome_args": auto_cfg.get("chrome_args", []),
        "wait_class_name": auto_cfg.get("wait_class_name", "stat-number"),
        "item_class_name": auto_cfg.get("item_class_name", "stat-item"),
        "label_class_name": auto_cfg.get("label_class_name", "stat-label"),
        "value_class_name": auto_cfg.get("value_class_name", "stat-number"),
        "desc_class_name": auto_cfg.get("desc_class_name", "stat-description"),
    }


def fetch_smca(config, settings):
    print("📡 正在获取实况数据...")
    opt = Options()
    for arg in settings["chrome_args"]:
        opt.add_argument(arg)
    
    # GitHub Actions 环境建议写法
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opt)
    
    try:
        driver.get(settings["source_url"])
        wait = WebDriverWait(driver, settings["wait_timeout"])
        wait.until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, settings["wait_class_name"])
            )
        )
        
        targets = settings["targets"]
        res = {}
        
        # 获取所有数据项
        items = driver.find_elements(By.CLASS_NAME, settings["item_class_name"])
        for i in items:
            try:
                lbl = i.find_element(By.CLASS_NAME, settings["label_class_name"]).text.strip()
                val = i.find_element(By.CLASS_NAME, settings["value_class_name"]).text.strip()
                if lbl in targets:
                    res[targets[lbl]] = val
                if "time" not in res:
                    desc = i.find_element(By.CLASS_NAME, settings["desc_class_name"]).text
                    res["time"] = desc.replace(settings["time_prefix"], "").strip()
            except Exception:
                continue

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
