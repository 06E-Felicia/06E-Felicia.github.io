"""Open the finished image replay directly; no server and no reintegration."""
import argparse
import functools
import http.server
import hashlib
import json
from pathlib import Path
import webbrowser
ROOT=Path(__file__).resolve().parents[2]
archive=ROOT/'simulation/vacation-replays'
try:
    pointer=json.loads((archive/'latest.json').read_text())
    directory=(archive/pointer['directory']).resolve()
    if directory.parent!=archive.resolve():raise ValueError('无效回放路径')
    raw=(directory/'manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pointer['manifestSha256']:raise ValueError('回放清单校验失败')
    manifest=json.loads(raw)
    if manifest['status']!='complete' or manifest['renderStatus']!='complete' or manifest.get('verificationStatus')!='complete':raise ValueError('回放尚未完成')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-open',action='store_true')
    args=parser.parse_args()
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(ROOT))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    url='http://127.0.0.1:%d/VacationReplay.html'%server.server_port
    print('完整回放：'+url,flush=True)
    print('直接读取已归档过程；关闭窗口停止本地服务。',flush=True)
    if not args.no_open:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
except (OSError,ValueError,KeyError) as error:
    raise SystemExit('无法打开归档，请先运行“development/launchers/生成放假模拟回放.command”：'+str(error))
