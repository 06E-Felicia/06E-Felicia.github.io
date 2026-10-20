"""Quota-bounded flight detail enrichment, matched by flight/date/route/STD.

Only sanitized fields are cached, never MCP envelopes, credentials, URLs from
unrelated fields, or provider errors. Route queries may include other airports;
their records must match an actual board row before they can be used.
"""
from collections import defaultdict
from datetime import date as calendar_date, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

from .client import MCPError
from .normalize import day_window, event_time, registration, source_rows, text, theme_photo

CACHE_PATH = Path(__file__).resolve().parent / '.cache' / 'details.json'
DEFAULT_DETAIL_LIMIT = 40  # Route queries, not one paid query per displayed row.


def seed_from_snapshots(snapshots):
    """Recover sanitized, already-public details after a cold Actions Cache miss."""
    entries = {}
    for snapshot in snapshots:
        if snapshot.get('source') != 'variflight-mcp':
            continue
        for f in snapshot.get('flights',[])+snapshot.get('today',[]):
            at = f.get('detail_checked_at')
            query = query_for(f,snapshot['airport']['iata'])
            if f.get('detail_source') != 'getFlightStatus' or type(at) is not int or not query:
                continue
            fields = {k:f.get(k) for k in ('type','type_family','is_widebody','is_four_engine')}
            fields.update(registration=registration(f.get('registration')),
                airline_name=text(f.get('airline_raw'),150) or None,
                arrival_terminal=f.get('terminal') if f['board']=='arrivals' else None,
                departure_terminal=f.get('terminal') if f['board']=='departures' else None,
                gate=f.get('gate') if f['board']=='departures' else None,
                livery=text(f.get('livery')) or None,
                photo=f.get('photo') if (f.get('photo') or {}).get('source') != 'planespotters' else None)
            key = query_key(query)
            old = entries.get(key)
            if not old or old['checked_at'] < at:
                entries[key] = {'query':query,'checked_at':at,'fields':fields}
            elif old['checked_at'] == at:
                old['fields'].update({k:v for k,v in fields.items() if v is not None})
    return entries


def read_cache(path, default):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError):
        return default


def write_cache(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False, separators=(',', ':'))
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def query_for(flight, home):
    query = flight.get('detail_query')
    if not isinstance(query, dict):
        times = flight.get('source_times') or {}
        incoming = flight.get('board') == 'arrivals'
        endpoint = (flight.get('endpoint') or {}).get('iata')
        query = {'fnum': flight.get('flight_number'), 'date': times.get('depDate'),
                 'dep': endpoint if incoming else home, 'arr': home if incoming else endpoint,
                 'dep_hour': times.get('depPlanHour')}
    query = {key: text(query.get(key), 40).upper() for key in ('fnum', 'date', 'dep', 'arr', 'dep_hour')}
    try:
        if calendar_date.fromisoformat(query['date']).isoformat() != query['date']:
            return None
    except ValueError:
        return None
    if not re.fullmatch(r'[A-Z0-9]{2}\d{1,5}[A-Z]?', query['fnum']):
        return None
    if any(not re.fullmatch(r'[A-Z]{3}', query[k]) for k in ('dep', 'arr')):
        return None
    if not re.fullmatch(r'(?:[01]?\d|2[0-3]):[0-5]\d(?::00)?', query['dep_hour']):
        return None
    hour, minute = map(int, query['dep_hour'].split(':')[:2])
    query['dep_hour'] = '%02d:%02d' % (hour, minute)
    return query


def query_key(query):
    return hashlib.sha256('|'.join(query[k] for k in ('fnum', 'date', 'dep', 'arr', 'dep_hour')).encode()).hexdigest()


