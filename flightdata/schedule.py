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


def decision(state, now, event):
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
    if state.get('ok') is False:
        return True, '上次全部失败，允许本次唤醒重试'
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
            output.write(f'## Flightdat 调度检查\n\n{reason}。\n\n每10分钟尝试采集；Actions 定时触发和执行仍可能延迟。\n')


if __name__ == '__main__':
    main()
