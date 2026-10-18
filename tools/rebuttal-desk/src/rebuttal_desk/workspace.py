"""Manifest validation and safe, explicit document loading."""

import re
from datetime import datetime
from html import escape
from pathlib import Path

import bleach
import markdown
import yaml

from .annotations import annotation_markup
from .integrity import content_checksum


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
        path.suffix.lower() in {".md", ".txt", ".html", ".json", ".yaml", ".yml"},
        "Documents must be .md, .txt, .html, .json or .yaml",
    )
    require(path.is_file(), f"Missing document: {relative}")
    require(path.stat().st_size <= 2_000_000, f"Document too large: {relative}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeError as exc:
        raise WorkspaceError(f"Document must be UTF-8: {relative}") from exc


def structured_html(source, annotated=False):
    try:
        raw = yaml.safe_load(source)
    except yaml.YAMLError as exc:
        raise WorkspaceError("Structured document must be valid YAML") from exc
    require(isinstance(raw, dict), "Structured document must be an object")
    sections = raw.get("sections")
    require(isinstance(sections, list), "Structured document sections must be a list")
    blocks = []
    for section in sections:
        require(isinstance(section, dict), "Section must be an object")
        heading = text(section.get("heading"), "section heading")
        content = section.get("content")
        require(isinstance(content, str), "Section content must be text")
        require(
            isinstance(section.get("annotated_content", content), str),
            "Annotated content must be text",
        )
        try:
            marked, _ = annotation_markup(
                content, section.get("annotated_content", content)
            )
        except ValueError as exc:
            raise WorkspaceError(str(exc)) from exc
        body = markdown.markdown(
            marked if annotated else content, extensions=["tables", "fenced_code"]
        )
        blocks.append(
            '<div><strong class="note-content-field">'
            + escape(heading)
            + '</strong><div class="note-content-value markdown-rendered">'
            + body
            + "</div></div>"
        )
    if "reviewer_id" in raw or "content_checksum" in raw:
        require(
            raw.get("content_checksum") == content_checksum(sections),
            "Original review content checksum mismatch",
        )
    return "\n".join(blocks)


def rendered(source, filename, annotated=False):
    if filename.endswith((".json", ".yaml", ".yml")):
        html = structured_html(source, annotated)
    elif filename.endswith(".html"):
        html = source
    else:
        html = markdown.markdown(source, extensions=["tables", "fenced_code"])
    tags = {
        "mark",
        "div",
        "span",
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
        attributes={
            "a": ["href", "title"],
            "mark": ["class", "data-annotation-id", "data-annotation-type"],
            "div": ["class"],
            "span": ["class"],
            "strong": ["class"],
        },
        protocols={"http", "https", "mailto"},
        strip=True,
    )


def load_content(root, filename):
    source = document(root, filename)
    result = {"source": source, "html": rendered(source, filename)}
    if filename.endswith((".yaml", ".yml")):
        result["annotated_html"] = rendered(source, filename, annotated=True)
    return result


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


def validate_conversation(entries, review_id):
    by_id = {entry["id"]: entry for entry in entries}
    require(len(by_id) == len(entries), "Duplicate conversation IDs")
    for entry in entries:
        parent = entry["reply_to"]
        seen = {entry["id"]}
        while parent is not None and parent != review_id:
            require(parent in by_id, "Unknown conversation reply target")
            require(parent not in seen, "Cyclic conversation replies")
            seen.add(parent)
            parent = by_id[parent]["reply_to"]


def load_conversation(content):
    raw = yaml.safe_load(content["source"])
    entries = raw.get("conversation", []) if isinstance(raw, dict) else []
    require(isinstance(entries, list), "conversation must be a list")
    result = []
    for entry in entries:
        require(isinstance(entry, dict), "Conversation entry must be an object")
        kind = entry.get("type")
        require(
            kind in {"author_response", "reviewer_comment"}, "Invalid conversation type"
        )
        timestamp = text(entry.get("created_at"), "conversation timestamp")
        try:
            datetime.fromisoformat(timestamp)
        except ValueError as exc:
            raise WorkspaceError("Invalid conversation timestamp") from exc
        result.append(
            {
                "id": identifier(entry.get("id")),
                "label": text(entry.get("title"), "conversation title"),
                "author": text(entry.get("author"), "conversation author"),
                "type": kind,
                "created_at": timestamp,
                "reply_to": entry.get("reply_to"),
                "document": {"html": rendered(yaml.safe_dump(entry), "entry.yaml")},
            }
        )
    validate_conversation(result, raw.get("id") if isinstance(raw, dict) else None)
    result.sort(key=lambda entry: (entry["created_at"], entry["id"]))
    return result


def load_review(root, raw):
    require(isinstance(raw, dict), "Review must be an object")
    concerns = raw.get("concerns")
    require(isinstance(concerns, list), "concerns must be a list")
    comments = raw.get("comments", [])
    require(isinstance(comments, list), "comments must be a list")
    content = load_content(root, raw.get("document"))
    conversation = (
        load_conversation(content)
        if raw.get("document", "").endswith((".yaml", ".yml"))
        else []
    )
    structured = (
        yaml.safe_load(content["source"])
        if raw.get("document", "").endswith((".yaml", ".yml"))
        else {}
    )
    return {
        "document_id": structured.get("id", raw.get("id")),
        "comments": [load_comment(root, comment) for comment in comments]
        + conversation,
        "id": identifier(raw.get("id")),
        "label": text(raw.get("label"), "review label"),
        "document": content,
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
    manifest = root / "workspace.yaml"
    if not manifest.exists():
        manifest = root / "workspace.json"
    require(manifest.resolve().is_relative_to(root), "Manifest escapes workspace")
    require(manifest.is_file(), "Missing workspace.yaml")
    require(manifest.stat().st_size <= 2_000_000, "Manifest too large")
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except (UnicodeError, yaml.YAMLError) as exc:
        raise WorkspaceError("Workspace manifest must be UTF-8 YAML") from exc
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
    (root / "workspace.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
