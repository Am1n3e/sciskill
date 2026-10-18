import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rebuttal_desk.server import make_server


class ShellTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server()
        self.addCleanup(self.server.server_close)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def test_packaged_assets(self):
        for route in ["/", "/styles.css"]:
            with urlopen(self.base + route) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
                self.assertIn(
                    "frame-ancestors 'none'",
                    response.headers["Content-Security-Policy"],
                )

    def test_no_filesystem_or_workspace_routes(self):
        for route in ["/workspace.json", "/../pyproject.toml", "/secret.txt"]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(self.base + route)
            self.assertEqual(caught.exception.code, 404)

    def test_host_restriction(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base, headers={"Host": "untrusted.example"}))
        self.assertEqual(caught.exception.code, 403)
