"""Command-line interface."""

import argparse
import webbrowser

from .server import make_server
from .workspace import init_workspace, load_workspace


def main():
    parser = argparse.ArgumentParser(prog="rebuttal-desk")
    parser.add_argument("--version", action="version", version="rebuttal-desk 0.1.0")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init", help="Create a synthetic template in a new directory"
    ).add_argument("workspace")
    commands.add_parser(
        "validate", help="Validate manifest, documents and links"
    ).add_argument("workspace")
    view = commands.add_parser("view", help="Open a read-only local review viewer")
    view.add_argument("workspace")
    view.add_argument("--port", type=int, default=0)
    view.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"rebuttal-desk: {exc}\n")


def run(args):
    if args.command == "init":
        init_workspace(args.workspace)
        print("Created synthetic workspace template.")
    elif args.command == "validate":
        workspace = load_workspace(args.workspace)
        print(f"Valid: {len(workspace['reviews'])} reviews.")
    else:
        with make_server(args.workspace, args.port) as server:
            url = f"http://127.0.0.1:{server.server_port}/"
            print(url, flush=True)
            if not args.no_browser:
                webbrowser.open(url)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
