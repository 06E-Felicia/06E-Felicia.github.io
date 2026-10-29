"""Cheap schedule wake-up gate; never updates the collector's freshness itself."""
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import time

STATUS = Path(__file__).resolve().parent/'docs/data/status.json'
INTERVAL = 10*60
CN = timezone(timedelta(hours=8))


def cooldown_remaining(state, now):
    try:
        until = float(state.get('retry_not_before') or 0)
    except (TypeError, ValueError):
        return 0
    # Ignore corrupt clocks; a valid source cooldown can span midnight.
    return math.ceil(until-now) if math.isfinite(until) and now < until <= now+86400 else 0


def access_backoff(previous, now, refusal=None):
    if refusal is None:
        return {'access_denied': False, 'consecutive_access_denials': 0,
                'retry_not_before': None, 'retry_not_before_iso': None}
    try:
        count = int(previous.get('consecutive_access_denials') or 0) if previous.get('access_denied') else 0
    except (TypeError, ValueError):
        count = 0
    count = min(10, max(0, count)) + 1
    # 30 min, 1 h, 2 h, 4 h, then at most 6 h; also honor Retry-After.
    delay = min(21600, 1800 * 2**min(count-1, 4))
    delay = max(delay, min(86400, max(0, getattr(refusal, 'retry_after', 0) or 0)))
    until = int(now + delay)
    return {'access_denied': True, 'access_status': getattr(refusal, 'status', None),
            'access_error': str(refusal)[:1200], 'consecutive_access_denials': count,
            'retry_not_before': until,
            'retry_not_before_iso': datetime.fromtimestamp(until, CN).isoformat()}


def decision(state, now, event):
    remaining = cooldown_remaining(state, now)
    if remaining:
        return False, f'源站拒绝后的冷却期尚余 {remaining} 秒，本次不访问 FR24（手动及跨日均遵守）'
    if event == 'workflow_dispatch':
        return True, '管理员手动运行，立即采集'
    if state.get('updated_by') != 'github-actions':
        return True, '尚无 GitHub 自动采集记录'
    try:
        started = float(state.get('schedule_checked_at') or state.get('collection_started_at') or state.get('updated_at') or 0)
    except (TypeError, ValueError):
        started = 0
    if not math.isfinite(started) or not started or started > now+120:
        return True, '上次时间缺失或异常'
    if datetime.fromtimestamp(started, CN).date() != datetime.fromtimestamp(now, CN).date():
        return True, '北京时间已跨日，执行首次更新与昨日数据清理'
    elapsed = now-started
    # Count from the cheap gate, not after browser setup/preflight. A small
    # scheduler-jitter allowance avoids skipping a nominal ten-minute tick.
    threshold = INTERVAL-30 if state.get('schedule_checked_at') else INTERVAL
    if elapsed >= threshold:
        return True, f'距离上次采集调度已过 {int(elapsed)} 秒，执行更新'
    return False, f'尚未满10分钟，本次只检查；约 {int(INTERVAL-elapsed)} 秒后到期'


def main():
    try:
        state = json.loads(STATUS.read_text(encoding='utf-8'))
        if not isinstance(state, dict):state = {}
    except (OSError, ValueError):
        state = {}
    checked = time.time()
    run, reason = decision(state, checked, os.environ.get('GITHUB_EVENT_NAME', 'schedule'))
    print(reason)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write(f'run={str(run).lower()}\n')
            output.write(f'checked_at={int(checked)}\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as output:
            output.write(f'## Flightdat 调度检查\n\n{reason}。\n\n正常每10分钟尝试采集；源站拒绝时退避冷却，Actions 定时触发和执行仍可能延迟。\n')


if __name__ == '__main__':
    main()
