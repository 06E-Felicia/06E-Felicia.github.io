"""Map the airport-board structuredContent actually observed on 2026-10-20.

No FR24 records or guessed airline names are used. Details are enriched separately.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import math
import re

from .client import MCPError

CN = timezone(timedelta(hours=8))
CAPABILITIES = {'aircraft_type': False, 'widebody': False, 'four': False,
                'cargo': False, 'foreign_airline': False, 'livery': True,
                'actual_time': True, 'terminal': True}
STATES = {
    '到达': ('arrived', '已落地', 'ok'),
    '起飞': ('departed', '已起飞', 'ok'),
    '提前取消': ('cancelled', '已取消', 'bad'),
    '取消': ('cancelled', '已取消', 'bad'),
    '计划': ('scheduled', '计划', 'muted'),
    '正在登机': ('boarding', '登机中', 'info'),
    '催促登机': ('boarding', '催促登机', 'warn'),
    '登机结束': ('boarding-complete', '登机结束', 'info'),
    '延误预警': ('delay-warning', '延误预警', 'warn'),
    '延误': ('delayed', '延误', 'warn'),
    '备降': ('diverted', '备降', 'warn'),
    '返航': ('returning', '返航', 'warn'),
}


def text(value, limit=300):
    if not isinstance(value, str):
        return ''
    return ''.join(c for c in value.strip() if ord(c) >= 32)[:limit]


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def registration(value):
    value = text(value, 30).upper().replace(' ', '')
    value = re.sub(r'^B([A-Z0-9]{4})$', r'B-\1', value)
    return value if re.fullmatch(r'[A-Z0-9][A-Z0-9-]{2,13}', value) and value not in ('UNKNOWN', 'NONE', 'NULL') else None


def airport_zone(code):
    # Board clocks are airport-local, as checked against ANA's NH965 timetable.
    # The seven configured airports have no daylight-saving transition.
    return timezone(timedelta(hours=9 if code == 'HND' else 8))


def timestamp(date, hour, zone):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(date)):
        return None
    match = re.fullmatch(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', str(hour))
    if not match:
        return None
    h, minute, second = (int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))
    try:
        if h == 24 and minute == second == 0:
            return int((datetime.fromisoformat(date).replace(tzinfo=zone) + timedelta(days=1)).timestamp())
        return int(datetime.fromisoformat(date).replace(hour=h, minute=minute, second=second, tzinfo=zone).timestamp())
    except ValueError:
        return None


def nearby_time(date, hour, zone, scheduled, delay=None):
    candidate = timestamp(date, hour, zone)
    if candidate is None:
        return None
    reference = scheduled + int(delay * 60) if delay is not None and abs(delay) <= 7*1440 else scheduled
    day_offset = round((reference - candidate) / 86400)
    return min((candidate + (day_offset + shift) * 86400 for shift in (-1, 0, 1)),
               key=lambda value: abs(value - reference))


def event_time(flight):
    for field in ('actual_ts', 'estimated_ts', 'scheduled_ts'):
        value = number(flight.get(field))
        if value is not None and value > 0:
            return int(value)
    return 0


def day_window(now):
    start = datetime.fromtimestamp(now, CN).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.date().isoformat(), int(start.timestamp()), int((start + timedelta(days=1)).timestamp())


def source_rows(result):
    if not isinstance(result, dict) or result.get('isError'):
        raise MCPError('机场大屏未返回有效结果，未更新快照')
    content = result.get('structuredContent')
    if isinstance(content, dict) and content.get('error'):
        raise MCPError('飞常准返回结构化业务错误，未将错误当作空列表')
    if not isinstance(content, dict) or content.get('kind') != 'collection' or not isinstance(content.get('items'), list):
        raise MCPError('机场大屏结构与已实测版本不同，需要核验后再更新，未猜测字段')
    if any(not isinstance(row, dict) for row in content['items']):
        raise MCPError('机场大屏包含无效记录，未更新快照')
    return content['items']


def normalize_board(result, airport, board, captured_at):
    if board not in ('arrivals', 'departures'):
        raise MCPError('方向参数不正确')
    rows = source_rows(result)
    prefix = 'arr' if board == 'arrivals' else 'dep'
    home_field = 'arrivalCode' if board == 'arrivals' else 'departureCode'
    endpoint_prefix = 'departure' if board == 'arrivals' else 'arrival'
    zone, flights, skipped = airport_zone(airport['iata']), {}, 0
    for raw in rows:
        flight_number = text(raw.get('flightNumber'), 40).upper()
        scheduled = timestamp(raw.get(prefix+'Date'), raw.get(prefix+'PlanHour'), zone)
        if not flight_number or not scheduled or raw.get(home_field) != airport['iata']:
            skipped += 1
            continue
        delay = number(raw.get('delayData'))
        estimated = nearby_time(raw.get(prefix+'Date'), raw.get(prefix+'EstHour'), zone, scheduled, delay)
        actual = nearby_time(raw.get(prefix+'Date'), raw.get(prefix+'ActHour'), zone, scheduled, delay)
        status_raw = text(raw.get('flightStatus'), 60)
        status, status_cn, kind = STATES.get(status_raw, ('unknown', status_raw or '未知', 'muted'))
        if status_raw == '起飞' and board == 'arrivals':
            status, status_cn, kind = 'en-route', '飞行中', 'info'
        reg = registration(raw.get('aircraftNumber'))
        livery = text(raw.get('flightDesc')) or None
        identity = '|'.join([board, flight_number, text(raw.get('departureCode')), text(raw.get('arrivalCode')),
                             text(raw.get('depDate')), text(raw.get('depPlanHour'))])
        fid = 'vf-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]
        airline_code = text(raw.get('airlineCode'), 5).upper()
        flights[fid] = {
            'id': fid, 'board': board, 'flight_number': flight_number, 'scheduled_ts': scheduled,
            'estimated_ts': estimated, 'actual_ts': actual, 'delay_min': delay,
            'status': status, 'status_cn': status_cn, 'status_kind': kind, 'source_status': status_raw,
            'airline': airline_code, 'airline_iata': airline_code, 'airline_raw': None,
            'airline_name_provided': False, 'registration': reg,
            'registration_source': 'getAirportFlightBoard' if reg else None,
            'type': None, 'type_family': None, 'callsign': None,
            'terminal': text(raw.get(prefix+'Terminal')) or None, 'gate': None, 'runway': None,
            'endpoint': {'iata': text(raw.get(endpoint_prefix+'Code'), 3),
                         'name': text(raw.get(endpoint_prefix)), 'city': text(raw.get(endpoint_prefix))},
            'is_special_livery': bool(livery), 'livery': livery, 'livery_source': 'variflight',
            'is_widebody': None, 'is_four_engine': None, 'is_cargo': None, 'is_foreign': None,
            'photo': None, 'last_seen_ts': captured_at, 'source': 'variflight-mcp',
            'source_times': {key: text(raw.get(key), 50) for key in
                             ('depDate','arrDate','depPlanHour','depEstHour','depActHour','arrPlanHour','arrEstHour','arrActHour')},
            'detail_query': {'fnum': flight_number, 'date': text(raw.get('depDate'), 10),
                             'dep': text(raw.get('departureCode'), 3), 'arr': text(raw.get('arrivalCode'), 3),
                             'dep_hour': text(raw.get('depPlanHour'), 8)},
        }
    if rows and not flights:
        raise MCPError('大屏有记录但全部无法核验机场或时间，未冒充零航班')
    result_flights = sorted(flights.values(), key=event_time)
    times = [f['scheduled_ts'] for f in result_flights]
    return result_flights, {'ok': True, 'raw_count': len(rows), 'parsed_count': len(result_flights),
        'skipped_count': skipped, 'partial': bool(skipped), 'captured_at': captured_at,
        'scheduled_from': min(times) if times else None, 'scheduled_to': max(times) if times else None,
        'coverage_complete': None}
