"""Read real airport boards, normalize observed fields, and publish local snapshots.

Manual by default. No account mutation, scheduling, scraping, or extra server.
"""
import argparse
import json
import os
from pathlib import Path
import time

from .client import Client, MCPError
from .enrich import DEFAULT_DETAIL_LIMIT, enrich_snapshots
from .normalize import CAPABILITIES, day_window, event_time, normalize_board
from .photos import PhotoError, attach_photos
from .private_key import KeyErrorSafe

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
INDEX = DATA / 'index.json'
STATUS = DATA / 'status.json'


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    temporary.replace(path)


def rollover(airports, now):
    day, _, _ = day_window(now)
    for airport in airports:
        path = DATA / (airport['iata'].lower()+'.json')
        data = read_json(path, {})
        if data and data.get('source') == 'variflight-mcp' and data.get('service_day') != day:
            # Do not fake a new successful collection time when clearing yesterday.
            data.update(service_day=day, flights=[], today=[], cleared_for_day=day)
            write_json(path, data)


def publish_airport(airport, boards, previous, now):
    day, start, end = day_window(now)
    previous = previous if previous.get('source') == 'variflight-mcp' else {}
    old_today = previous.get('today', []) if previous.get('service_day') == day else []
    today = {row['id']: row for row in old_today if start <= event_time(row) < end}
    current, ids = [], set()
    info = dict(previous.get('boards') or {})
    for board, (rows, board_info) in boards.items():
        if rows is None:
            continue
        current.extend(rows)
        ids.update(row['id'] for row in rows)
        info[board] = board_info
        for row in rows:
            if start <= event_time(row) < end:
                today[row['id']] = row
            else:
                today.pop(row['id'], None)  # A delay into tomorrow must leave today's history.
    for row in today.values():
        row['from_history'] = row['id'] not in ids
    return {'source': 'variflight-mcp', 'schema_version': 1, 'service_day': day,
        'generated_at': now, 'airport': dict(airport, timezone='Asia/Tokyo' if airport['iata']=='HND' else 'Asia/Shanghai'),
        'capabilities': dict(CAPABILITIES), 'boards': info,
        'flights': sorted(current, key=event_time), 'today': sorted(today.values(), key=event_time),
        'coverage_note': '仅包含接口实际返回及本日已采集的航班，不把跨日记录当作全天完整性证明'}


