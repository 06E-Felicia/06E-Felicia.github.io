"""Private Playwright state handling. Never log cookie/token contents."""
import base64
import gzip
import io
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

AUTH_DIR = Path(__file__).resolve().parent/'.auth'
STATE_FILE = AUTH_DIR/'fr24-state.json'
SECRET_FILE = AUTH_DIR/'fr24-state.b64'
SECRET_NAME = 'FR24_STORAGE_STATE_B64'
MAX_STATE_BYTES = 256*1024
MAX_SECRET_BYTES = 48*1024
_CHALLENGE_COOKIES = {'cf_clearance','__cf_bm','_cfuvid','cf_chl_rc_i','cf_chl_rc_ni'}


class SessionError(RuntimeError):
    pass


def is_fr24_host(host):
    host = str(host or '').lower().lstrip('.')
    return host == 'flightradar24.com' or host.endswith('.flightradar24.com')


def scoped_state(data):
    if not isinstance(data,dict) or not isinstance(data.get('cookies'),list) or not isinstance(data.get('origins',[]),list):
        raise SessionError('登录会话格式无效，请重新导出')
    cookies = []
    for cookie in data['cookies']:
        if not isinstance(cookie,dict) or not is_fr24_host(cookie.get('domain')):
            continue
        if cookie.get('name') in _CHALLENGE_COOKIES:
            continue  # Never reuse a Cloudflare challenge clearance on CI.
        if not isinstance(cookie.get('name'),str) or not isinstance(cookie.get('value'),str):
            raise SessionError('登录会话格式无效，请重新导出')
        cookies.append({k:v for k,v in cookie.items() if k in
                        ('name','value','domain','path','expires','httpOnly','secure','sameSite','partitionKey')})
    origins = []
    for item in data.get('origins',[]):
        if not isinstance(item,dict):
            continue
        try:
            url = urlsplit(item.get('origin',''))
        except (ValueError,TypeError):
            continue
        if url.scheme != 'https' or not is_fr24_host(url.hostname) or url.username or url.password:
            continue
        local = item.get('localStorage',[])
        if not isinstance(local,list) or any(not isinstance(x,dict) or
                not isinstance(x.get('name'),str) or not isinstance(x.get('value'),str) for x in local):
            raise SessionError('登录会话格式无效，请重新导出')
        origins.append({'origin':item['origin'],'localStorage':local})
    if not cookies and not any(o['localStorage'] for o in origins):
        raise SessionError('没有可复用的 FR24 会话，请在专用窗口登录后重新导出')
    return {'cookies':cookies,'origins':origins}


def encode_state(data):
    state = scoped_state(data)
    raw = json.dumps(state,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    if len(raw)>MAX_STATE_BYTES:
        raise SessionError('会话文件过大，请使用仅用于 FR24 的专用窗口重新登录')
    encoded = base64.b64encode(gzip.compress(raw,mtime=0)).decode('ascii')
    if len(encoded)>MAX_SECRET_BYTES:
        raise SessionError('会话超过 GitHub Secret 大小限制，请重新导出')
    return state,encoded


def decode_state(encoded):
    try:
        if not isinstance(encoded,str) or len(encoded)>MAX_SECRET_BYTES:
            raise ValueError()
        raw = base64.b64decode(encoded.strip(),validate=True)
        if raw.startswith(b'\x1f\x8b'):
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(MAX_STATE_BYTES+1)
        if len(raw)>MAX_STATE_BYTES:
            raise ValueError()
        return scoped_state(json.loads(raw))
    except Exception:
        # JSON/Playwright exceptions can otherwise include fragments of tokens.
        raise SessionError('FR24 Secret 无效或损坏，请在本机重新导出并更新') from None


def state_requested():
    return bool(os.environ.get(SECRET_NAME) or os.environ.get('FR24_STORAGE_STATE_PATH') or
                (not os.environ.get('GITHUB_ACTIONS') and STATE_FILE.is_file()))


def load_state():
    encoded = os.environ.get(SECRET_NAME)
    if encoded:
        return decode_state(encoded)
    path = os.environ.get('FR24_STORAGE_STATE_PATH')
    if not path and not os.environ.get('GITHUB_ACTIONS') and STATE_FILE.is_file():
        path = str(STATE_FILE)
    if not path:
        return None
    try:
        raw = Path(path).read_bytes()
        if len(raw)>MAX_STATE_BYTES:
            raise ValueError()
        return scoped_state(json.loads(raw))
    except Exception:
        raise SessionError('本地 FR24 会话不可读取，请在专用窗口重新导出') from None


def save_private_state(data):
    state,encoded = encode_state(data)
    if AUTH_DIR.is_symlink():
        raise SessionError('私有会话目录不可为符号链接')
    AUTH_DIR.mkdir(mode=0o700,parents=True,exist_ok=True)
    AUTH_DIR.chmod(0o700)
    for path,value in [(STATE_FILE,json.dumps(state,ensure_ascii=False,separators=(',',':'))),
                       (SECRET_FILE,encoded)]:
        # Restrictive permissions from creation, never a public-data directory.
        fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as output:
            output.write(value)
        path.chmod(0o600)
    return STATE_FILE,SECRET_FILE


def assert_24h(data):
    try:
        hours = float((data.get('props') or {}).get('meta',{}).get('hoursRange') or 0)
    except (TypeError,ValueError):
        hours = 0
    if not 24<=hours<=168:
        raise SessionError('当前会话未验证到 24 小时查看权限；可能已过期或权限不足，请本地重新登录并更新 Secret')
    return hours
