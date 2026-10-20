#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FR24 深圳宝安国际机场 (SZX/ZGSZ) 起降数据采集器 · GitHub Actions 版
====================================================================

原理
----
FlightRadar24 的机场看板把数据服务端渲染进 Inertia 数据岛：
    <div id="app" data-page="{...}">
其中含航班号、航司（彩绘会标注在括号里，如 `AirAsia (Legend Heroes Park Livery)`）、
机型、注册号、计划/预计时间、状态与起降地。直接 requests 会撞 Cloudflare，
所以这里用 Playwright 驱动 Chromium 打开真实页面，等挑战自动通过后再解析数据岛。

GitHub Actions 适配
-------------------
* 每次运行使用全新的浏览器上下文（不依赖本地 profile）；
* CI 使用完整 Chrome 与 xvfb 窗口环境，与本地 Chrome 使用相同浏览器引擎；
* 后续页通过官网分页链接加载，兼容 Inertia JSON 和整页 HTML 响应；
* 抓取失败不会覆盖上一次成功的数据，只更新 status.json，页面会提示“数据可能过期”。

输出
----
docs/data/latest.json          最新成功快照（GitHub Pages 直接读取）
docs/data/status.json          每次运行的运行状态（成功/失败、时间、错误）
data/history.json              历史累积（按 flight id 去重，保留 history_days 天）
data/livery_registry.json      自动学习到的“注册号 -> 彩绘涂装”对照表

用法
----
    python3 scraper.py                # 正常抓取（headless）
    python3 scraper.py --headed       # 有头模式（CI 里配合 xvfb-run）
    python3 scraper.py --debug        # 失败时保存页面截图到 data/debug-*.png
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import math
import os
import random
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urljoin, urlsplit

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "docs"
DATA_DIR = BASE_DIR / "data"
SITE_DATA_DIR = DOCS_DIR / "data"
CONFIG_PATH = BASE_DIR / "config.json"

LATEST_PATH = SITE_DATA_DIR / "latest.json"
STATUS_PATH = SITE_DATA_DIR / "status.json"
HISTORY_PATH = DATA_DIR / "history.json"
REGISTRY_PATH = DATA_DIR / "livery_registry.json"
PHOTO_CACHE_PATH = DATA_DIR / "photos.json"

TZ_CN = timezone(timedelta(hours=8))
LOG = logging.getLogger("fr24")

BOARDS = ("arrivals", "departures")

# ---------------------------------------------------------------------------
# 机型归一化：把 ICAO / IATA 各种写法映射到“家族”
# ---------------------------------------------------------------------------
TYPE_FAMILIES: dict[str, list[str]] = {
    "A318": ["A318", "318", "A19N"],
    "A319": ["A319", "319"],
    "A320": ["A320", "A20N", "32S", "32N", "320"],
    "A321": ["A321", "A21N", "32Q", "321"],
    "A330": ["A330", "A332", "A333", "A338", "A339", "330", "332", "333", "338", "339"],
    "A340": ["A340", "A342", "A343", "A345", "A346", "340", "342", "343", "345", "346"],
    "A350": ["A350", "A359", "A35K", "350", "359", "35K"],
    "A380": ["A380", "A388", "380", "388"],
    "B737": [
        "B737", "B738", "B739", "B736", "B735", "B734", "B733", "B732", "B731", "B73X",
        "738", "739", "736", "735", "734", "733", "732", "731",
        "73H", "73W", "73C", "73G", "73J", "73F", "73X", "73Y",
    ],
    "B737MAX": ["B38M", "B39M", "B37M", "7M8", "7M9", "38M", "39M", "37M"],
    "B747": [
        "B741", "B742", "B743", "B744", "B748", "B74F", "B74N",
        "741", "742", "743", "744", "748", "74F", "74N", "74X", "74Y", "74U", "74V",
        "B74X", "B74Y",
    ],
    "B757": ["B752", "B753", "B75F", "757", "752", "753", "75F"],
    "B767": ["B762", "B763", "B764", "B76F", "767", "763", "764", "762", "76F"],
    "B777": ["B772", "B773", "B77L", "B77W", "B77F", "777", "772", "773", "77L", "77W", "77F"],
    "B787": ["B787", "B788", "B789", "B78X", "787", "788", "789", "78X"],
    "MD11": ["MD11", "MD1F", "11F"],
    "C919": ["C919", "919"],
    "ARJ21": ["AJ27", "ARJ21", "AJ21", "ARJ"],
    "A220": ["BCS1", "BCS3", "A220", "221", "223", "CS1", "CS3"],
    "E-Jet": [
        "E170", "E175", "E190", "E195", "E75L", "E75S", "E290", "E295",
        "170", "175", "190", "195", "290", "295",
    ],
    "CRJ": ["CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX", "CR2", "CR7", "CR9"],
    "Q400": ["DH8D", "Q400", "DH8"],
    "ATR": ["AT72", "AT75", "AT76", "ATR"],
    "AN124": ["AN124", "A124", "AN12"],
    "IL96": ["IL96", "IL76"],
    "B717": ["B712", "B717", "717"],
}

CODE_TO_FAMILY: dict[str, str] = {}
for _fam, _codes in TYPE_FAMILIES.items():
    for _c in _codes:
        CODE_TO_FAMILY.setdefault(_c.upper(), _fam)

FREIGHTER_FAMILIES = {"B747", "B757", "B767", "B777", "MD11", "AN124"}

# 公务机（ICAO 机型代码）。可在 config.json 的 bizjet_types 里追加。
DEFAULT_BIZJET_TYPES = {
    "GLF2", "GLF3", "GLF4", "GLF5", "GLF6", "GL7T", "GL5T", "GL6T", "G150", "G280", "GALX", "ASTR",
    "CL30", "CL35", "CL60", "CL64", "CL65",
    "C25A", "C25B", "C25C", "C25M", "C510", "C525", "C550", "C560", "C56X",
    "C650", "C680", "C68A", "C700", "C750",
    "E50P", "E55P", "E545", "E550", "E35L",
    "FA7X", "FA8X", "F900", "F2TH", "F1EX",
    "H25A", "H25B", "H25C", "HA4T",
    "LJ31", "LJ35", "LJ45", "LJ55", "LJ60", "LJ75",
    "BE40", "BE20", "BE30", "BE9L", "B350",
    "PC12", "PC24", "TBM7", "TBM8", "TBM9", "P180", "SF50", "HDJT", "EA50", "WW24",
}

_HEAVY_FAMILIES = {"B747", "A340", "A380"}

