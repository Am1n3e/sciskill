"""Manifest validation and safe, explicit document loading."""

import json
import re
from pathlib import Path

import bleach
import markdown


class WorkspaceError(ValueError):
    """Invalid workspace configuration or document."""


def require(condition, message):
    if not condition:
        raise WorkspaceError(message)


def text(value, field):
    require(
        isinstance(value, str) and bool(value.strip()), f"{field} must be nonempty text"
    )
    return value


def identifier(value):
    text(value, "id")
    require(
        bool(re.fullmatch(r"[A-Za-z0-9_-]+", value)), "IDs use letters, digits, _ or -"
    )
    return value


def document(root, relative):
    text(relative, "document path")
    require(not Path(relative).is_absolute(), "Document paths must be relative")
    path = (root / relative).resolve()
    require(path.is_relative_to(root), "Document path escapes workspace")
    require(
        path.suffix.lower() in {".md", ".txt", ".html"},
        "Documents must be .md, .txt or .html",
    )
    require(path.is_file(), f"Missing document: {relative}")
    require(path.stat().st_size <= 2_000_000, f"Document too large: {relative}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise WorkspaceError(f"Document must be UTF-8: {relative}") from exc


def rendered(source, filename):
    if filename.endswith(".html"):
        html = source
    else:
        html = markdown.markdown(source, extensions=["tables", "fenced_code"])
    tags = {
        "p",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "ul",
        "ol",
        "li",
        "strong",
        "em",
        "code",
        "pre",
        "blockquote",
        "a",
        "hr",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
    }
    return bleach.clean(
        html,
        tags=tags,
        attributes={"a": ["href", "title"]},
        protocols={"http", "https", "mailto"},
        strip=True,
    )


def load_content(root, filename):
    source = document(root, filename)
    return {"source": source, "html": rendered(source, filename)}


def load_concern(root, raw):
    require(isinstance(raw, dict), "Concern must be an object")
    related = raw.get("related", [])
    require(
        isinstance(related, list) and all(isinstance(x, str) for x in related),
        "related must be a list of concern IDs",
    )
    return {
        "id": identifier(raw.get("id")),
        "title": text(raw.get("title"), "concern title"),
        "question": text(raw.get("question", raw.get("title")), "concern question"),
        "related": related,
        "analysis": load_content(root, raw.get("analysis")),
        "response": load_content(root, raw.get("response")),
    }


def load_comment(root, raw):
    require(isinstance(raw, dict), "Comment must be an object")
    return {
        "id": identifier(raw.get("id")),
        "label": text(raw.get("label"), "comment label"),
        "document": load_content(root, raw.get("document")),
    }


def presentation(raw):
    require(isinstance(raw, dict), "presentation must be an object")
    require(
        not set(raw) - {"character_limit"},
        "Only character_limit is configurable in presentation",
    )
    limit = raw.get("character_limit", 10000)
    require(
        limit is None or (type(limit) is int and limit > 0),
        "character_limit must be positive or null",
    )
    return {"character_limit": limit}


def load_review(root, raw):
    require(isinstance(raw, dict), "Review must be an object")
    concerns = raw.get("concerns")
    require(isinstance(concerns, list), "concerns must be a list")
    comments = raw.get("comments", [])
    require(isinstance(comments, list), "comments must be a list")
    return {
        "comments": [load_comment(root, comment) for comment in comments],
        "id": identifier(raw.get("id")),
        "label": text(raw.get("label"), "review label"),
        "document": load_content(root, raw.get("document")),
        "concerns": [load_concern(root, c) for c in concerns],
    }


def validate_links(reviews):
    ids = [c["id"] for r in reviews for c in r["concerns"]]
    require(len(ids) == len(set(ids)), "Concern IDs must be globally unique")
    review_ids = [r["id"] for r in reviews]
    require(len(review_ids) == len(set(review_ids)), "Review IDs must be unique")
    for review in reviews:
        for concern in review["concerns"]:
            require(
                all(link in ids for link in concern["related"]),
                f"Unknown related concern in {concern['id']}",
            )


def load_workspace(directory):
    root = Path(directory).resolve()
    manifest = root / "workspace.json"
    require(manifest.resolve().is_relative_to(root), "Manifest escapes workspace")
    require(manifest.is_file(), "Missing workspace.json")
    require(manifest.stat().st_size <= 2_000_000, "Manifest too large")
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WorkspaceError("workspace.json must be UTF-8 JSON") from exc
    require(isinstance(raw, dict), "Manifest must be an object")
    require(
        type(raw.get("version")) is int and raw.get("version") == 1,
        "Manifest version must be 1",
    )
    display = presentation(raw.get("presentation", {}))
    require(
        isinstance(raw.get("reviews"), list) and bool(raw["reviews"]),
        "reviews must be a nonempty list",
    )
    reviews = [load_review(root, r) for r in raw["reviews"]]
    validate_links(reviews)
    return {
        "title": text(raw.get("title"), "title"),
        "presentation": display,
        "reviews": reviews,
    }


def init_workspace(directory):
    root = Path(directory)
    require(not root.exists(), "Workspace already exists; nothing overwritten")
    root.mkdir(parents=True)
    files = {
        "review.md": "# Reviewer 1\n\nPlease clarify which measurements support the comparison.\n",
        "analysis.md": "# Evidence to gather\n\nCheck the measurement protocol and identify the relevant table.\n",
        "response.md": "TBD\n",
    }
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
    manifest = {
        "version": 1,
        "title": "Example review workspace",
        "presentation": {"character_limit": 10000},
        "reviews": [
            {
                "id": "reviewer-1",
                "label": "Reviewer 1",
                "document": "review.md",
                "concerns": [
                    {
                        "id": "concern-1",
                        "title": "Explain the measurements",
                        "analysis": "analysis.md",
                        "response": "response.md",
                        "related": [],
                    }
                ],
            }
        ],
    }
    (root / "workspace.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
