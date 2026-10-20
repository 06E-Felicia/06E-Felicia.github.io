"""Once per China-calendar day, not before 12:00; no API calls in this gate."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

CN = timezone(timedelta(hours=8))
STATUS = Path(__file__).resolve().parent / 'data' / 'status.json'


def due(status, now, event='schedule'):
    # A manual acceptance/recovery run is intentional, not an automatic retry.
    # Local sample snapshots must never cause a user-triggered run to be skipped.
    if event == 'workflow_dispatch':
        return True
    local = datetime.fromtimestamp(now,CN)
    if local.hour < 12:
        return False
    at = status.get('updated_at') if isinstance(status,dict) else None
    if isinstance(at,(int,float)) and at > 0:
        try:
            if datetime.fromtimestamp(at,CN).date() == local.date():
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
    run = due(status,time.time(),event)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:
            output.write('run=%s\n' % str(run).lower())
    reason = ('手动立即更新，将使用账号额度' if event=='workflow_dispatch' else '北京时间12时后的本日首次自动采集') if run else '未到12时或今天已自动采集，跳过以节省积分'
    print('Feimadat：'+reason)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as out:
            out.write('## Feimadat 运行方式\n\n'+reason+'。\n\n自动任务仍为每天北京时间12:00一次；手动运行明确绕过当天限制。\n')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
