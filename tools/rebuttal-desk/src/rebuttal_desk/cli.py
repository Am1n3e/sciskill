"""Rebuttal Desk launch checkpoint."""

import argparse
import webbrowser

from .server import make_server


def main():
    parser = argparse.ArgumentParser(prog="rebuttal-desk")
    parser.add_argument("--version", action="version", version="rebuttal-desk 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    view = commands.add_parser("view", help="Launch the local application shell")
    view.add_argument("--port", type=int, default=0)
    view.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        with make_server(args.port) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print(url, flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except (ValueError, OSError) as exc:
        parser.exit(2, f"rebuttal-desk: {exc}\n")
