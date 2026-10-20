"""Small Streamable HTTP MCP client, confined to the official VariFlight host.

Only reads airport boards and flight-status details. Never logs credentials or provider bodies.
"""
import json
import re
from datetime import date as calendar_date
import urllib.error
import urllib.request

from .private_key import load_key

ENDPOINT = 'https://c-gw.variflight.com/chat_message/mcp/api'
MAX_RESPONSE = 8 * 1024 * 1024
PROTOCOLS = {'2024-11-05', '2025-03-26', '2025-06-18', '2025-11-25'}


class MCPError(RuntimeError):
    """Messages in this exception are deliberately safe for terminal output."""
    def __init__(self, message, http_status=None):
        super().__init__(message)
        self.http_status = http_status


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise MCPError('接口发生重定向，已停止，避免将密钥发送到其他地址')


def _matching_result(message, request_id):
    messages = message if isinstance(message, list) else [message]
    for item in messages:
        if not isinstance(item, dict) or item.get('id') != request_id:
            continue
        if 'error' in item:
            error = item['error']
            code = error.get('code') if isinstance(error, dict) else None
            code = code if type(code) is int else '未知'
            raise MCPError('MCP 请求失败，错误码 %s；未输出服务端正文' % code)
        if 'result' not in item or not isinstance(item['result'], dict):
            raise MCPError('MCP 响应缺少有效 result，未更新航班数据')
        return item['result']
    return None


def read_result(response, request_id):
    content_type = response.headers.get_content_type()
    if content_type == 'application/json':
        raw = response.read(MAX_RESPONSE + 1)
        if len(raw) > MAX_RESPONSE:
            raise MCPError('接口响应超过安全大小限制')
        try:
            result = _matching_result(json.loads(raw), request_id)
        except (ValueError, UnicodeError):
            raise MCPError('接口返回了无效 JSON，未更新航班数据') from None
        if result is None:
            raise MCPError('MCP 响应 ID 不匹配，未更新航班数据')
        return result
    if content_type != 'text/event-stream':
        raise MCPError('接口响应类型不是 JSON 或 SSE，未更新航班数据')
    size, event = 0, []
    while True:
        line = response.readline(MAX_RESPONSE + 1)
        size += len(line)
        if size > MAX_RESPONSE:
            raise MCPError('接口 SSE 响应超过安全大小限制')
        if not line or line.strip() == b'':
            if event:
                try:
                    result = _matching_result(json.loads(b'\n'.join(event)), request_id)
                except (ValueError, UnicodeError):
                    raise MCPError('接口返回了无效 SSE 数据，未更新航班数据') from None
                if result is not None:
                    return result  # Do not wait for a long-lived stream to close.
                event = []
            if not line:
                break
        elif line.startswith(b'data:'):
            event.append(line[5:].lstrip(b' ').rstrip(b'\r\n'))
    raise MCPError('SSE 流结束前没有取得本次请求的结果')


