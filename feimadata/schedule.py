"""Two China-time update slots, 06:00 and 14:00; no API calls in this gate."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

CN = timezone(timedelta(hours=8))
STATUS = Path(__file__).resolve().parent / 'data' / 'status.json'


def slot(now):
    local = datetime.fromtimestamp(now,CN)
    hour = 14 if local.hour >= 14 else 6 if local.hour >= 6 else None
    return '%sT%02d:00' % (local.date().isoformat(),hour) if hour is not None else None


def due(status, now, event='schedule', cron=None):
    if event == 'workflow_dispatch':
        return True  # The collector still enforces the shared daily quota.
    current = slot(now)
    if not current:
        return False
    expected = {'0 22 * * *':'06:00','0 6 * * *':'14:00'}.get(cron)
    if expected and not current.endswith(expected):
        return False
    if current in (status.get('schedule_slots') or []):
        return False
    at = status.get('last_attempt_at') or status.get('updated_at')
    if isinstance(at,(int,float)) and at > 0:
        try:
            if slot(at) == current:
                return False
        except (ValueError,OverflowError,OSError):
            pass
    return True


def main():
    try:
        status = json.loads(STATUS.read_text(encoding='utf-8'))
    except (ValueError,OSError):
        status = {}
    event = os.environ.get('EVENT_NAME','schedule')
    run = due(status,time.time(),event,os.environ.get('EVENT_SCHEDULE'))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:
            output.write('run=%s\n' % str(run).lower())
    reason = ('手动更新，仍受每日共享额度限制' if event=='workflow_dispatch' else '执行当前北京时间06:00或14:00更新时段') if run else '未到更新时段或该时段已尝试，跳过'
    print('Feimadat：'+reason)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
            out.write('## Feimadat 运行方式\n\n'+reason+'。\n\n仅深圳；北京时间每天06:00和14:00更新，两次共用每日200次详情额度。\n')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
