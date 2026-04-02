import time

import requests
from bs4 import BeautifulSoup

from updater_common import load_config, log_error, save_config


def get_warning_settings(config):
    warning_cfg = config.get("WARNING_CONFIG", {})
    return {
        "source_url": warning_cfg.get(
            "source_url",
            "https://weather.sz.gov.cn/qixiangfuwu/yujingfuwu/tufashijianyujing/index.html",
        ),
        "headers": warning_cfg.get("headers"),
        "city_selector_class": warning_cfg.get("city_selector_class", "tit fl tit_sz"),
        "request_timeout": int(warning_cfg.get("request_timeout", 20)),
        "refresh_interval": int(
            warning_cfg.get("refresh_interval", config.get("REFRESH_INTERVAL", 600))
        ),
    }


def fetch_sz_warnings(config, settings):
    response = None
    try:
        response = requests.get(
            settings["source_url"],
            headers=settings["headers"],
            timeout=settings["request_timeout"],
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")

        warn_icons = []
        sz_div = soup.find("div", class_=settings["city_selector_class"])
        if sz_div:
            imgs = sz_div.find_all("img")
            for img in imgs:
                src = img.get("src")
                if src:
                    warn_icons.append(src)

        return warn_icons
    except Exception as e:
        print(f"爬取失败: {e}")
        response_snapshot = ""
        if response is not None and response.text:
            response_snapshot = response.text[:1000]
        log_error(config, "warning.fetch_sz_warnings", str(e), response_snapshot)
        return []


def update_config():
    config = load_config()
    settings = get_warning_settings(config)
    warnings = fetch_sz_warnings(config, settings)

    config["WARNINGS"] = warnings
    config["REFRESH_INTERVAL"] = settings["refresh_interval"]
    save_config(config)

    print(f"[{time.strftime('%H:%M:%S')}] 更新成功，当前预警数: {len(warnings)}")
    return settings["refresh_interval"]


if __name__ == "__main__":
    while True:
        try:
            interval = update_config()
        except Exception as e:
            print(f"更新失败: {e}")
            log_error(None, "warning.update_config", str(e))
            interval = 600
        time.sleep(interval)
