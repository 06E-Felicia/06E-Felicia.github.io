"""Fetch Shenzhen weather data from the public data files used by weather.sz.gov.cn."""

import json
import re
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__all__ = ["fetch_shenzhen_weather"]

DATA_BASE_URL = "https://weather.121.com.cn/data_cache/"
FORECAST_URL = DATA_BASE_URL + "szWeather/sz10day_new.js"
LIVE_URL = DATA_BASE_URL + "szWeather/szOssmo.js"
ALARM_URL = DATA_BASE_URL + "szWeather/alarm/szAlarm.js"
ALARM_ICON_BASE_URL = "https://weather.sz.gov.cn/alarmIcon/"
REQUEST_TIMEOUT = 20


def _parse_javascript_object(source):
    """Extract the JSON object from the official JavaScript data wrapper."""
    match = re.search(r"=\s*(\{.*\})\s*;?\s*}\s*catch", source, re.DOTALL)
    if not match:
        raise ValueError("Official data file did not contain a JSON object")
    return json.loads(match.group(1))


def _fetch_jsonp(url):
    """Fetch once per half-second retry without requiring third-party packages."""
    last_error = None
    request = Request(url, headers={"User-Agent": "ShenzhenWeatherBoard/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return _parse_javascript_object(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
    raise last_error


def _temperature(value):
    try:
        return f"{float(value):g}°C"
    except (TypeError, ValueError):
        return "--"


def _millimetres(value):
    try:
        return f"{float(value):g}mm"
    except (TypeError, ValueError):
        return "--"


def _hectopascals(value):
    try:
        return f"{float(value):g}hPa"
    except (TypeError, ValueError):
        return "--"


def _icon_path(icon):
    # Existing local icons are numbered 01-17; use them when an exact match exists.
    icon = str(icon or "").split("_")[0].replace(".png", "")
    return f"assets/images/weather_icons/{icon}.png" if icon else ""


def _short_weather(report):
    """Keep the compact home card readable; full wording remains on forecast.html."""
    return str(report or "暂无预报").split("；", 1)[0].strip()


def _normalise_forecast(data):
    forecasts = []
    for day in data.get("daynew", [])[:7]:
        raw_date = str(day.get("reportTime") or day.get("reporttime") or "")[:10]
        try:
            date = datetime.strptime(raw_date, "%Y-%m-%d")
            date_label = f"{date.month}月{date.day}日"
            weekday = "周" + "一二三四五六日"[date.weekday()]
        except ValueError:
            date_label, weekday = raw_date or "--", ""

        forecasts.append({
            "date": date_label,
            "weekday": weekday,
            "weather": day.get("report", "暂无预报"),
            "low": _temperature(day.get("minT")),
            "high": _temperature(day.get("maxT")),
            "humidity": f"{day.get('minU', '--')}%-{day.get('maxU', '--')}%",
            "wind": f"{day.get('wd', '--')}风 {day.get('ws', '--')}级",
            "icon": _icon_path(day.get("icon")),
            "published_at": day.get("pubTime", ""),
        })
    return forecasts


def _normalise_warning(warning):
    alarm_type = str(warning.get("alarmType") or "气象")
    alarm_color = str(warning.get("alarmColor") or "").strip()
    icon = str(warning.get("icon") or "")
    return {
        "title": f"深圳市{alarm_type}{alarm_color}预警",
        "type": alarm_type,
        "color": alarm_color,
        "message": warning.get("str") or "",
        "published_at": warning.get("date") or "",
        "area": warning.get("alarmArea") or "深圳市",
        "icon": f"{ALARM_ICON_BASE_URL}{icon}.png" if icon else "",
    }


def _build_payload(forecast_data, live_data, alarm_data):
    today = forecast_data.get("today", {})
    forecasts = _normalise_forecast(forecast_data)
    warnings = [_normalise_warning(item) for item in alarm_data.get("subAlarm", [])]
    primary_warning = warnings[0] if warnings else None
    humidity_low = today.get("minU", today.get("humidity", "--"))
    humidity_high = today.get("maxU", today.get("maxhumidity", "--"))

    return {
        "LIVE_DATA": {
            "time": live_data.get("date", "--"),
            "t": _temperature(live_data.get("t")),
            "th": _temperature(live_data.get("maxt")),
            "tl": _temperature(live_data.get("mint")),
            "r_day": _millimetres(live_data.get("r24h")),
            "r_1h": _millimetres(live_data.get("h01r")),
            "p": _hectopascals(live_data.get("p")),
        },
        "MANUAL_CONFIG": {
            "low": _temperature(today.get("minT")),
            "high": _temperature(today.get("maxT")),
            "humidity": f"{humidity_low}%-{humidity_high}%",
            "rainProb": _short_weather(today.get("report")),
            "wind": f"{today.get('ws', '--')}级",
            "dir": f"{today.get('wd', '--')}风",
            "icon": _icon_path(today.get("nextIcon") or today.get("icon")),
            "bg": "assets/images/background.jpg",
        },
        "FORECAST": forecasts,
        "WARNINGS": warnings,
        "ALERT_CONFIG": {
            "enabled": bool(primary_warning),
            "title": primary_warning["title"] if primary_warning else "",
            "image": primary_warning["icon"] if primary_warning else "",
            "message": primary_warning["message"] if primary_warning else "",
        },
        "META": {
            "source": "深圳市气象台",
            "forecast_updated_at": forecast_data.get("pubDate", ""),
            "updated_at": live_data.get("date", ""),
            "warnings_updated_at": alarm_data.get("alarmDate", ""),
        },
    }


def fetch_shenzhen_weather(logger):
    """Return all values required by the static site, or None when the source fails."""
    try:
        forecast_data = _fetch_jsonp(FORECAST_URL)
        live_data = _fetch_jsonp(LIVE_URL)
        alarm_data = _fetch_jsonp(ALARM_URL)
        return _build_payload(forecast_data, live_data, alarm_data)
    except Exception as error:
        logger.log_error("autoupdate.fetch_shenzhen_weather", str(error))
        return None