class Client:
    def __init__(self, key=None, opener=None, timeout=40):
        self._key = load_key() if key is None else key
        self._opener = opener or urllib.request.build_opener(NoRedirect())
        self.timeout = timeout
        self._request_id = 0
        self._session = None
        self.protocol = None
        self.board_tool = None
        self._tools = {}
        self._catalog_loaded = False

    def _request(self, method, params=None, notification=False):
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        if not notification:
            self._request_id += 1
            payload['id'] = self._request_id
        headers = {'Authorization': 'Bearer ' + self._key,
                   'Accept': 'application/json, text/event-stream',
                   'Content-Type': 'application/json', 'User-Agent': 'Feimadat/1.0'}
        if self._session:
            headers['Mcp-Session-Id'] = self._session
        if self.protocol:
            headers['MCP-Protocol-Version'] = self.protocol
        request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if notification:
                    return None
                result = read_result(response, payload['id'])
                if method == 'initialize':
                    sid = response.headers.get('Mcp-Session-Id')
                    if sid:
                        if len(sid) > 4096 or any(not 33 <= ord(c) <= 126 for c in sid):
                            raise MCPError('服务端会话标识无效')
                        self._session = sid
                return result
        except MCPError:
            raise
        except urllib.error.HTTPError as error:
            if error.code in (401, 403):
                raise MCPError('飞常准拒绝授权（HTTP %s），请核对 MCP Key、工具权限和账户额度' % error.code, error.code) from None
            if error.code == 429:
                raise MCPError('飞常准请求限流（HTTP 429），已停止，不自动重试', 429) from None
            raise MCPError('飞常准接口返回 HTTP %s，未输出响应正文' % error.code) from None
        except Exception:
            raise MCPError('飞常准网络请求未完成，未更新航班数据；未输出凭据或服务端正文') from None

    def initialize(self):
        result = self._request('initialize', {'protocolVersion': '2025-03-26',
            'capabilities': {}, 'clientInfo': {'name': 'Feimadat', 'version': '1.0'}})
        protocol = result.get('protocolVersion')
        if protocol not in PROTOCOLS:
            raise MCPError('接口协商了尚未支持的 MCP 协议版本，需要核验后再接入')
        self.protocol = protocol
        self._request('notifications/initialized', notification=True)
        return result

    def discover_tool(self, name):
        if name in self._tools:
            return self._tools[name]
        if self._catalog_loaded:
            raise MCPError('当前账号未提供 %s 工具，请检查产品和权限' % name)
        cursor, seen = None, set()
        for _ in range(10):
            result = self._request('tools/list', {'cursor': cursor} if cursor else {})
            tools = result.get('tools')
            if not isinstance(tools, list):
                raise MCPError('工具目录结构不正确，未猜测调用地址')
            for tool in tools:
                if isinstance(tool, dict) and isinstance(tool.get('name'), str):
                    self._tools[tool['name']] = tool
            cursor = result.get('nextCursor')
            if not cursor:
                break
            if not isinstance(cursor, str) or cursor in seen:
                raise MCPError('工具目录分页重复或无效')
            seen.add(cursor)
        self._catalog_loaded = True
        if name not in self._tools:
            raise MCPError('当前账号未提供 %s 工具，请检查产品和权限' % name)
        return self._tools[name]

    def discover_board(self):
        self.board_tool = self.discover_tool('getAirportFlightBoard')
        return self.board_tool

    def get_status(self, date, dep, arr, fnum=None):
        """One documented route query can supply several flights; no hidden API."""
        try:
            if calendar_date.fromisoformat(date).isoformat() != date:
                raise ValueError
        except (ValueError, TypeError):
            raise MCPError('航班查询日期不正确') from None
        if any(not isinstance(code, str) or not re.fullmatch(r'[A-Z]{3}', code) for code in (dep, arr)):
            raise MCPError('航班查询机场不正确')
        arguments = {'date': date, 'dep': dep, 'arr': arr}
        if fnum is not None:
            if not re.fullmatch(r'[A-Z0-9]{2}\d{1,5}[A-Z]?', fnum):
                raise MCPError('航班号不正确')
            arguments['fnum'] = fnum
        tool = self.discover_tool('getFlightStatus')
        if any(key not in arguments for key in (tool.get('inputSchema') or {}).get('required', [])):
            raise MCPError('航班详情新增必填参数，需要核验后再调用')
        result = self._request('tools/call', {'name': 'getFlightStatus', 'arguments': arguments})
        if result.get('isError'):
            raise MCPError('航班详情返回业务错误；未输出服务端正文')
        return result

    def get_board(self, airport='SZX', direction='1'):
        if not re.fullmatch(r'[A-Z]{3}', airport) or direction not in ('0', '1'):
            raise MCPError('机场或进出港参数不正确')
        if not self.board_tool:
            self.discover_board()
        arguments = {'local': airport, 'out': direction}
        schema = self.board_tool.get('inputSchema') or {}
        if any(name not in arguments for name in schema.get('required', [])):
            raise MCPError('工具新增了必填参数，需要按实际文档核验后再调用')
        result = self._request('tools/call', {'name': 'getAirportFlightBoard', 'arguments': arguments})
        if result.get('isError'):
            raise MCPError('机场大屏返回业务错误，请检查账号权限或配额；未输出可能含敏感信息的正文')
        return result

    def close(self):
        # Session expiry is controlled by the service. No cancellation,
        # account mutation, unknown tool or additional network request here.
        self._key = ''
        self._session = None