def aircraft_model(model, generic=''):
    """Classify only known model/ICAO families, never infer from registration."""
    model, generic = text(model, 80), text(generic, 20).upper()
    display = model if model.upper() not in ('', 'JET', 'UNKNOWN', '--') else (
        generic if generic not in ('', 'JET', 'UNKNOWN', '--') else None)
    codes = [(display or '').upper(),generic]
    patterns = (
        ('A350', r'A350|A35[09]|35[09]$'), ('A380', r'A380|A388|388$'),
        ('A340', r'A340|A34[236]|34[236]$'), ('A330', r'A330|A33[02389]|33[02389]$'),
        ('B787', r'B?787|B78[789X]|78[789]$'), ('B777', r'B?777|B77[23789LWFX]|77[23789LWF]$'),
        ('B747', r'B?747|B74[48FS]|74[48F]$'), ('B767', r'B?767|B76[237FW]|76[237F]$'),
        ('B757', r'B?757|B75[23F]|75[23F]$'), ('B737', r'B?737|B73[0-9A-Z]|B3[89]M|73[0-9]$'),
        ('A320', r'A3(?:18|19|20|21)|A2[01]N|(?:31[89N]|32[01ABNZ])$'),
        ('E-Jet', r'ERJ|EMBRAER|E1[79][05]|E[12][79][05]'), ('CRJ', r'CRJ|CR[279X]'),
        ('C919', r'C919'), ('ARJ21', r'ARJ21|C909'), ('ATR', r'ATR|AT[47][256]'),
    )
    # Match the model prefix, not a customer suffix (A330-343 is not A340).
    family = next((family for family, pattern in patterns if any(re.match('(?:'+pattern+')',code) for code in codes)), None)
    wide = family in ('A330', 'A340', 'A350', 'A380', 'B747', 'B767', 'B777', 'B787') if family else None
    four = family in ('A340', 'A380', 'B747') if family else None
    return {'type': display, 'type_family': family, 'is_widebody': wide, 'is_four_engine': four}


def parse_details(result):
    # The collection envelope and these fields were verified with real responses.
    entries = {}
    for row in source_rows(result):
        plan = text(row.get('FlightDeptimePlanDate'), 30)
        match = re.fullmatch(r'(\d{4}-\d{2}-\d{2})[ T](\d{1,2}:\d{2})(?::00)?', plan)
        if not match:
            continue
        query = query_for({'detail_query': {'fnum': row.get('FlightNo'), 'date': match[1],
            'dep': row.get('FlightDepcode'), 'arr': row.get('FlightArrcode'), 'dep_hour': match[2]}}, None)
        if not query:
            continue
        fields = aircraft_model(row.get('miniAirplaneModels'), row.get('generic'))
        fields.update(registration=registration(row.get('aircraftNumber')),
            airline_name=text(row.get('FlightCompany'), 150) or None,
            arrival_terminal=text(row.get('FlightArrTerminal'), 40) or None,
            departure_terminal=text(row.get('FlightDepTerminal'), 40) or None,
            gate=text(row.get('BoardGate'), 40) or None,
            livery=text(row.get('flightDesc')) or None, photo=theme_photo(row.get('flightPic')))
        key = query_key(query)
        # Ambiguous duplicate summaries must not arbitrarily pick an aircraft.
        if key in entries and entries[key]['fields'] != fields:
            entries[key]['fields'] = {}
        else:
            entries[key] = {'query': query, 'fields': fields}
    return entries


def fresh(entry, flight, now):
    if not isinstance(entry, dict) or not isinstance(entry.get('fields'), dict):
        return False
    at = entry.get('checked_at')
    if type(at) is not int or not 0 <= now-at <= 2*86400:
        return False
    # Empty/unassigned results are short-lived; assignments refresh near flight.
    if not entry['fields'].get('registration'):
        ttl = 15*60
    elif flight.get('actual_ts') and event_time(flight) < now:
        ttl = 2*86400
    else:
        ttl = 30*60 if abs(event_time(flight)-now) < 3*3600 else 4*3600
    return now-at < ttl


