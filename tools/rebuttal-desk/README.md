# Rebuttal Desk — phase 1 checkpoint

A standalone Python package that launches its bundled local application shell. This checkpoint tests packaging and launch only; review loading, workspace schema, viewer extraction and editing are later phases.

```sh
uvx --from ./tools/rebuttal-desk rebuttal-desk --help
uvx --from ./tools/rebuttal-desk rebuttal-desk --version
uvx --from ./tools/rebuttal-desk rebuttal-desk view
# Headless / fixed port:
uvx --from ./tools/rebuttal-desk rebuttal-desk view --no-browser --port 8765
```

Paths above assume the repository root. An absolute package path works from any directory. The server binds only to 127.0.0.1 and prints its address; Ctrl-C stops it. Only two explicitly packaged assets are exposed, with no directory listings or workspace access. No runtime dependencies or CDN assets are needed. First-time package building may resolve its build backend through uv; cached installation then runs offline.

```sh
uv run --project tools/rebuttal-desk python -m unittest discover -s tools/rebuttal-desk/tests -v
uv build tools/rebuttal-desk
```

The subsequent viewer will preserve the existing local Rebuttal Desk concept. Input/loading contract and OpenReview renderer parity require review before phase 2. Editor/save support is phase 3, not implemented here. GPL-3.0-only, consistent with this repository.
