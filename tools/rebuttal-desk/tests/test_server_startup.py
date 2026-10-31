"""Local viewer startup must not depend on reverse DNS availability."""

import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rebuttal_desk.server import make_server
from rebuttal_desk.workspace import init_workspace


class ServerStartupTests(unittest.TestCase):
    def test_loopback_bind_does_not_resolve_reverse_dns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            init_workspace(root)
            with (
                patch.object(
                    socket,
                    "getfqdn",
                    side_effect=AssertionError("Reverse DNS forbidden"),
                ),
                patch.object(
                    socket,
                    "gethostbyaddr",
                    side_effect=AssertionError("Reverse DNS forbidden"),
                ),
                make_server(root) as server,
            ):
                self.assertEqual(server.server_name, "localhost")
                self.assertEqual(server.server_address[0], "127.0.0.1")
                self.assertEqual(server.server_port, server.socket.getsockname()[1])
                self.assertGreater(server.server_port, 0)


if __name__ == "__main__":
    unittest.main()