def apply_details(flight, entry):
    fields = entry['fields']
    if not fields:
        return
    reg = fields.get('registration')
    board_reg = flight.get('registration') if flight.get('registration_source') != 'getFlightStatus' else None
    # A fresh board assignment wins over a conflicting cached detail assignment.
    if board_reg and reg and board_reg != reg:
        return
    flight['detail_base'] = {k:flight.get(k) for k in (
        'registration','registration_source','type','type_family','is_widebody','is_four_engine',
        'airline','airline_raw','airline_name_provided','terminal','gate','livery','is_special_livery','livery_source','photo')}
    if reg and not board_reg:
        flight.update(registration=reg, registration_source='getFlightStatus')
    for key in ('type', 'type_family', 'is_widebody', 'is_four_engine'):
        if fields.get(key) is not None:
            flight[key] = fields[key]
    if fields.get('airline_name'):
        flight.update(airline=fields['airline_name'], airline_raw=fields['airline_name'], airline_name_provided=True)
    terminal = fields.get('arrival_terminal' if flight['board']=='arrivals' else 'departure_terminal')
    if terminal:
        flight['terminal'] = terminal
    if flight['board'] == 'departures' and fields.get('gate'):
        flight['gate'] = fields['gate']
    if fields.get('livery'):
        flight.update(livery=fields['livery'], is_special_livery=True, livery_source='variflight')
    if fields.get('photo') and not flight.get('photo'):
        flight['photo'] = fields['photo']
    flight['detail_checked_at'] = entry['checked_at']
    flight['detail_source'] = 'getFlightStatus'


def clear_old_details(flight):
    """Enrichment-only updates cannot silently retain an obsolete assignment."""
    if flight.get('detail_source') != 'getFlightStatus':
        return
    base = flight.pop('detail_base', None)
    if isinstance(base, dict):
        flight.update(base)
        flight.pop('detail_checked_at', None)
        flight.pop('detail_source', None)
        flight.pop('detail_stale', None)
        return
    if flight.get('registration_source') == 'getFlightStatus':
        flight.update(registration=None, registration_source=None)
        # A photo is tied to a registration, not to a reusable flight number.
        if (flight.get('photo') or {}).get('source') == 'planespotters':
            flight['photo'] = None
    flight.update(type=None, type_family=None, is_widebody=None, is_four_engine=None,
                  airline=flight.get('airline_iata'), airline_raw=None, airline_name_provided=False)
    flight.pop('detail_checked_at', None)
    flight.pop('detail_source', None)
    flight.pop('detail_stale', None)