STATUS_MAP: dict[str, tuple[str, str]] = {
    "scheduled": ("计划", "muted"),
    "estimated": ("预计", "info"),
    "expected": ("预计", "info"),
    "delayed": ("延误", "warn"),
    "landed": ("已落地", "ok"),
    "arrived": ("已落地", "ok"),
    "departed": ("已起飞", "ok"),
    "en-route": ("飞行中", "info"),
    "enroute": ("飞行中", "info"),
    "boarding": ("登机中", "info"),
    "canceled": ("取消", "bad"),
    "cancelled": ("取消", "bad"),
    "diverted": ("备降", "bad"),
    "unknown": ("未知", "muted"),
}

PAREN_RE = re.compile(r"^(?P<base>.+?)\s*\((?P<extra>[^()]+)\)\s*$")


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def now_ts() -> int:
    return int(time.time())


def ts_iso(ts: int | float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(int(ts), TZ_CN).isoformat()


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def get_airports(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    airports = cfg.get("airports")
    if airports:
        return airports
    return [{
        "iata": cfg.get("airport_iata", "SZX"),
        "icao": cfg.get("airport_icao", "ZGSZ"),
        "name": cfg.get("airport_name", "Shenzhen Bao'an International Airport"),
        "city": cfg.get("airport_city", "Shenzhen"),
    }]


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)


def bizjet_set(cfg: dict[str, Any] | None = None) -> set[str]:
    types = set(DEFAULT_BIZJET_TYPES)
    if cfg:
        types |= {str(x).upper().strip() for x in (cfg.get("bizjet_types") or [])}
    return types


def family_of(code: str | None, cfg: dict[str, Any] | None = None) -> str:
    if not code:
        return "未知"
    c = str(code).upper().strip()
    if not c:
        return "未知"
    if c in bizjet_set(cfg):
        return "公务机"
    if c in CODE_TO_FAMILY:
        return CODE_TO_FAMILY[c]
    for prefix, fam in (
        ("A33", "A330"), ("A34", "A340"), ("A35", "A350"), ("A38", "A380"),
        ("A31", "A319"), ("A32", "A320"),
        ("B74", "B747"), ("B75", "B757"), ("B76", "B767"),
        ("B77", "B777"), ("B78", "B787"), ("B73", "B737"), ("B71", "B717"),
    ):
        if c.startswith(prefix):
            return fam
    return "其他"


def parse_airline(name: str | None) -> tuple[str, str | None]:
    """拆分航司名与 FR24 标注的彩绘。"""
    name = (name or "").strip()
    m = PAREN_RE.match(name)
    if m:
        base, extra = m.group("base").strip(), m.group("extra").strip()
        if base and extra:
            return base, extra
    return name, None


def looks_like_livery(extra: str, keywords: list[str]) -> bool:
    low = extra.lower()
    return any(k in low for k in keywords)


NON_AIRLINE_NAMES = {"private owner", "private", "private jet", "unknown", "none"}


def is_foreign_airline(name: str | None, iata: str | None, cfg: dict[str, Any]) -> bool:
    """是否为外航：不在中国大陆航司名单内（名单可通过 config.json 扩展）。"""
    base = (name or "").strip()
    if not base:
        return False
    low = base.lower()
    if low in NON_AIRLINE_NAMES:
        return False
    cn_names = {str(x).strip().lower() for x in (cfg.get("mainland_airlines") or [])}
    if low in cn_names:
        return False
    codes = {str(x).strip().upper() for x in (cfg.get("mainland_airline_codes") or [])}
    if iata and str(iata).strip().upper() in codes:
        return False
    return True


# ---------------------------------------------------------------------------
# 单条航班解析
# ---------------------------------------------------------------------------
def build_flight(
    raw: dict[str, Any],
    board: str,
    cfg: dict[str, Any],
    manual: dict[str, str],
    learned: dict[str, Any],
) -> dict[str, Any] | None:
    fid = str(raw.get("id") or "").strip()
    fnum = (raw.get("flightNumber") or "").strip().upper()
    if not fid or not fnum:
        return None

    ac = raw.get("aircraft") or {}
    al = raw.get("airline") or {}
    ep = raw.get("endpoint") or {}
    st = raw.get("status") or {}

    reg = (ac.get("registration") or "").strip().upper() or None
    type_code = (ac.get("type") or "").strip().upper() or None
    family = family_of(type_code, cfg)

    airline_raw = (al.get("name") or "").strip()
    airline, livery_label = parse_airline(airline_raw)

    livery: str | None = None
    livery_source: str | None = None
    if livery_label and looks_like_livery(livery_label, cfg.get("livery_keywords", [])):
        livery, livery_source = livery_label, "fr24"
    elif reg and reg in manual:
        livery, livery_source = manual[reg], "manual"
    elif reg and reg in learned:
        item = learned[reg]
        livery = item.get("livery") if isinstance(item, dict) else str(item)
        livery_source = "learned"

    widebody = family in set(cfg.get("widebody_families", []))
    rare = family in set(cfg.get("rare_families", []))
    bizjet = family == "公务机"
    four_engine = family in set(
        cfg.get("four_engine_families") or {"A340", "A380", "B747", "IL96", "AN124"}
    )
    heavies = family in set(cfg.get("heavy_rare_families") or _HEAVY_FAMILIES)
    foreign = (not bizjet) and is_foreign_airline(airline, al.get("iata"), cfg)
    cargo_names = [c.lower() for c in cfg.get("cargo_airlines", [])]
    # 货机：机型代码以 F 结尾（73F/74F/77F…），或属于纯货运航司
    is_cargo = (type_code or "").endswith("F") or any(
        c in airline_raw.lower() for c in cargo_names
    )
    # 特殊机型只保留：四发机 + 货机 + 公务机（不再包含所有宽体机）
    special_type = bool(four_engine or is_cargo or bizjet)

    status_name = str(st.get("name") or "unknown").lower()
    status_cn, status_kind = STATUS_MAP.get(status_name, (status_name, "muted"))

    sched = raw.get("scheduledTime")
    est = raw.get("estimatedTime")
    delay_min = None
    try:
        if sched and est:
            delay_min = int(round((int(est) - int(sched)) / 60))
    except (TypeError, ValueError):
        delay_min = None

    return {
        "id": fid,
        "board": board,
        "flight_number": fnum,
        "callsign": (raw.get("callsign") or "").strip().upper() or None,
        "flight_id": raw.get("flightId"),
        "airline": airline,
        "airline_raw": airline_raw,
        "airline_iata": (al.get("iata") or "").strip().upper() or None,
        "livery": livery,
        "is_special_livery": bool(livery),
        "livery_source": livery_source,
        "type": type_code,
        "type_family": family,
        "is_widebody": widebody,
        "is_rare": rare,
        "is_bizjet": bizjet,
        "is_four_engine": four_engine,
        "is_foreign": foreign,
        "is_heavies": heavies,
        "is_cargo": is_cargo,
        "is_special_type": special_type,
        "registration": reg,
        "endpoint": {
            "iata": ep.get("iata"),
            "icao": ep.get("icao"),
            "city": ep.get("city"),
            "name": ep.get("name"),
            "country": ep.get("countryName"),
        },
        "scheduled_ts": int(sched) if sched else None,
        "estimated_ts": int(est) if est else None,
        "scheduled_iso": ts_iso(sched),
        "estimated_iso": ts_iso(est),
        "delay_min": delay_min,
        "status": status_name,
        "status_cn": status_cn,
        "status_kind": status_kind,
        "gate": raw.get("gate"),
        "runway": raw.get("runway"),
        "last_seen_ts": now_ts(),
    }




# ---------------------------------------------------------------------------
# 浏览器抓取
# ---------------------------------------------------------------------------
def _browser_args() -> list[str]:
    return [
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--window-size=1440,1000",
    ]


def _title_safe(page) -> str:
    try:
        return (page.title() or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _is_challenge_title(title: str) -> bool:
    low = title.lower()
    return "just a moment" in low or "attention required" in low


class SourceAccessError(RuntimeError):
    """Explicit source access refusal: report it instead of repeated challenges."""


class AirportFlights(list):
    """Parsed flights plus board diagnostics; never turn an exception into empty success."""
    def __init__(self, items=(), *, errors=None, boards=None):
        super().__init__(items)
        self.errors = dict(errors or {})
        self.boards = dict(boards or {})


class BoardPages(list):
    """Successful pages survive a later page failing; keep that warning too."""
    def __init__(self, items=()):
        super().__init__(items)
        self.warning = None
        self.coverage = {}


class _DataIslandParser(HTMLParser):
    """Read the response's actual data, not the initial DOM's stale data-page."""
    raw = None

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "app" and attrs.get("data-page"):
            self.raw = attrs["data-page"]
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])


