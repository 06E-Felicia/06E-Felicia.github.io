"""Seasonal, conditional squall-line estimates from Guangdong official warnings.

This is a longitude-projection heuristic, not radar tracking or an official forecast.
All times are explicitly in China Standard Time, including on GitHub runners.
"""

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen

CHINA_TZ = timezone(timedelta(hours=8))
WARNING_URL = "https://www.gd121.cn/api/ftproot/ActiveYJ.json"
RADAR_PAGE = "https://www.nmc.cn/publish/radar/huanan.html"
CITIES = {
    "4417": "阳江", "4412": "肇庆", "4407": "江门", "4420": "中山",
    "4404": "珠海", "4406": "佛山", "4401": "广州", "4419": "东莞",
}
# Approximate city-centre reference points, deliberately shared by all districts
# of the same city. Source latitude is not used in the longitude projection.
CITY_CENTRES = {
    "4417": (21.8580, 111.9820), "4412": (23.0470, 112.4650),
    "4407": (22.5787, 113.0819), "4420": (22.5176, 113.3926),
    "4404": (22.2710, 113.5766), "4406": (23.0215, 113.1214),
    "4401": (23.1291, 113.2644), "4419": (23.0207, 113.7518),
}
THUNDER_TYPES = {"雷雨大风", "暴雨", "雷电", "雷暴", "冰雹"}
DEFAULT_SETTINGS = {
    "default_mode": "auto",
    "speed_kmh": 50,
    "target_latitude": 22.5431,
    "target_longitude": 114.0579,
    # Covers the farthest city's 4h16 travel + 30-minute grace without resetting ETA.
    "max_warning_age_hours": 6,
    "data_ttl_minutes": 45,
    "radar_max_age_minutes": 45,
    "arrival_grace_minutes": 30,
    "high_confidence_distance_km": 60,
    "medium_confidence_distance_km": 150,
}


def china_now():
    return datetime.now(CHINA_TZ)


def parse_time(value):
    value = str(value or "").strip().replace(" ", "T", 1)
    # Guangdong uses a one-digit fraction (.0); Python 3.9/3.10 expect 3 or 6.
    value = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{1,6})(?=$|[+-])",
                   lambda match: match[1] + "." + match[2].ljust(6, "0"), value)
    parsed = datetime.fromisoformat(value)
    return (parsed.replace(tzinfo=CHINA_TZ) if parsed.tzinfo is None else parsed).astimezone(CHINA_TZ)


def timestamp(value):
    return value.isoformat(timespec="seconds")


def settings_from_config(config):
    settings = {**DEFAULT_SETTINGS, **(config or {})}
    for name in DEFAULT_SETTINGS:
        if name == "default_mode":
            if settings[name] not in {"auto", "on", "off"}:
                raise ValueError("default_mode must be auto, on or off")
        elif not isinstance(settings[name], (int, float)) or not math.isfinite(settings[name]):
            raise ValueError(f"Invalid thunder setting: {name}")
    if settings["speed_kmh"] != 50:
        raise ValueError("The agreed estimation speed is fixed at 50 km/h")
    if not -90 < settings["target_latitude"] < 90 or not -180 <= settings["target_longitude"] <= 180:
        raise ValueError("Invalid target coordinates")
    if not 0 < settings["high_confidence_distance_km"] < settings["medium_confidence_distance_km"]:
        raise ValueError("Invalid confidence distance thresholds")
    for key in ("max_warning_age_hours", "data_ttl_minutes", "radar_max_age_minutes", "arrival_grace_minutes"):
        if settings[key] <= 0:
            raise ValueError(f"{key} must be positive")
    return settings


def apply_monitor_mode(config, requested="keep"):
    """GitHub's admin-only workflow input; scheduled runs preserve the last mode."""
    aliases = {"保持当前设置": "keep", "自动（3–5 月）": "auto", "开启": "on", "关闭": "off"}
    requested = aliases.get(requested, requested)
    if requested not in {"keep", "auto", "on", "off"}:
        raise ValueError("Unknown backend monitor mode")
    settings = settings_from_config(config)
    if requested != "keep":
        settings["default_mode"] = requested
    return settings


