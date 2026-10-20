"""Once per China-calendar day, not before 12:00; no API calls in this gate."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

CN = timezone(timedelta(hours=8))
STATUS = Path(__file__).resolve().parent / 'data' / 'status.json'


def due(status, now):
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
    run = due(status,time.time())
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:
            output.write('run=%s\n' % str(run).lower())
    print('Feimadat：北京时间12时后的本日首次采集' if run else 'Feimadat：未到12时或今天已运行，跳过以节省积分')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
