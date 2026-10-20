"""Probe ONE real airport board; never publish guessed records or credentials."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from .client import Client, MCPError
from .private_key import KeyErrorSafe


def schema_summary(value, depth=0):
    if depth >= 5:
        return type(value).__name__
    if isinstance(value, dict):
        return {str(k)[:64]: schema_summary(v, depth + 1) for k, v in list(value.items())[:35]}
    if isinstance(value, list):
        return {'type': 'list', 'length': len(value), 'item': schema_summary(value[0], depth + 1) if value else None}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            return 'str'
        return {'type': 'JSON string', 'schema': schema_summary(parsed, depth + 1)}
    return type(value).__name__


def run(airport='SZX', direction='1'):
    client = Client()
    try:
        client.initialize()
        tool = client.discover_board()
        print('MCP 初始化和机场大屏工具发现成功；没有记录密钥。', flush=True)
        print('工具参数定义：' + json.dumps(tool.get('inputSchema'), ensure_ascii=False), flush=True)
        result = client.get_board(airport, direction)
        print('机场大屏真实调用成功。响应结构（不输出字段值）：', flush=True)
        print(json.dumps(schema_summary(result), ensure_ascii=False, indent=2), flush=True)
        # Raw provider data is held only in a new private temporary directory,
        # not under a Git/Pages root. Inspect before writing any public adapter.
        directory = Path(tempfile.mkdtemp(prefix='feimadat-probe-'))
        os.chmod(directory, 0o700)
        target = directory / 'board.json'
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(result, output, ensure_ascii=False)
        print('真实响应已暂存于私有目录：' + str(target), flush=True)
        print('尚未发布航班快照。将按这份实际响应完成字段映射后再展示。', flush=True)
        return 0
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--airport', default='SZX')
    parser.add_argument('--out', choices=['0', '1'], default='1')
    arguments = parser.parse_args()
    try:
        raise SystemExit(run(arguments.airport.upper(), arguments.out))
    except (MCPError, KeyErrorSafe) as error:
        print(str(error))
        raise SystemExit(1)
