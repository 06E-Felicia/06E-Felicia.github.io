"""Static local preview: stdlib only, no scientific runtime or integration."""
import functools
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from simulation.preview import ROOT, HEALTH, PreviewHandler, bind_preview, check_assets, existing_preview


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.server, self.port = bind_preview(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:%d' % self.port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_assets_complete_without_importing_numpy(self):
        check_assets()
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, '项目文件不完整'):
                check_assets(Path(root))

    def test_loopback_and_same_project_reuse(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        self.assertTrue(existing_preview(self.port, ROOT))
        other, port = bind_preview(self.port)
        self.assertIsNone(other)
        self.assertEqual(port, self.port)
        with urlopen(self.base + HEALTH) as response:
            self.assertEqual(json.load(response)['root'], str(ROOT))

    def test_html_and_wasm_mime_no_stale_cache(self):
        for path, mime in [('/simulator.html', 'text/html'),
                           ('/assets/scripts/simulation-local-worker.js', 'application/javascript'),
                           ('/assets/vendor/pyodide/pyodide.asm.wasm', 'application/wasm')]:
            with urlopen(self.base + path) as response:
                self.assertEqual(response.headers.get_content_type(), mime)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
                self.assertTrue(response.read(16))

    def test_hidden_and_encoded_parent_paths_are_forbidden(self):
        for path in ('/.git/config', '/%2e%2e/%2e%2e/etc/passwd'):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(error.exception.code, 403)

    def test_unrelated_server_port_is_not_reused(self):
        with tempfile.TemporaryDirectory() as root:
            handler = functools.partial(PreviewHandler, directory=root)
            other = ThreadingHTTPServer(('127.0.0.1', 0), handler)
            thread = threading.Thread(target=other.serve_forever, daemon=True)
            thread.start()
            try:
                server, port = bind_preview(other.server_port)
                self.assertIsNotNone(server)
                self.assertNotEqual(port, other.server_port)
                server.server_close()
            finally:
                other.shutdown()
                other.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
