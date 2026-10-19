"""Open completed native Astra test snapshots; stdlib only, never integrate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import webbrowser
from .preview import ROOT,bind_preview

ARCHIVE=ROOT/'local-test-results/astra'
PAGE='simulation/test-replay.html'


def validate_archive(directory=ARCHIVE):
    directory=Path(directory).resolve()
    try:
        data=json.loads((directory/'index.json').read_text(encoding='utf8'))
    except (OSError,ValueError) as error:
        raise RuntimeError('未找到已完成的 Astra 测试快照。请先完成测试并导出本地回放；启动器不会重新随机计算。') from error
    if data.get('schema')!='stormsim-astra-test-v1' or data.get('status')!='complete' or not data.get('cases'):
        raise RuntimeError('测试快照清单未完成，不能回放。')
    seen=set()
    for case in data['cases']:
        name=case.get('file','')
        if not re.fullmatch(r'astra-\d+\.json',name) or name in seen:
            raise RuntimeError('测试快照路径无效。')
        seen.add(name);path=directory/name
        if path.resolve().parent!=directory or not path.is_file():
            raise RuntimeError('测试快照缺失：'+name)
        if not re.fullmatch(r'[a-f0-9]{64}',case.get('sha256','')):
            raise RuntimeError('测试快照摘要无效。')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=case['sha256']:
            raise RuntimeError('测试快照校验失败：'+name+'；请重新导出，不要混用其他轮结果。')
    return data


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('端口须为 1–65535')
    try:
        data=validate_archive()
        for name in [PAGE,'assets/scripts/simulation-test-replay.js','assets/styles/simulation-test-replay.css',
                     'assets/vendor/leaflet/leaflet.js','assets/vendor/leaflet/leaflet.css']:
            if not (ROOT/name).is_file():raise RuntimeError('回放页面文件缺失：'+name)
    except RuntimeError as error:parser.exit(1,str(error)+'\n')
    print('已校验 %d 轮 Astra 实际测试；直接读取已保存结果，不重新计算。'%len(data['cases']),flush=True)
    if args.check:return
    server,port=bind_preview(args.port)
    url='http://127.0.0.1:%d/%s'%(port,PAGE)
    print('Astra 测试复现：'+url,flush=True)
    print('仅本机可用；保持此终端打开，退出按 Control+C。',flush=True)
    if not args.no_open:webbrowser.open(url)
    if server is None:
        print('已复用同一项目的本地预览服务。',flush=True);return
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()


if __name__=='__main__':main()