def _read_url(url):
    request = Request(url, headers={
        "User-Agent": "ShenzhenWeatherBoard/1.0",
        "Cache-Control": "no-cache",
    })
    with urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8-sig")


class RadarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "img" and attrs.get("id") == "imgpath":
            self.image = attrs.get("src", "")


def parse_radar_page(html, now, max_age_minutes=45):
    parser = RadarParser()
    parser.feed(html)
    url = parser.image.replace("http://", "https://", 1)
    # The official image ID contains UTC time, while the page label uses UTC+8.
    match = re.search(r"_PI_(\d{14})\d*\.PNG", url, re.IGNORECASE)
    if urlparse(url).hostname != "image.nmc.cn" or not match or "_ASCN_" not in url:
        raise ValueError("Latest South China radar image not found on the official page")
    observed = datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).astimezone(CHINA_TZ)
    age = (now - observed).total_seconds() / 60
    if not -5 <= age <= max_age_minutes:
        raise ValueError("South China radar image is stale or dated in the future")
    return {"image": url, "observed_at": timestamp(observed), "source_url": RADAR_PAGE}


def projected_distance_km(source_longitude, target_latitude, target_longitude):
    """Eastward distance along the target latitude from a N-S projected line."""
    return max(0.0, 6371.0088 * math.cos(math.radians(target_latitude)) * math.radians(target_longitude - source_longitude))


def estimate_warning(row, settings, now):
    published = parse_time(row.get("PUBLISHDATE"))
    city_code = str(row["AREA_CODE"])[:4]
    latitude, longitude = CITY_CENTRES[city_code]
    if longitude > settings["target_longitude"]:
        return None, "east_of_target"
    distance = projected_distance_km(longitude, settings["target_latitude"], settings["target_longitude"])
    travel_minutes = int(distance / 50 * 60 + 0.5)
    arrival = published + timedelta(minutes=travel_minutes)
    expires = arrival + timedelta(minutes=settings["arrival_grace_minutes"])
    if expires <= now:
        return None, "elapsed_window"
    confidence = ("较高" if distance <= settings["high_confidence_distance_km"] else
                  "中等" if distance <= settings["medium_confidence_distance_km"] else "较低")
    city = CITIES[city_code]
    return {
        "id": str(row.get("INDENTIFIER") or row.get("ID") or ""),
        "city": city,
        "district": str(row.get("DISTRICTS_NAME") or city),
        "type": row["CATEGORY_CNNAME"],
        "title": str(row.get("TITLE") or ""),
        "message": str(row.get("CONTENT") or ""),
        "published_at": timestamp(published),
        "source_url": "https://www.gd121.cn/yj/content.shtml?" + urlencode({
            "code": str(row.get("INDENTIFIER") or ""), "city": str(row["AREA_CODE"])[:4],
        }),
        "distance_km": round(distance, 1),
        "source_latitude": latitude,
        "source_longitude": longitude,
        "coordinate_basis": "城市中心近似坐标沿经线投影",
        "travel_minutes": travel_minutes,
        "estimated_arrival": timestamp(arrival),
        "expires_at": timestamp(expires),
        "confidence": confidence,
    }, None


