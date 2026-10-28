#!/usr/bin/env python3
"""Serve the repository locally and open Vacation.html; Python standard library only."""
import functools
import http.server
import signal
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()


def main():
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(ROOT)))
    url = f'http://127.0.0.1:{server.server_port}/Vacation.html'
    print('放假模拟器：' + url, flush=True)
    print('关闭此窗口或按 Ctrl+C 停止预览。', flush=True)
    threading.Timer(.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