def run(codes=None, prefetched=None, client=None, detail_limit=DEFAULT_DETAIL_LIMIT,
        photo_limit=60, enrich_only=False, prefetched_details=None):
    if any(type(value) is not int or not 0 <= value <= 2000 for value in (detail_limit,photo_limit)):
        raise MCPError('详情和照片查询上限须为 0–2000')
    index = read_json(INDEX, {})
    airports = index.get('airports') or []
    selected = [a for a in airports if not codes or a['iata'] in codes]
    if not selected or (codes and set(codes)-{a['iata'] for a in selected}):
        raise MCPError('机场选择不在已配置的七机场列表内')
    now = int(time.time())
    previous_status = read_json(STATUS, {})
    states = dict(previous_status.get('airports') or {})
    rollover(airports, now)
    client = client or (Client() if not enrich_only or detail_limit else None)
    successes, fatal, pending = 0, None, []
    detail_stats, photo_stats = {}, {}
    try:
        if client:
            client.initialize()
            if not enrich_only:
                client.discover_board()
        for airport in selected:
            code = airport['iata']
            path = DATA / (code.lower()+'.json')
            previous = read_json(path, {})
            if enrich_only:
                if (previous.get('source') == 'variflight-mcp' and previous.get('airport',{}).get('iata') == code
                        and isinstance(previous.get('flights'),list) and previous.get('generated_at')):
                    pending.append((code,path,previous))
                    successes += 1
                continue
            boards, errors = {}, {}
            for board, direction in [('arrivals', '1'), ('departures', '0')]:
                if fatal:
                    errors[board] = fatal
                    continue
                try:
                    cached = (prefetched or {}).get((code, board))
                    captured = int(time.time())
                    result = cached[0] if cached else client.get_board(code, direction)
                    if cached:
                        captured = cached[1]
                    rows, details = normalize_board(result, airport, board, captured)
                    boards[board] = (rows, details)
                    if details['partial']:
                        errors[board] = '%d 条记录未通过时间或机场核验' % details['skipped_count']
                    print('%s %s：取得 %d 条，核验 %d 条' % (code, board, details['raw_count'], len(rows)), flush=True)
                except MCPError as error:
                    errors[board] = str(error)
                    print('%s %s：%s' % (code, board, error), flush=True)
                    if error.http_status in (401, 429):
                        fatal = str(error)
            if boards:
                latest = publish_airport(airport, boards, previous, int(time.time()))
                write_json(path, latest)
                pending.append((code,path,latest))
                successes += 1
                states[code] = {'ok': True, 'partial': bool(errors), 'last_success_at': latest['generated_at'],
                    'boards': {b: detail for b, (_, detail) in boards.items()}, 'errors': errors}
            else:
                states[code] = {'ok': False, 'partial': False, 'errors': errors,
                    'last_success_at': (states.get(code) or {}).get('last_success_at') or previous.get('generated_at')}
        snapshots = [data for _,_,data in pending]
        if snapshots:
            try:
                detail_stats = enrich_snapshots(snapshots, client, limit=0 if fatal else detail_limit,
                                                prefetched=prefetched_details)
                if detail_stats.get('fatal_status'):
                    fatal = '详情补齐遇到授权或限流错误，已停止新增查询；看板数据保留'
                photo_stats = attach_photos(snapshots, limit=photo_limit)
            except (MCPError,PhotoError) as error:
                # Optional metadata must never erase a valid airport board.
                print('补充资料未全部完成：%s' % error, flush=True)
            for code,path,data in pending:
                write_json(path,data)
                states.setdefault(code, {'ok':True,'last_success_at':data['generated_at']})
                states[code]['last_enriched_at'] = data.get('enriched_at')
                states[code]['detail_coverage'] = data.get('detail_coverage')
            print('详情：本轮 %d 次航线查询，已匹配 %d 班；照片：本轮 %d 个注册号查询。' % (
                detail_stats.get('route_calls',0), detail_stats.get('matched',0), photo_stats.get('calls',0)), flush=True)
    except (MCPError, KeyErrorSafe) as error:
        fatal = str(error)
        print(fatal, flush=True)
    finally:
        if client:
            client.close()
    at = int(time.time())
    repo, run_id = os.environ.get('GITHUB_REPOSITORY'), os.environ.get('GITHUB_RUN_ID')
    state = {'source': 'variflight-mcp', 'connected': successes > 0,
        'connection_state': 'ready' if successes else 'unavailable',
        'updated_at': at, 'successes': successes, 'requested_airports': len(selected),
        'duration_sec': round(time.time()-now, 1), 'airports': states, 'error': fatal,
        'enrichment': {'details':detail_stats, 'photos':photo_stats},
        'run_url': 'https://github.com/%s/actions/runs/%s' % (repo, run_id) if repo and run_id else None}
    write_json(STATUS, state)
    # Index contains configuration, not an invented last-success timestamp.
    index.update(source='variflight-mcp', connection_state=state['connection_state'])
    write_json(INDEX, index)
    print('本轮 %d/%d 机场取得有效快照；定时任务每天北京时间12时运行一次。' % (successes, len(selected)), flush=True)
    return 0 if successes else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--airports', default='all', help='all 或用英文逗号分隔，例如 SZX,HND')
    parser.add_argument('--detail-limit', type=int, default=DEFAULT_DETAIL_LIMIT,
                        help='每轮最多详情航线查询次数（默认40；0仅读取缓存，不发起详情查询）')
    parser.add_argument('--photo-limit', type=int, default=60, help='每轮最多新照片元数据查询次数（默认60）')
    parser.add_argument('--enrich-only', action='store_true', help='仅补充已有快照，不重新获取机场大屏')
    args = parser.parse_args()
    codes = None if args.airports == 'all' else [code.strip().upper() for code in args.airports.split(',')]
    try:
        raise SystemExit(run(codes, detail_limit=args.detail_limit, photo_limit=args.photo_limit,
                             enrich_only=args.enrich_only))
    except (MCPError, KeyErrorSafe) as error:
        print(str(error))
        raise SystemExit(1)