def enrich_snapshots(snapshots, client, limit=DEFAULT_DETAIL_LIMIT, now=None, path=None, prefetched=None, previous=None):
    """Bound the paid route requests; use valid cache even with limit=0."""
    if type(limit) is not int or not 0 <= limit <= 2000:
        raise MCPError('详情航线查询上限须为 0–2000')
    now, path = int(time.time()) if now is None else now, path or CACHE_PATH
    day = day_window(now)[0]
    cache = read_cache(path, {})
    # Rebuild rather than allow indefinite cache growth (overnight flights kept).
    cutoff = (calendar_date.fromisoformat(day)-timedelta(days=1)).isoformat()
    upper = (calendar_date.fromisoformat(day)+timedelta(days=2)).isoformat()
    old = cache.get('entries') or {}
    entries = {k:v for k,v in old.items() if isinstance(v,dict) and
               cutoff <= str((v.get('query') or {}).get('date','')) <= upper}
    for key,entry in seed_from_snapshots(list(previous or [])+snapshots).items():
        if cutoff <= entry['query']['date'] <= upper and entry['checked_at'] > (entries.get(key) or {}).get('checked_at',0):
            entries[key] = entry
    refs = defaultdict(list)
    for snapshot in snapshots:
        for flight in snapshot.get('flights', [])+snapshot.get('today', []):
            query = query_for(flight, snapshot['airport']['iata'])
            if query:
                flight['detail_query'] = query
                refs[query_key(query)].append(flight)
    routes = defaultdict(set)
    for key, flights in refs.items():
        if all(fresh(entries.get(key), f, now) for f in flights):
            continue
        query = flights[0]['detail_query']
        routes[(query['date'],query['dep'],query['arr'])].add(key)
    # Near-future routes first; old completed flights never starve today's list.
    def priority(route):
        times = [event_time(f) for key in routes[route] for f in refs[key]]
        future = [t for t in times if t >= now]
        return (0, min(future)-now) if future else (1, now-max(times))
    stats = {'route_calls':0, 'batch_routes':0, 'cache_hits':0, 'matched':0, 'pending_routes':0, 'errors':0, 'fatal_status':None}
    supplied = dict(prefetched or {})
    deadline = time.monotonic()+10*60
    pending = set(routes)
    homes = {s['airport']['iata'] for s in snapshots}
    while pending:
        # Another batch may already have returned these exact records.
        pending = {r for r in pending if any(not fresh(entries.get(k),refs[k][0],now) for k in routes[r])}
        allowed = pending if stats['route_calls'] < limit else pending.intersection(supplied)
        if not allowed:
            break
        if time.monotonic() >= deadline:
            break
        route = min(allowed,key=priority)
        batch = [route]
        if route not in supplied:
            options = []
            for fixed in (1,2):
                if route[fixed] not in homes:
                    continue
                selected,weight = [route],len(routes[route])
                for other in sorted(pending-{route},key=priority):
                    if other[0] != route[0] or other[fixed] != route[fixed]:
                        continue
                    if len(selected) >= 3 or weight+len(routes[other]) > 60:
                        continue
                    selected.append(other);weight += len(routes[other])
                options.append(selected)
            if options:
                batch = max(options,key=lambda group:sum(len(routes[r]) for r in group))
        pending.difference_update(batch)
        try:
            if route in supplied:
                response, checked = supplied[route]
            else:
                stats['route_calls'] += 1
                arguments = (route[0],','.join(dict.fromkeys(r[1] for r in batch)),
                             ','.join(dict.fromkeys(r[2] for r in batch)))
                response, checked = client.get_status(*arguments), now
                stats['batch_routes'] += len(batch)
            parsed = parse_details(response)
            for key in set().union(*(routes[r] for r in batch)):
                if key not in parsed:
                    entries[key] = {'query':refs[key][0]['detail_query'], 'fields':{}, 'checked_at':checked}
            for key, entry in parsed.items():
                if key in refs:  # Exact five-element match, never array position.
                    entries[key] = dict(entry, checked_at=checked)
                    stats['matched'] += 1
            write_cache(path, {'schema_version':1,'service_day':day,'entries':entries})
        except MCPError as error:
            stats['errors'] += 1
            print('航班详情补齐未完成：%s' % error, flush=True)
            if error.http_status in (401,403,429):
                stats['fatal_status'] = error.http_status
                break
    for key, flights in refs.items():
        entry = entries.get(key)
        for f in flights:
            clear_old_details(f)
            # Retain last-known data within a daily snapshot, not a fake new check.
            at = entry.get('checked_at') if isinstance(entry,dict) else None
            usable = (type(at) is int and 0 <= now-at <= 2*86400
                      and isinstance(entry.get('fields'),dict))
            if usable:
                apply_details(f, entry)
                if f.get('detail_source'):
                    f['detail_stale'] = not fresh(entry,f,now)
        if entry and entry.get('fields') and any(f.get('detail_source') == 'getFlightStatus' for f in flights):
            stats['cache_hits'] += 1
    stats['pending_routes'] = sum(any(not fresh(entries.get(k),refs[k][0],now) for k in keys) for keys in routes.values())
    write_cache(path, {'schema_version':1,'service_day':day,'entries':entries})
    for snapshot in snapshots:
        rows = snapshot['flights']
        coverage = {'total':len(rows),'registration':sum(bool(f.get('registration')) for f in rows),
            'aircraft_type':sum(bool(f.get('type')) for f in rows), 'photo':sum(bool(f.get('photo')) for f in rows)}
        caps = snapshot.setdefault('capabilities', {})
        caps.update(aircraft_type=bool(coverage['aircraft_type']),
            widebody=any(f.get('is_widebody') is not None for f in rows),
            four=any(f.get('is_four_engine') is not None for f in rows))
        snapshot.update(detail_coverage=coverage, enriched_at=now)
    return stats