def _decode_island(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(html.unescape(raw))


def _validate_board(data, airport):
    props = data.get("props") if isinstance(data, dict) else None
    if not isinstance(props, dict) or not isinstance(props.get("flights"), list):
        raise RuntimeError("数据岛缺少 flights 列表；页面字段可能变化")
    got = ((props.get("airport") or {}).get("iata") or "").upper()
    if got and got != airport["iata"].upper():
        raise RuntimeError(f"机场不匹配：{got}")
    return data


def _response_board(response, airport):
    """Read the actual response before frontend hydration can stall a tab."""
    if response.status in (401, 403, 429):
        raise SourceAccessError(f"源站拒绝访问 HTTP {response.status}；不重试访问验证")
    if response.status >= 400:
        raise RuntimeError(f"源站返回 HTTP {response.status}")
    body = response.text()
    if "application/json" in response.headers.get("content-type", "").lower():
        return _validate_board(json.loads(body), airport)
    parser = _DataIslandParser()
    parser.feed(body)
    if not parser.raw:
        title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
        title = html.unescape(title.group(1)).strip() if title else "空"
        error_type = SourceAccessError if _is_challenge_title(title) else RuntimeError
        raise error_type(f"服务器响应未包含航班数据岛（标题：{title}）")
    data = _validate_board(_decode_island(parser.raw), airport)
    # These are links observed in the server response, not guessed endpoints.
    data["_pagination_links"] = parser.links
    return data


def _debug_screenshot(page, airport, label, debug):
    if not debug:
        return
    shot = DATA_DIR / f"debug-{airport['iata'].lower()}-{label}.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(shot), full_page=False)
        LOG.warning("已保存截图：%s", shot)
    except Exception:  # noqa: BLE001
        pass


def capture_error(flights) -> str:
    labels = {"arrivals": "到达", "departures": "出发", "browser": "浏览器"}
    errors = getattr(flights, "errors", {})
    return "；".join(f"{labels.get(key, key)}：{str(value)[:600]}" for key, value in errors.items())


def _wait_for_island(page, timeout: float) -> str | None:
    """轮询等待 #app[data-page]，期间让 Cloudflare 挑战自行完成。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            raw = page.get_attribute("#app", "data-page", timeout=1500)
        except Exception:  # noqa: BLE001
            raw = None
        if raw and raw.strip():
            return raw
        page.wait_for_timeout(600)
    return None


def fetch_board(
    page,
    board: str,
    airport: dict[str, Any],
    cfg: dict[str, Any],
    debug: bool,
    url: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    iata = airport["iata"].lower()
    if not url:
        url = f"https://www.flightradar24.com/data/airports/{iata}/{board}"
    tag = label or board
    attempts = int(cfg.get("max_retries", 3))
    last_err: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            LOG.info("[%s] 第 %d/%d 次打开 %s", tag, attempt, attempts, url)
            response = page.goto(url, timeout=75_000, wait_until="domcontentloaded")
            status = response.status if response is not None else None
            if status in (401, 403, 429):
                _debug_screenshot(page, airport, f"{board}-{attempt}", debug)
                raise SourceAccessError(f"源站拒绝访问 HTTP {status}（标题：{_title_safe(page) or '空'}）；停止重试，请核对源站访问权限或限流")
            if status is not None and status >= 400:
                raise RuntimeError(f"源站返回 HTTP {status}：{url}")
            page.wait_for_timeout(random.randint(900, 2200))

            # Prefer server-rendered data and preserve its real pagination
            # links. Avoid relying on a DOM that FR24 may already be replacing.
            if response is not None:
                try:
                    data = _response_board(response, airport)
                    LOG.info("[%s] 服务器响应成功：%d 条航班", tag, len(data["props"]["flights"]))
                    return data
                except SourceAccessError:
                    raise
                except (RuntimeError, ValueError, TypeError):
                    pass  # A legitimate client-rendered page can still fill the DOM below.

            raw = _wait_for_island(page, timeout=70)
            if not raw:
                title = _title_safe(page)
                _debug_screenshot(page, airport, f"{board}-{attempt}", debug)
                error_type = SourceAccessError if _is_challenge_title(title) else RuntimeError
                raise error_type(
                    f"未取得数据岛（标题：{title or '空'}；"
                    f"{'源站显示访问验证，停止重试' if _is_challenge_title(title) else '页面结构可能变化，需检查截图与选择器'}）"
                )

            data = _validate_board(_decode_island(raw), airport)
            props = data["props"]
            LOG.info("[%s] 成功：%d 条航班", tag, len(props["flights"]))
            return data
        except SourceAccessError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            LOG.warning("[%s] 第 %d 次失败：%s", tag, attempt, exc)
            page.wait_for_timeout(3000 + attempt * 2500 + random.randint(0, 1500))

    raise RuntimeError(f"{tag} 抓取失败：{last_err}")


def _launch_browser(pw, headless: bool, proxy: str | None, channel: str | None):
    """优先按指定 channel 启动，失败则回退到 Playwright 自带 Chromium。"""
    attempts = [channel, None] if channel else [None]
    last_err: Exception | None = None
    for ch in attempts:
        try:
            b = pw.chromium.launch(
                headless=headless,
                channel=ch,
                chromium_sandbox=False,
                proxy={"server": proxy} if proxy else None,
                args=_browser_args(),
            )
            if ch:
                LOG.info("浏览器：系统 Chrome（channel=%s）", ch)
            else:
                LOG.info("浏览器：Playwright Chromium")
            return b
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if ch:
                if os.environ.get("GITHUB_ACTIONS"):
                    raise RuntimeError(f"CI 指定的 {ch} 无法启动，拒绝静默降级为不同浏览器：{exc}") from exc
                LOG.warning("channel=%s 启动失败，回退到 Playwright Chromium：%s", ch, exc)
    raise RuntimeError(f"无法启动浏览器：{last_err}")


def fetch_next_board(page, board, airport, cfg, debug, previous):
    """Follow the real Later flights link in the current browser session.

    Let the site's own client set its navigation headers. Never synthesize
    an API, copy credentials, or replay a blocked request through another host.
    """
    if airport["iata"].upper() == "SZX" and board == "arrivals":
        return fetch_next_document(page, board, airport, cfg, debug, previous)
    meta = previous["props"].get("meta") or {}
    next_page = str(meta.get("nextPage") or "")
    expected_path = f"/data/airports/{airport['iata'].lower()}/{board}"
    # Allow the frontend to render the next link after an Inertia response.
    deadline = time.monotonic() + 8
    target = None
    while time.monotonic() < deadline:
        links = page.locator("a[href]").evaluate_all(
            "es => es.filter(e => e.getClientRects().length).map(e => e.getAttribute('href'))"
        )
        for href in links:
            parsed = urlsplit(urljoin(page.url, href))
            if (parsed.scheme == "https" and parsed.hostname == "www.flightradar24.com"
                    and parsed.path.rstrip("/") == expected_path
                    and parse_qs(parsed.query).get("page") == [next_page]):
                target = (href, parsed)
                break
        if target:
            break
        page.wait_for_timeout(250)
    if not target:
        raise RuntimeError(f"找不到官网第 {next_page} 页的可见分页链接；停止猜测分页 URL")
    href, target_url = target
    target_query = parse_qs(target_url.query)

    def is_target(response):
        candidate = urlsplit(response.url)
        query = parse_qs(candidate.query)
        return (candidate.scheme == target_url.scheme and candidate.netloc == target_url.netloc
                and candidate.path == target_url.path and query == target_query
                and response.request.resource_type in ("document", "xhr", "fetch")
                and not 300 <= response.status < 400)

    # Space normal page interactions; do not hammer the server with reloads.
    page.wait_for_timeout(max(0, min(15000, int(cfg.get("pagination_delay_ms", 2500)))))
    LOG.info("[%s %s p%s] 键盘激活官网分页链接 %s", airport["iata"], board, next_page, href)
    try:
        with page.expect_response(is_target, timeout=45000) as captured:
            # A long arrivals board can reflow while scrolling or have a
            # sticky banner over its footer. Native Enter activates the same
            # anchor/website handler without pointer hit-testing and scroll
            # stability waits. Response waiting belongs to expect_response,
            # not to the interaction's separate 12-second timeout.
            page.locator(f"a[href={json.dumps(href)}]:visible").first.press(
                "Enter", timeout=12000, no_wait_after=True
            )
        response = captured.value
        LOG.info("[%s %s p%s] 分页响应 HTTP %s（%s）", airport["iata"], board,
                 next_page, response.status, response.request.resource_type)
        if response.status in (401, 403, 429):
            raise SourceAccessError(f"官网第 {next_page} 页返回 HTTP {response.status}；源站拒绝当前会话访问")
        if response.status >= 400:
            raise RuntimeError(f"官网第 {next_page} 页返回 HTTP {response.status}")
        body = response.text()
        if "application/json" in response.headers.get("content-type", "").lower():
            data = json.loads(body)
        else:
            parser = _DataIslandParser()
            parser.feed(body)
            if not parser.raw:
                title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
                title = html.unescape(title.group(1)).strip() if title else _title_safe(page)
                error_type = SourceAccessError if _is_challenge_title(title) else RuntimeError
                raise error_type(f"官网第 {next_page} 页未返回航班数据（标题：{title or '空'}）")
            data = _decode_island(parser.raw)
        # Require flights in THIS response, never reuse the previous page's
        # flights as a successful result of an incomplete/error response.
        data = _validate_board(data, airport)
        if "airport" not in data["props"] and previous["props"].get("airport"):
            data["props"]["airport"] = previous["props"]["airport"]
        current = data["props"]["flights"]
        if current and current == previous["props"]["flights"]:
            raise RuntimeError(f"第 {next_page} 页返回了与前页相同的航班；不计为翻页成功")
        LOG.info("[%s %s p%s] 官网分页成功：%d 条", airport["iata"], board, next_page, len(current))
        return data
    except Exception:
        _debug_screenshot(page, airport, f"{board}-page-{next_page}", debug)
        raise


def fetch_next_document(page, board, airport, cfg, debug, previous):
    """SZX arrivals: isolated browser document, no click/focus/hydration wait.

    Still uses the same browser context/cookies and the site's observed link.
    A source refusal is reported, never retried via a different identity.
    """
    next_page = str((previous["props"].get("meta") or {}).get("nextPage") or "")
    expected_path = f"/data/airports/{airport['iata'].lower()}/{board}"
    links = previous.get("_pagination_links")
    if links is None:
        links = page.locator("a[href]").evaluate_all("es => es.map(e => e.getAttribute('href'))")
    target = None
    for href in links:
        parsed = urlsplit(urljoin(page.url, href))
        if (parsed.scheme == "https" and parsed.hostname == "www.flightradar24.com"
                and parsed.path.rstrip("/") == expected_path
                and parse_qs(parsed.query).get("page") == [next_page]):
            target = parsed.geturl()
            break
    if not target:
        raise RuntimeError(f"服务器响应没有第 {next_page} 页的官网链接，停止猜测 URL")
    page.wait_for_timeout(max(0, min(15000, int(cfg.get("pagination_delay_ms", 2500)))))
    document = page.context.new_page()
    try:
        LOG.info("[%s %s p%s] 独立标签读取官网 HTML：%s", airport["iata"], board, next_page, target)
        # commit waits for HTTP response headers, not completion of the
        # scripts that made both click() and press() hang in production.
        response = document.goto(target, referer=page.url, wait_until="commit", timeout=45000)
        if response is None:
            raise RuntimeError("分页没有返回 HTTP 响应")
        data = _response_board(response, airport)
        if data["props"]["flights"] and data["props"]["flights"] == previous["props"]["flights"]:
            raise RuntimeError(f"第 {next_page} 页重复返回上一页数据")
        LOG.info("[%s %s p%s] 官网 HTML 分页成功：%d 条", airport["iata"], board,
                 next_page, len(data["props"]["flights"]))
        return data
    except Exception:
        # Avoid renderer-dependent screenshots in the very path introduced
        # to recover from a stuck renderer; the HTTP error remains in status.
        LOG.exception("[%s %s p%s] HTML 分页失败", airport["iata"], board, next_page)
        raise
    finally:
        try:
            document.close()
        except Exception as exc:  # noqa: BLE001
            LOG.warning("关闭分页标签失败：%s", exc)


def _board_time(value):
    """A missing/bad timestamp must never certify a page as tomorrow-only."""
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number > 0 else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def fetch_board_pages(
    page,
    board: str,
    airport: dict[str, Any],
    cfg: dict[str, Any],
    debug: bool,
    today_end: int | None = None,
) -> list[dict[str, Any]]:
    """Read real pagination until a confirmed day boundary or source exhaustion.

    One far-future outlier is not the end of the board. Require TWO complete
    consecutive pages whose *every* scheduled and effective time is next-day.
    A mixed/invalid page resets that confirmation. This deliberately reads
    beyond midnight once, rather than trusting the maximum timestamp.
    """
    max_pages = max(1, int(cfg.get("pages_per_board", 40)))
    pages = BoardPages()
    pages.coverage = {"target_end": today_end, "coverage_complete": False,
                      "boundary_confirmed": False, "completion_reason": None,
                      "raw_flights": 0, "scheduled_from": None, "scheduled_to": None}
    signatures, cursors = set(), set()
    beyond_pages = 0
    data = fetch_board(page, board, airport, cfg, debug)
    while True:
        props = data.get("props") or {}
        raw = props.get("flights") or []
        meta = props.get("meta") or {}
        # Also catch cycles longer than two pages; never count repeated data
        # as the second all-tomorrow confirmation page.
        if raw:
            signature = tuple(sorted((str(f.get("id") or ""), str(f.get("scheduledTime") or "")) for f in raw))
            if signature in signatures:
                pages.warning = "分页重复返回已读取的数据；未确认当日覆盖完整"
                pages.coverage["completion_reason"] = "repeated_data"
                break
            signatures.add(signature)
        pages.append(data)
        scheduled = [_board_time(f.get("scheduledTime")) for f in raw]
        effective = [_board_time(f.get("estimatedTime")) or t for f, t in zip(raw, scheduled)]
        valid = [t for t in scheduled if t]
        pages.coverage["raw_flights"] += len(raw)
        if valid:
            pages.coverage["scheduled_from"] = min(valid + [pages.coverage["scheduled_from"] or min(valid)])
            pages.coverage["scheduled_to"] = max(valid + [pages.coverage["scheduled_to"] or max(valid)])
        entirely_next_day = bool(today_end and raw and all(t >= today_end for t in scheduled + effective))
        beyond_pages = beyond_pages + 1 if entirely_next_day else 0
        LOG.info("[%s %s] 第 %d 页：%d 条，计划范围 %s–%s，连续整页跨日 %d/2",
                 airport["iata"], board, len(pages), len(raw),
                 ts_iso(min(valid)) if valid else "未知", ts_iso(max(valid)) if valid else "未知", beyond_pages)
        if beyond_pages >= 2:
            pages.coverage.update(coverage_complete=True, boundary_confirmed=True,
                                  completion_reason="next_day_confirmed")
            break
        if meta.get("hasMoreNextData") is False:
            # Source exhaustion certifies only the AVAILABLE board, not an
            # invented last flight at 23:59 or an unseen subscription window.
            pages.coverage.update(coverage_complete=True, completion_reason="source_exhausted")
            break
        if not raw:
            pages.warning = "返回空页但源站未明确分页结束；未确认当日覆盖完整"
            pages.coverage["completion_reason"] = "unexpected_empty_page"
            break
        if not meta.get("hasMoreNextData") or not meta.get("nextPage"):
            pages.warning = "缺少明确的后续分页 / 结束信息；未确认当日覆盖完整"
            pages.coverage["completion_reason"] = "missing_pagination"
            break
        if len(pages) >= max_pages:
            pages.warning = f"已达 {max_pages} 页安全上限，源站仍有后续数据；未确认当日覆盖完整"
            pages.coverage["completion_reason"] = "page_limit"
            break
        cursor = (str(meta.get("date") or ""), str(meta["nextPage"]))
        if cursor in cursors:
            pages.warning = "源站重复返回相同的下一页位置；未确认当日覆盖完整"
            pages.coverage["completion_reason"] = "repeated_cursor"
            break
        cursors.add(cursor)
        try:
            data = fetch_next_board(page, board, airport, cfg, debug, pages[-1])
        except Exception as exc:  # noqa: BLE001
            pages.warning = f"第 {len(pages)+1} 页未更新：{str(exc)[:1000]}"
            pages.coverage["completion_reason"] = "page_failed"
            break
    LOG.info("[%s %s] 停止分页：%s；整页跨日确认=%s；%s", airport["iata"], board,
             pages.coverage["completion_reason"], pages.coverage["boundary_confirmed"], pages.warning or "已读完目标或源站可用数据")
    return pages


def collect_airport(
    page,
    cfg: dict[str, Any],
    airport: dict[str, Any],
    manual: dict[str, str],
    learned: dict[str, Any],
    debug: bool,
) -> tuple[list[dict[str, Any]], int | None]:
    flights = AirportFlights()
    window_hours: int | None = None
    today_end = day_window(now_ts())[2]

    for board in BOARDS:
        try:
            pages = fetch_board_pages(page, board, airport, cfg, debug, today_end=today_end)
        except Exception as exc:  # noqa: BLE001
            # Arrivals and departures are independent. Do not throw away a
            # valid arrivals board when departures fails, or skip departures
            # just because arrivals was unavailable.
            flights.errors[board] = str(exc)[:1200]
            flights.boards[board] = {"ok": False, "error": str(exc)[:1200]}
            LOG.error("[%s %s] 看板失败，继续检查另一方向：%s", airport["iata"], board, exc)
            continue
        before_count = len(flights)
        LOG.info("[%s %s] 共抓取 %d 页", airport["iata"], board, len(pages))
        for data in pages:
            props = data.get("props") or {}
            meta = props.get("meta") or {}
            if meta.get("hoursRange"):
                window_hours = meta["hoursRange"]
            for raw in props.get("flights") or []:
                item = build_flight(raw, board, cfg, manual, learned)
                if item:
                    flights.append(item)
        warning = getattr(pages, "warning", None)
        flights.boards[board] = {"ok": True, "pages": len(pages), "parsed_flights": len(flights)-before_count,
                                 "partial": bool(warning), **getattr(pages, "coverage", {})}
        if warning:
            flights.errors[board] = warning
            flights.boards[board]["error"] = warning

    deduped: dict[tuple, dict] = {}
    for f in flights:
        key = (f.get("board"), f.get("flight_number"), f.get("scheduled_ts"))
        deduped.setdefault(key, f)
    if len(deduped) != len(flights):
        LOG.info("[%s] 分页去重：%d → %d", airport["iata"], len(flights), len(deduped))
    flights[:] = deduped.values()

    for f in flights:
        if f["is_special_livery"] and f["livery_source"] == "fr24" and f["registration"]:
            entry = learned.get(f["registration"])
            if not isinstance(entry, dict):
                entry = {"first_seen": now_ts()}
            entry["livery"] = f["livery"]
            entry["airline"] = f["airline"]
            entry["last_seen"] = now_ts()
            learned[f["registration"]] = entry

    return flights, window_hours


def collect_all(
    cfg: dict[str, Any], headless: bool, debug: bool
) -> dict[str, tuple[list[dict[str, Any]], int | None]]:
    """一次启动浏览器，依次抓取所有机场（复用 cookie / cf_clearance）。"""
    from playwright.sync_api import sync_playwright

    manual = {str(k).upper(): str(v) for k, v in (cfg.get("manual_liveries") or {}).items()}
    learned: dict[str, Any] = read_json(REGISTRY_PATH, {})
    if not isinstance(learned, dict):
        learned = {}

    proxy = (os.environ.get("PROXY_URL") or "").strip() or None
    if proxy:
        LOG.info("使用代理：%s", re.sub(r"//[^@]*@", "//***@", proxy))

    results: dict[str, tuple[list[dict[str, Any]], int | None]] = {}
    with sync_playwright() as pw:
        channel = (os.environ.get("PLAYWRIGHT_CHANNEL") or "").strip() or None
        browser = _launch_browser(pw, headless, proxy, channel)
        ctx = browser.new_context(
            locale="en-US",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1440, "height": 1000},
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"},
        )
        LOG.info("浏览器版本：%s；运行模式：%s", browser.version, "headless" if headless else "headed")
        try:
            page = ctx.new_page()
            page.set_default_timeout(30_000)
            for airport in get_airports(cfg):
                iata = airport["iata"]
                LOG.info("===== 开始 %s %s =====", iata, airport.get("name", ""))
                try:
                    results[iata] = collect_airport(
                        page, cfg, airport, manual, learned, debug
                    )
                except Exception as exc:  # noqa: BLE001
                    LOG.error("[%s] 采集失败：%s", iata, exc)
                    results[iata] = (AirportFlights(errors={"browser": str(exc)[:1200]}), None)
        finally:
            ctx.close()
            browser.close()

    write_json(REGISTRY_PATH, learned)
    return results


# ---------------------------------------------------------------------------
# 机型照片（PlaneSpotters 公共 API，按注册号查询并缓存）
# ---------------------------------------------------------------------------
DISPLAY_KEYS = ("is_special_livery", "is_foreign", "is_widebody", "is_four_engine", "is_cargo", "is_bizjet")


def is_displayed(f: dict[str, Any]) -> bool:
    """页面展示：彩绘 / 外航 / 宽体 / 四发 / 货机 / 公务机，含普通国内宽体客机。"""
    return any(bool(f.get(k)) for k in DISPLAY_KEYS)


def _fetch_photo_once(reg: str, user_agent: str) -> dict[str, Any] | None:
    url = f"https://api.planespotters.net/pub/photos/reg/{quote(reg)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        payload = json.loads(resp.read().decode("utf-8", "replace"))
    photos = payload.get("photos") or []
    if not photos:
        return None
    p = photos[0]
    large = p.get("thumbnail_large") or p.get("thumbnail") or {}
    src = large.get("src")
    if not src:
        return None
    size = large.get("size") or {}
    return {
        "src": src,
        "link": p.get("link"),
        "photographer": p.get("photographer"),
        "width": size.get("width"),
        "height": size.get("height"),
        "source": "planespotters",
    }


def attach_photos(flights: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
    opts = cfg.get("photos") or {}
    if not opts.get("enabled", True):
        LOG.info("照片：已在配置中关闭")
        for f in flights:
            f.setdefault("photo", None)
        return

    user_agent = (opts.get("user_agent") or "").strip() or (
        "SZXLiveryRadar/1.0 (+https://github.com/)"
    )
    cache = read_json(PHOTO_CACHE_PATH, {})
    if not isinstance(cache, dict):
        cache = {}

    now = now_ts()
    ttl = int(opts.get("cache_days", 30)) * 86400
    none_ttl = int(opts.get("none_cache_days", 7)) * 86400
    budget = int(opts.get("max_per_run", 60))
    delay = float(opts.get("delay_sec", 0.35))

    displayed = [f for f in flights if is_displayed(f)]
    regs: list[str] = []
    for f in displayed:
        reg = (f.get("registration") or "").upper()
        if reg and reg not in regs:
            regs.append(reg)

    fetched = 0
    for reg in regs:
        entry = cache.get(reg)
        fresh = False
        if isinstance(entry, dict):
            age = now - int(entry.get("updated_at") or 0)
            fresh = age < (none_ttl if entry.get("none") else ttl)
        if not fresh and budget > 0:
            try:
                photo = _fetch_photo_once(reg, user_agent)
                cache[reg] = {"photo": photo, "none": photo is None, "updated_at": now}
            except Exception as exc:  # noqa: BLE001
                LOG.warning("照片 %s 获取失败（下次重试）：%s", reg, exc)
            else:
                fetched += 1
            budget -= 1
            time.sleep(delay)

        entry = cache.get(reg) or {}
        photo = entry.get("photo") if isinstance(entry, dict) else None
        if photo:
            photo = dict(photo, reg=reg)
        for f in displayed:
            if (f.get("registration") or "").upper() == reg:
                f["photo"] = photo

    for f in flights:
        f.setdefault("photo", None)

    got = sum(1 for f in displayed if f.get("photo"))
    LOG.info(
        "照片：覆盖 %d/%d（本次新查 %d 个注册号，缓存 %d）",
        got, len(displayed), fetched, max(0, len(regs) - fetched),
    )
    write_json(PHOTO_CACHE_PATH, cache)


# ---------------------------------------------------------------------------
# 汇总与落盘
# ---------------------------------------------------------------------------
def stats_of(items: list[dict[str, Any]]) -> dict[str, int]:
    def is_special_type(x):
        return bool(x.get("is_four_engine") or x.get("is_cargo") or x.get("is_bizjet"))

    def is_livery_foreign(x):
        return bool(x.get("is_special_livery") or x.get("is_foreign"))

    return {
        "total": len(items),
        "arrivals": sum(1 for x in items if x["board"] == "arrivals"),
        "departures": sum(1 for x in items if x["board"] == "departures"),
        "livery": sum(1 for x in items if x["is_special_livery"]),
        "foreign": sum(1 for x in items if x.get("is_foreign")),
        "four_engine": sum(1 for x in items if x.get("is_four_engine")),
        "cargo": sum(1 for x in items if x["is_cargo"]),
        "bizjet": sum(1 for x in items if x.get("is_bizjet")),
        "widebody": sum(1 for x in items if x["is_widebody"]),
        "rare": sum(1 for x in items if x["is_rare"]),
        "heavies": sum(1 for x in items if x.get("is_heavies")),
        "livery_foreign": sum(1 for x in items if is_livery_foreign(x)),
        "special_type": sum(1 for x in items if is_special_type(x)),
        # 页面实际展示的航班数
        "special": sum(1 for x in items if is_displayed(x)),
    }


def flight_event_time(flight):
    """Use the latest known operation time, not when a record was re-fetched."""
    for key in ("estimated_ts", "scheduled_ts"):
        try:
            value = int(flight.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def day_window(timestamp):
    local = datetime.fromtimestamp(timestamp, TZ_CN)
    start = int(local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    return local.date().isoformat(), start, start+86400


def rollover_airport(airport, timestamp):
    """Reset yesterday's accumulated records on the first run of a new CN day.

    Also runs before collection: a failed first capture must not carry an
    ever-growing previous day's cache or republish yesterday as today's data.
    """
    day, start, end = day_window(timestamp)
    history_path = DATA_DIR / f"history_{airport['iata'].lower()}.json"
    history = read_json(history_path, {})
    if not isinstance(history, dict):
        history = {}
    old = history.get("flights") or {}
    if not isinstance(old, dict) or (history.get("service_day") and history["service_day"] != day):
        old = {}
    flights = {key: f for key, f in old.items()
               if isinstance(f, dict) and start <= flight_event_time(f) < end}
    if history.get("service_day") != day or flights != history.get("flights"):
        history = {"service_day": day, "updated_at": timestamp, "updated_at_iso": ts_iso(timestamp), "flights": flights}
        write_json(history_path, history)
    snapshot_path = SITE_DATA_DIR / f"{airport['iata'].lower()}.json"
    snapshot = read_json(snapshot_path, {})
    if isinstance(snapshot, dict) and snapshot.get("generated_at"):
        snapshot_day = snapshot.get("service_day") or day_window(snapshot["generated_at"])[0]
        if snapshot_day != day:
            # Keep the real last-success time, never fake a successful capture.
            snapshot.update(service_day=day, cleared_for_day=day, flights=[], today=[],
                            stats=stats_of([]), today_stats=stats_of([]),
                            coverage_from=None, coverage_to=None, coverage_hours=None)
            write_json(snapshot_path, snapshot)
    return history


def build_latest(
    cfg: dict[str, Any],
    airport: dict[str, Any],
    flights: list[dict],
    window_hours: int | None,
    started: float,
    scanned_total: int | None = None,
) -> dict[str, Any]:
    iata = airport["iata"]
    history_path = DATA_DIR / f"history_{iata.lower()}.json"
    generated = now_ts()
    day, today_start, today_end = day_window(generated)

    for f in flights:
        f["last_seen_ts"] = now_ts()
    flights.sort(key=lambda f: (f.get("scheduled_ts") or 0, f.get("flight_number") or ""))

    history: dict[str, Any] = rollover_airport(airport, generated)
    if not isinstance(history, dict) or not isinstance(history.get("flights"), dict):
        history = {"flights": {}}
    for f in flights:
        if today_start <= flight_event_time(f) < today_end:
            history["flights"][f["id"]] = f
    pruned = history["flights"]

    four_fams = set(cfg.get("four_engine_families") or {"A340", "A380", "B747", "IL96", "AN124"})
    for f in pruned.values():
        f["is_four_engine"] = family_of(f.get("type"), cfg) in four_fams
        f["is_foreign"] = (not f.get("is_bizjet")) and is_foreign_airline(
            f.get("airline") or f.get("airline_raw"), f.get("airline_iata"), cfg
        )
        f["is_special_type"] = bool(
            f.get("is_four_engine") or f.get("is_cargo") or f.get("is_bizjet")
        )

    write_json(history_path, {
        "service_day": day,
        "updated_at": now_ts(),
        "updated_at_iso": ts_iso(now_ts()),
        "flights": pruned,
    })

    # A source board can still include last night's flights around midnight.
    # Do not reintroduce them into the new day's published snapshot.
    flights = [f for f in flights if flight_event_time(f) >= today_start]
    current_ids = {f["id"] for f in flights}
    seen: dict[tuple, dict] = {}
    for f in pruned.values():
        ts = flight_event_time(f)
        if ts < today_start or ts >= today_end:
            continue
        key = (f.get("board"), f.get("flight_number"), f.get("scheduled_ts"))
        prev = seen.get(key)
        if prev is None or int(f.get("last_seen_ts") or 0) > int(prev.get("last_seen_ts") or 0):
            seen[key] = f
    today_flights = [dict(f, from_history=f["id"] not in current_ids) for f in seen.values()]
    today_flights.sort(key=lambda f: (f.get("scheduled_ts") or 0, f.get("flight_number") or ""))

    photo_cache = read_json(PHOTO_CACHE_PATH, {})
    if isinstance(photo_cache, dict):
        for f in today_flights:
            if f.get("photo"):
                continue
            reg = (f.get("registration") or "").upper()
            entry = photo_cache.get(reg)
            if isinstance(entry, dict) and entry.get("photo"):
                f["photo"] = dict(entry["photo"], reg=reg)

    times = [int(f["scheduled_ts"]) for f in flights if f.get("scheduled_ts")]
    coverage_from = min(times) if times else None
    coverage_to = max(times) if times else None
    coverage_hours = round((coverage_to - coverage_from) / 3600, 1) if times else None

    stats = stats_of(flights)
    stats["scanned_total"] = scanned_total if scanned_total is not None else len(flights)

    return {
        "generated_at": generated,
        "generated_at_iso": ts_iso(generated),
        "service_day": day,
        "duration_sec": round(time.time() - started, 1),
        "airport": {
            "iata": airport["iata"],
            "icao": airport["icao"],
            "name": airport["name"],
            "city": airport.get("city", ""),
            "timezone": "Asia/Shanghai",
        },
        "refresh_hours": cfg.get("refresh_hours", 1/6),
        "window_hours": window_hours,
        "coverage_from": coverage_from,
        "coverage_to": coverage_to,
        "coverage_hours": coverage_hours,
        "pages_per_board": int(cfg.get("pages_per_board", 40)),
        "stats": stats,
        "today_stats": stats_of(today_flights),
        "flights": flights,
        "today": today_flights,
    }


def run(headless: bool = True, debug: bool = False) -> int:
    cfg = load_config()
    airports = get_airports(cfg)
    started = time.time()
    prev_status = read_json(STATUS_PATH, {}) or {}
    prev_airports = prev_status.get("airports") or {}
    for airport in airports:
        rollover_airport(airport, int(started))

    LOG.info("开始抓取 %d 个机场：%s（headless=%s）",
             len(airports), ", ".join(a["iata"] for a in airports), headless)
    try:
        collected = collect_all(cfg, headless=headless, debug=debug)
    except Exception as exc:  # noqa: BLE001
        # Browser/dependency startup failures must also persist a truthful
        # current status rather than leave yesterday's green status in place.
        LOG.error("浏览器启动或采集环境异常：%s", exc)
        collected = {a["iata"]: (AirportFlights(errors={"browser": str(exc)[:1200]}), None) for a in airports}

    # 所有机场的展示航班合并后「一次性」补图：全局共用一份预算，避免逐机场重复消耗
    all_flights: list[dict[str, Any]] = []
    for ap_flights, _ in collected.values():
        all_flights.extend(ap_flights)
    if all_flights:
        attach_photos(all_flights, cfg)

    results: dict[str, Any] = {}
    index_airports: list[dict[str, Any]] = []
    successes = 0

    for airport in airports:
        iata = airport["iata"]
        flights, window_hours = collected.get(iata, ([], None))
        t0 = time.time()
        boards = getattr(flights, "boards", {})
        errors = getattr(flights, "errors", {})
        valid_empty = bool(boards) and all(b.get("ok") for b in boards.values()) and not errors
        if not flights and not valid_empty:
            error = capture_error(flights) or "未返回航班且没有可确认成功的看板；请查看本轮日志，不能据此断定 Cloudflare 拦截"
            prev = prev_airports.get(iata) or {}
            existing = read_json(SITE_DATA_DIR / f"{iata.lower()}.json", {}) or {}
            entry = {
                "ok": False, "iata": iata, "icao": airport.get("icao"),
                "name": airport.get("name"), "city": airport.get("city"),
                "last_success_at": prev.get("last_success_at") or existing.get("generated_at"),
                "last_success_iso": prev.get("last_success_iso") or existing.get("generated_at_iso"),
                "error": error,
                "errors": errors, "boards": boards, "partial": False,
                "stats": prev.get("stats") or existing.get("stats"),
                "coverage_from": existing.get("coverage_from"),
                "coverage_to": existing.get("coverage_to"),
                "duration_sec": None,
            }
            results[iata] = entry
            LOG.error("[%s] 失败：%s", iata, error)
            continue

        try:
            displayed = [f for f in flights if is_displayed(f)]
            latest = build_latest(cfg, airport, displayed, window_hours, t0, len(flights))
            write_json(SITE_DATA_DIR / f"{iata.lower()}.json", latest)
            successes += 1
            entry = {
                "ok": True, "iata": iata, "icao": airport.get("icao"),
                "name": airport.get("name"), "city": airport.get("city"),
                "last_success_at": latest["generated_at"],
                "last_success_iso": latest["generated_at_iso"],
                "error": None,
                "errors": errors, "boards": boards, "partial": bool(errors),
                "stats": latest["stats"],
                "coverage_from": latest.get("coverage_from"),
                "coverage_to": latest.get("coverage_to"),
                "duration_sec": latest["duration_sec"],
            }
            results[iata] = entry
            s = latest["stats"]
            LOG.info(
                "[%s] 完成：扫描 %d，展示 %d（彩绘/外航 %d · 四发 %d · 货机 %d）· 用时 %.1fs",
                iata, s["scanned_total"], s["special"], s["livery_foreign"],
                s["four_engine"], s["cargo"], latest["duration_sec"],
            )
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:300]
            LOG.error("[%s] 汇总失败：%s", iata, error)
            results[iata] = {
                "ok": False, "iata": iata, "icao": airport.get("icao"),
                "name": airport.get("name"), "city": airport.get("city"),
                "last_success_at": None, "last_success_iso": None,
                "error": error, "stats": None, "duration_sec": None,
            }

    now = now_ts()
    index_airports = [results[a["iata"]] for a in airports if a["iata"] in results]
    index = {
        "generated_at": now,
        "generated_at_iso": ts_iso(now),
        "refresh_hours": cfg.get("refresh_hours", 1/6),
        "default_airport": cfg.get("default_airport", "SZX"),
        "duration_sec": round(time.time() - started, 1),
        "airports": index_airports,
    }
    write_json(SITE_DATA_DIR / "index.json", index)

    repo = os.environ.get("GITHUB_REPOSITORY")
    run_id = os.environ.get("GITHUB_RUN_ID")
    try:
        checked_at = int(os.environ.get("FLIGHTDATA_CHECKED_AT", "0"))
    except ValueError:
        checked_at = 0
    if not started-3600 <= checked_at <= started:
        checked_at = int(started)
    status = {
        "collection_started_at": int(started),
        "schedule_checked_at": checked_at,
        "ok": successes > 0,
        "partial": successes < len(airports) or any(r.get("partial") for r in results.values()),
        "successes": successes,
        "total_airports": len(airports),
        "updated_at": now,
        "updated_at_iso": ts_iso(now),
        "refresh_hours": cfg.get("refresh_hours", 1/6),
        "default_airport": cfg.get("default_airport", "SZX"),
        "duration_sec": round(time.time() - started, 1),
        "airports": results,
        "source": "flightradar24-web",
        "repo_url": f"https://github.com/{repo}" if repo else prev_status.get("repo_url"),
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}" if repo and run_id else None,
        "updated_by": "github-actions" if os.environ.get("GITHUB_ACTIONS") else "local",
    }
    write_json(STATUS_PATH, status)

    LOG.info("全部完成：%d/%d 个机场成功，总用时 %.1fs",
             successes, len(airports), time.time() - started)
    return 0 if successes > 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抓取 SZX 起降航班数据（FR24）")
    ap.add_argument("--headed", action="store_true", help="有头模式（CI 中配合 xvfb-run）")
    ap.add_argument("--debug", action="store_true", help="失败时保存截图")
    ap.add_argument("--quiet", action="store_true", help="只输出警告与错误")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return run(headless=not args.headed, debug=args.debug)


if __name__ == "__main__":
    raise SystemExit(main())
