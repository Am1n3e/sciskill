import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rebuttal_desk.server import make_server
from rebuttal_desk.workspace import (
    WorkspaceError,
    init_workspace,
    load_workspace,
    rendered,
)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace"
        init_workspace(self.root)

    def mutate(self, change):
        path = self.root / "workspace.json"
        raw = json.loads(path.read_text())
        change(raw)
        path.write_text(json.dumps(raw))

    def test_template_and_non_overwriting_init(self):
        self.assertEqual(
            load_workspace(self.root)["reviews"][0]["concerns"][0]["response"][
                "source"
            ],
            "TBD\n",
        )
        with self.assertRaises(WorkspaceError):
            init_workspace(self.root)

    def test_path_escape_absolute_and_symlink(self):
        outside = Path(self.temp.name) / "secret.md"
        outside.write_text("PRIVATE")
        (self.root / "link.md").symlink_to(outside)
        for path in ["../secret.md", str(outside), "link.md"]:
            with self.subTest(path=path):
                self.mutate(lambda x, path=path: x["reviews"][0].update(document=path))
                with self.assertRaises(WorkspaceError):
                    load_workspace(self.root)

    def test_unknown_related_duplicate_and_schema(self):
        self.mutate(
            lambda x: x["reviews"][0]["concerns"][0].update(related=["missing"])
        )
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root)
        self.mutate(lambda x: x["reviews"][0]["concerns"][0].update(related=[]))
        self.mutate(
            lambda x: x["reviews"][0]["concerns"].append(x["reviews"][0]["concerns"][0])
        )
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root)

    def test_missing_file_and_limit(self):
        self.mutate(lambda x: x.update(presentation={"character_limit": True}))
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root)
        self.mutate(lambda x: x.update(presentation={"character_limit": 500}))
        (self.root / "analysis.md").unlink()
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root)

    def test_rendering_removes_active_content(self):
        payload = '<script>alert(1)</script><img src="https://example.com/pixel" onerror="bad()"><a href="javascript:bad()">x</a><p onclick="bad()">safe</p>'
        for suffix in [".html", ".md"]:
            html = rendered(payload, "review" + suffix)
            for forbidden in ["<script", "<img", "onclick", "javascript:", "onerror"]:
                self.assertNotIn(forbidden, html)
            self.assertIn("safe", html)

    def test_unrelated_workspaces_are_independent(self):
        other = Path(self.temp.name) / "another"
        init_workspace(other)
        (other / "review.md").write_text("Distinct review")
        self.assertNotEqual(
            load_workspace(self.root)["reviews"][0]["document"],
            load_workspace(other)["reviews"][0]["document"],
        )

    def test_profiles_keep_data_stable_and_configure_display(self):
        generic = load_workspace(self.root)
        self.mutate(lambda x: x.update(presentation={"profile": "openreview"}))
        openreview = load_workspace(self.root)
        self.assertEqual(generic["reviews"], openreview["reviews"])
        self.assertIsNone(generic["presentation"]["character_limit"])
        self.assertEqual(openreview["presentation"]["character_limit"], 10000)
        self.assertEqual(openreview["presentation"]["comment_layout"], "thread")
        self.mutate(
            lambda x: x.update(
                presentation={"profile": "openreview", "character_limit": 500}
            )
        )
        self.assertEqual(
            load_workspace(self.root)["presentation"]["character_limit"], 500
        )
        self.mutate(lambda x: x.update(presentation={"profile": "unknown"}))
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root)

    def test_comments_are_loaded_and_contained(self):
        self.mutate(
            lambda x: x["reviews"][0].update(
                comments=[
                    {
                        "id": "comment-1",
                        "label": "Author clarification",
                        "document": "analysis.md",
                    }
                ]
            )
        )
        self.assertIn(
            "Evidence",
            load_workspace(self.root)["reviews"][0]["comments"][0]["document"][
                "source"
            ],
        )
        self.mutate(
            lambda x: x["reviews"][0]["comments"][0].update(document="../outside.md")
        )
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root)

    def test_server_exposes_only_assets_and_validated_data(self):
        (self.root / "secret.txt").write_text("PRIVATE")
        server = make_server(self.root)
        self.addCleanup(server.server_close)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        for route in ["/", "/app.js", "/styles.css", "/workspace.json"]:
            with urlopen(base + route) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(
                    "frame-ancestors 'none'",
                    response.headers["Content-Security-Policy"],
                )
                self.assertNotIn(b"PRIVATE", response.read())
        for route in [
            "/secret.txt",
            "/review.md",
            "/../pyproject.toml",
            "/%2e%2e/secret.txt",
        ]:
            with self.subTest(route=route), self.assertRaises(HTTPError) as caught:
                urlopen(base + route)
            self.assertEqual(caught.exception.code, 404)
        with self.assertRaises(HTTPError) as caught:
            urlopen(
                Request(base + "/workspace.json", headers={"Host": "attacker.example"})
            )
        self.assertEqual(caught.exception.code, 403)
        (self.root / "review.md").write_text("Updated review")
        with urlopen(base + "/workspace.json") as response:
            self.assertIn(b"Updated review", response.read())


if __name__ == "__main__":
    unittest.main()