def build_thunder_alert(feed, settings, now):
    settings = settings_from_config(settings)
    now = now.astimezone(CHINA_TZ)
    result = {
        "enabled": False, "status": "outside_season", "generated_at": timestamp(now),
        "valid_until": timestamp(now + timedelta(minutes=settings["data_ttl_minutes"])),
        "title": "上游雷暴抵达估测（非官方预警）",
        "source_url": WARNING_URL, "method": "city_centre_meridian_projection_50kmh",
        "settings": settings, "candidates": [], "audit": {}, "radar": {},
    }
    if not isinstance(feed, dict) or not isinstance(feed.get("DATA"), list):
        raise ValueError("Official warning feed has no DATA array")

    audit = {"source_rows": len(feed["DATA"]), "outside_region_or_type": 0,
             "invalid_time": 0, "superseded": 0, "cancelled": 0, "stale": 0,
             "future": 0, "east_of_target": 0, "elapsed_window": 0}
    latest = {}
    for row in feed["DATA"]:
        if not isinstance(row, dict):
            raise ValueError("Malformed official warning record")
        area = str(row.get("AREA_CODE") or "")
        if area[:4] not in CITIES or row.get("CATEGORY_CNNAME") not in THUNDER_TYPES or str(row.get("ALERT_TYPE")) != "2":
            audit["outside_region_or_type"] += 1
            continue
        try:
            published = parse_time(row.get("PUBLISHDATE"))
        except (ValueError, TypeError):
            audit["invalid_time"] += 1
            continue
        if published > now:
            audit["future"] += 1
            continue
        key = (area, row["CATEGORY_CNNAME"])
        if key in latest:
            audit["superseded"] += 1
        # A newer cancellation supersedes the earlier signal in the same region.
        if key not in latest or published >= latest[key][0]:
            latest[key] = (published, row)
    for published, row in latest.values():
        if str(row.get("SEVERITY")) == "6" or "解除" in str(row.get("TITLE") or ""):
            audit["cancelled"] += 1
            continue
        if now - published > timedelta(hours=settings["max_warning_age_hours"]):
            audit["stale"] += 1
            continue
        candidate, reason = estimate_warning(row, settings, now)
        if reason:
            audit[reason] += 1
        else:
            result["candidates"].append(candidate)
    # Closest CITY first, then its newest active signal, not the newest province-wide.
    result["candidates"].sort(key=lambda item: (
        item["distance_km"], -parse_time(item["published_at"]).timestamp(), item["id"]
    ))
    result["audit"] = audit
    active_mode = settings["default_mode"] == "on" or (settings["default_mode"] == "auto" and 3 <= now.month <= 5)
    result["enabled"] = bool(result["candidates"]) and active_mode
    result["status"] = ("disabled" if settings["default_mode"] == "off" else
                        "outside_season" if not active_mode else
                        "estimated_risk" if result["candidates"] else "no_recent_candidate")
    # Do not publish actionable candidates while centrally disabled. This also
    # prevents older cached front-end code from reviving them with a local switch.
    audit["valid_candidates"] = len(result["candidates"])
    if not active_mode:
        result["candidates"] = []
    if result["candidates"]:
        primary = result["candidates"][0]
        result["valid_until"] = timestamp(min(parse_time(result["valid_until"]), parse_time(primary["expires_at"])))
        # Farther cities' later warnings must not reset/reopen the primary event.
        identity = f"{primary['id']}:{primary['published_at']}:{primary['source_longitude']}"
        identity += json.dumps(settings, sort_keys=True)
        result["event_id"] = hashlib.sha256(identity.encode()).hexdigest()[:20]
    return result


def fetch_thunder_alert(config, logger, now=None):
    now = (now or china_now()).astimezone(CHINA_TZ)
    try:
        settings = settings_from_config(config)
    except (ValueError, TypeError) as error:
        logger.log_error("thunder.settings", str(error))
        return {"enabled": False, "status": "source_error", "generated_at": timestamp(now),
                "settings": DEFAULT_SETTINGS.copy(), "candidates": [], "radar": {}}
    # Backend ON is allowed all year; OFF/auto outside season publish no candidates.
    try:
        feed = json.loads(_read_url(WARNING_URL))
        result = build_thunder_alert(feed, settings, now)
    except Exception as error:
        logger.log_error("thunder.warning_feed", str(error))
        return {
            "enabled": False, "status": "source_error", "generated_at": timestamp(now),
            "settings": settings, "candidates": [], "radar": {},
        }
    if result["candidates"]:
        try:
            result["radar"] = parse_radar_page(_read_url(RADAR_PAGE), now, settings["radar_max_age_minutes"])
        except Exception as error:
            logger.log_error("thunder.radar", str(error))
            result["radar"] = {"image": "", "status": "unavailable", "source_url": RADAR_PAGE}
    print("雷暴估测核验:", json.dumps(result, ensure_ascii=False))
    return result
