"""Registration-matched PlaneSpotters metadata; no image downloads or MCP Key.

Reuse the site's existing photo provider, but keep Feimadat caches independent.
Always retain the source link/photographer and label photos as reference photos.
"""
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit

from .enrich import read_cache, write_cache
from .normalize import event_time, registration, text

CACHE_PATH = Path(__file__).resolve().parent / '.cache' / 'photos.json'
SHARED_PHOTOS = Path(__file__).resolve().parents[1] / 'flightdata' / 'data' / 'photos.json'
MAX_RESPONSE = 2*1024*1024


class PhotoError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PhotoError('照片服务发生重定向，已停止')


def safe_url(value, image=False):
    value = text(value, 2000)
    try:
        url = urlsplit(value)
        hosts = ('t.plnspttrs.net','cdn.planespotters.net') if image else ('www.planespotters.net','planespotters.net')
        if (url.scheme == 'https' and url.hostname in hosts and not url.username and not url.password
                and url.port in (None,443) and not url.fragment and (image or url.path.startswith('/photo/'))):
            return value
    except ValueError:
        pass
    return None


def normalize_photo(photo, reg):
    if not isinstance(photo, dict):
        return None
    # If a provider explicitly returns a different registration, reject it.
    if photo.get('reg') and registration(photo['reg']) != reg:
        return None
    large = photo.get('thumbnail_large') or photo.get('thumbnail') or {}
    image, link = safe_url(large.get('src'), True), safe_url(photo.get('link'))
    credit = text(photo.get('photographer'), 150)
    if not image or not link or not credit:
        return None
    return {'src':image, 'link':link, 'photographer':credit, 'reg':reg,
            'source':'planespotters', 'provider':'PlaneSpotters.net · 同注册号资料照片（非本航班实拍）'}


def fetch_photo(reg, opener=None):
    reg = registration(reg)
    if not reg:
        raise PhotoError('注册号无效，未查询照片')
    request = urllib.request.Request('https://api.planespotters.net/pub/photos/reg/'+quote(reg, safe=''),
        headers={'User-Agent':'Feimadat/1.1 (+https://06e-felicia.github.io/Feimadat.html)', 'Accept':'application/json'})
    try:
        import json
        with (opener or urllib.request.build_opener(NoRedirect())).open(request, timeout=15) as response:
            raw = response.read(MAX_RESPONSE+1)
        if len(raw) > MAX_RESPONSE:
            raise PhotoError('照片元数据超出大小限制')
        data = json.loads(raw)
        if not isinstance(data,dict) or not isinstance(data.get('photos'),list):
            raise PhotoError('照片响应结构无效')
        if not data['photos']:
            return None
        for photo in data['photos']:
            normalized = normalize_photo(photo, reg)
            if normalized:
                return normalized
        raise PhotoError('照片来源或署名无法核验')
    except PhotoError:
        raise
    except urllib.error.HTTPError as error:
        raise PhotoError('照片服务 HTTP %d' % error.code, error.code) from None
    except Exception:
        raise PhotoError('照片元数据读取失败；不影响航班数据') from None


def attach_photos(snapshots, limit=60, now=None, path=None, fetcher=None, delay=0.35, previous=None, shared=None):
    if type(limit) is not int or not 0 <= limit <= 2000:
        raise PhotoError('照片查询上限须为 0–2000')
    now, path, fetcher = int(time.time()) if now is None else now, path or CACHE_PATH, fetcher or fetch_photo
    raw = read_cache(path, {})
    cache = {k:v for k,v in (raw.get('entries') or {}).items() if isinstance(v,dict)
        and type(v.get('checked_at')) is int and 0 <= now-v['checked_at'] <= 30*86400}
    # Photos belong to a registration, not a flight-data provider. Reuse only
    # verified PlaneSpotters metadata; never import FR24 flight/aircraft fields.
    for reg,entry in read_cache(shared or SHARED_PHOTOS,{}).items():
        if not isinstance(entry,dict) or registration(reg) != reg:
            continue
        photo,at = entry.get('photo') or {},entry.get('updated_at')
        if (type(at) is int and 0 <= now-at < 30*86400 and photo.get('source')=='planespotters'
                and safe_url(photo.get('src'),True) and safe_url(photo.get('link'))
                and text(photo.get('photographer')) and at > (cache.get(reg) or {}).get('checked_at',0)):
            cache[reg] = {'checked_at':at,'photo':dict(photo,reg=reg,
                provider='PlaneSpotters.net · 同注册号资料照片（非本航班实拍）')}
    for snapshot in list(previous or [])+snapshots:
        for f in snapshot.get('flights',[])+snapshot.get('today',[]):
            reg,photo = registration(f.get('registration')),f.get('photo') or {}
            at = f.get('photo_checked_at') or snapshot.get('enriched_at')
            if (reg and type(at) is int and 0 <= now-at < 30*86400 and photo.get('source')=='planespotters'
                    and photo.get('reg')==reg and safe_url(photo.get('src'),True)
                    and safe_url(photo.get('link')) and text(photo.get('photographer'))
                    and at > (cache.get(reg) or {}).get('checked_at',0)):
                cache[reg] = {'checked_at':at,'photo':photo}
    refs = {}
    for snapshot in snapshots:
        for f in snapshot.get('flights',[])+snapshot.get('today',[]):
            reg = registration(f.get('registration'))
            photo = f.get('photo') or {}
            if photo.get('source') == 'planespotters' and photo.get('reg') != reg:
                f['photo'] = None
            if reg:
                refs.setdefault(reg,[]).append(f)
    stats = {'calls':0,'covered':0,'errors':0}
    deadline = time.monotonic()+3*60
    consecutive_errors = 0
    def priority(reg):
        future = [event_time(f) for f in refs[reg] if event_time(f) >= now]
        return (0,min(future)-now) if future else (1,0)
    for reg in sorted(refs, key=priority):
        entry = cache.get(reg)
        ttl = 7*86400 if entry and entry.get('photo') is None else 30*86400
        fresh = entry and now-entry['checked_at'] < ttl
        # Livery theme pictures remain a fallback if the reference service fails.
        if not fresh and stats['calls'] < limit and time.monotonic() < deadline:
            stats['calls'] += 1
            try:
                photo = fetcher(reg)
                cache[reg] = {'checked_at':now,'photo':photo}
                entry = cache[reg]
                consecutive_errors = 0
            except PhotoError as error:
                stats['errors'] += 1
                consecutive_errors += 1
                if error.status in (401,403,429) or consecutive_errors >= 3:
                    # Do not hammer a service which has refused or rate-limited us.
                    limit = stats['calls']
            if delay:
                time.sleep(delay)
        if entry and entry.get('photo') and now-entry['checked_at'] < 30*86400:
            photo = entry['photo']
            if (photo.get('reg') == reg and safe_url(photo.get('src'), True)
                    and safe_url(photo.get('link')) and text(photo.get('photographer'))):
                for f in refs[reg]:
                    f['photo'] = dict(photo)
                    f['photo_checked_at'] = entry['checked_at']
                stats['covered'] += 1
    write_cache(path, {'schema_version':1,'entries':cache})
    for snapshot in snapshots:
        coverage = snapshot.get('detail_coverage')
        if coverage is not None:
            coverage['photo'] = sum(bool(f.get('photo')) for f in snapshot['flights'])
    return stats
