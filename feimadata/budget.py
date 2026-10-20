"""Persistent China-calendar-day detail budget shared by both updates/manual runs."""
from datetime import datetime, timedelta, timezone
from .enrich import read_cache, write_cache

CN = timezone(timedelta(hours=8))
DAILY_LIMIT = 200


class DetailBudget:
    def __init__(self, path, status, now, publish=None):
        local = datetime.fromtimestamp(now,CN)
        self.day = local.date().isoformat()
        # Reserve the second half for the afternoon; unused morning quota carries.
        self.ceiling = 100 if local.hour < 14 else DAILY_LIMIT
        self.path, self.publish = path, publish
        sources = [read_cache(path,{}),status.get('daily_detail_budget') or {}]
        self.used = max([0]+[s['used'] for s in sources if s.get('day') == self.day
                            and type(s.get('used')) is int and s['used'] >= 0])

    def record(self):
        return {'day':self.day,'limit':DAILY_LIMIT,'used':self.used,
                'remaining':max(0,DAILY_LIMIT-self.used)}

    def remaining(self):
        return max(0,self.ceiling-self.used)

    def reserve(self):
        if not self.remaining():
            return False
        self.used += 1
        record = self.record()
        # Reserve before sending: failed/unauthorized requests count as well.
        write_cache(self.path,record)
        if self.publish:
            self.publish(record)
        return True
