"""Loopback-only static preview. No simulation dependencies or external service."""
import argparse
import errno
import functools
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
HEALTH = '/__stormsim_preview__'
REQUIRED = (
    'simulator.html', 'simulator-sol.html', 'simulation/__init__.py',
    'simulation/core.py', 'simulation/coldpool.py', 'simulation/precipitation.py', 'simulation/synoptic.py', 'simulation/numerics.py',
    'simulation/thermo.py', 'simulation/terrain.py', 'simulation/run.py',
    'simulation/config.json', 'simulation/experiment.py', 'simulation/browser.py',
    'assets/scripts/simulation-local-worker.js', 'assets/scripts/simulation-advection.js',
    'assets/scripts/simulation-v2.js', 'assets/scripts/simulation-data.js',
    'assets/scripts/simulation-frame-store.js', 'assets/styles/simulation-v2.css',
    'assets/vendor/leaflet/leaflet.js', 'assets/vendor/leaflet/leaflet.css',
    'assets/data/simulation-terrain.npz', 'assets/data/simulation-terrain-detail.npz',
    'assets/data/simulator-stations.json', 'assets/vendor/pyodide/pyodide.js',
    'assets/vendor/pyodide/pyodide.asm.js', 'assets/vendor/pyodide/pyodide.asm.wasm',
    'assets/vendor/pyodide/python_stdlib.zip', 'assets/vendor/pyodide/pyodide-lock.json',
)


def check_assets(root=ROOT):
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    lock = root / 'assets/vendor/pyodide/pyodide-lock.json'
    if lock.is_file():
        packages = json.loads(lock.read_text())['packages']
        for name in ('numpy', 'scipy', 'libopenblas'):
            package = 'assets/vendor/pyodide/' + packages[name]['file_name']
            if not (root / package).is_file():
                missing.append(package)
    if missing:
        raise RuntimeError('项目文件不完整，请补齐：\n' + '\n'.join(missing))


class PreviewHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      '.js': 'application/javascript', '.wasm': 'application/wasm',
                      '.whl': 'application/octet-stream'}

    def end_headers(self):
        # Local source edits must not mix cached UI/Worker/Python versions.
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def allowed(self):
        parts = Path(unquote(urlsplit(self.path).path)).parts
        target = Path(self.translate_path(self.path)).resolve()
        root = Path(self.directory).resolve()
        return not any(part.startswith('.') for part in parts) and (target == root or root in target.parents)

    def do_GET(self):
        if urlsplit(self.path).path == HEALTH:
            body = json.dumps({'app': 'stormsim-preview', 'root': str(Path(self.directory).resolve())}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if not self.allowed():
            self.send_error(403)
            return
        try:
            super().do_GET()
        except (BrokenPipeError, ConnectionResetError):
            pass  # A cancelled browser download is not a server failure.

    def do_HEAD(self):
        if not self.allowed():
            self.send_error(403)
            return
        super().do_HEAD()


def existing_preview(port, root):
    try:
        with urlopen('http://127.0.0.1:%d%s' % (port, HEALTH), timeout=.5) as response:
            data = json.load(response)
        return data.get('app') == 'stormsim-preview' and data.get('root') == str(root.resolve())
    except (OSError, URLError, ValueError):
        return False


def bind_preview(port=8765, root=ROOT):
    handler = functools.partial(PreviewHandler, directory=str(root))
    for candidate in range(port, min(port + 20, 65536)):
        try:
            server = ThreadingHTTPServer(('127.0.0.1', candidate), handler)
            return server, server.server_port
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            if existing_preview(candidate, root):
                return None, candidate
    raise RuntimeError('本地预览端口均被占用，请使用 --port 指定其他端口。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--check', action='store_true', help='Only verify bundled runtime assets')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('端口须为 1–65535')
    check_assets()
    if args.check:
        print('PASS 本地运行时、科学包、地形及站表齐全')
        return
    server, port = bind_preview(args.port)
    url = 'http://127.0.0.1:%d/simulator.html' % port
    print('StormSim 本地预览：' + url, flush=True)
    print('保持此终端窗口打开；结束预览按 Control+C。仅监听本机，不对外开放。', flush=True)
    if not args.no_open:
        webbrowser.open(url)
    if server is None:
        print('已复用同一项目的预览服务。')
        return
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
