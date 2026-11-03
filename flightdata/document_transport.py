"""Optional FR24 document transport using only the user's scoped session."""
import http.cookiejar
import json
import random
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlsplit


class _FR24Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urlsplit(newurl)
        if url.scheme != 'https' or url.hostname != 'www.flightradar24.com' or url.port not in (None, 443):
            raise RuntimeError('源站重定向到非预期地址，停止采集')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _Island(HTMLParser):
    def __init__(self):
        super().__init__()
        self.raw = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get('id') == 'app' and attrs.get('data-page'):
            self.raw = attrs['data-page']
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])


class DocumentTransport:
    def __init__(self, state, access_error):
        self.access_error = access_error
        self._request_sent = False
        jar = http.cookiejar.CookieJar()
        for item in (state or {}).get('cookies', []):
            # urllib has no partition-key support; do not broaden cookie scope.
            if item.get('partitionKey'):
                continue
            expiry = item.get('expires')
            expiry = int(expiry) if expiry and expiry > 0 else None
            jar.set_cookie(http.cookiejar.Cookie(
                0, item['name'], item['value'], None, False, item['domain'], True,
                item['domain'].startswith('.'), item.get('path', '/'), True,
                item.get('secure', False), expiry, expiry is None, None, None, {}, False))
        self.opener = urllib.request.build_opener(_FR24Redirect(), urllib.request.HTTPCookieProcessor(jar))
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5', 'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'none',
        }

    def get(self, url, airport):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'www.flightradar24.com' or parsed.port not in (None, 443):
            raise RuntimeError('无效的官网链接')
        # Space every request, including the first page of a different board.
        if self._request_sent:
            time.sleep(random.uniform(3.5, 4.0))
        self._request_sent = True
        try:
            response = self.opener.open(urllib.request.Request(url, headers=self.headers), timeout=45)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            wrapped = SimpleNamespace(status=response.status, headers=headers,
                                      request=SimpleNamespace(resource_type='document', headers={}))
            if response.status in (401, 403, 429):
                raise self.access_error(wrapped, f'源站拒绝访问 HTTP {response.status}；停止本轮采集')
            if response.status >= 400:
                raise RuntimeError(f'源站返回 HTTP {response.status}')
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise RuntimeError('源站响应过大')
        parser = _Island()
        parser.feed(body.decode('utf-8', 'replace'))
        if not parser.raw:
            text = body[:4096].decode('utf-8', 'replace').lower()
            if 'just a moment' in text or 'attention required' in text:
                raise self.access_error(wrapped, '源站显示访问验证；停止本轮采集')
            raise RuntimeError('服务器响应未包含航班数据岛')
        data = json.loads(parser.raw)
        props = data.get('props') if isinstance(data, dict) else None
        if not isinstance(props, dict) or not isinstance(props.get('flights'), list):
            raise RuntimeError('数据岛缺少 flights 列表')
        got = ((props.get('airport') or {}).get('iata') or '').upper()
        if got and got != airport['iata'].upper():
            raise RuntimeError(f'机场不匹配：{got}')
        data['_pagination_links'] = parser.links
        return data

    def first(self, board, airport):
        return self.get(f"https://www.flightradar24.com/data/airports/{airport['iata'].lower()}/{board}", airport)

    def next(self, board, airport, previous):
        base = f"https://www.flightradar24.com/data/airports/{airport['iata'].lower()}/{board}"
        next_page = str((previous['props'].get('meta') or {}).get('nextPage') or '')
        for href in previous.get('_pagination_links', []):
            target = urljoin(base, href)
            parsed = urlsplit(target)
            if (next_page and parsed.scheme == 'https' and parsed.hostname == 'www.flightradar24.com'
                    and parsed.port in (None, 443) and parsed.path.rstrip('/') == urlsplit(base).path
                    and parse_qs(parsed.query).get('page') == [next_page]):
                data = self.get(target, airport)
                if data['props']['flights'] and data['props']['flights'] == previous['props']['flights']:
                    raise RuntimeError('分页重复返回上一页数据')
                return data
        raise RuntimeError('服务器响应没有下一页官网链接')
