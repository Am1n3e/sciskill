"""Import content from a fully loaded OpenReview HTML capture."""

import re
from datetime import datetime
from pathlib import Path

import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify

from .workspace import identifier, require


class ContentDumper(yaml.SafeDumper):
    """Keep Markdown paragraphs readable in YAML."""


def string_value(dumper, value):
    return dumper.represent_scalar(
        "tag:yaml.org,2002:str", value, style="|" if "\n" in value else None
    )


ContentDumper.add_representer(str, string_value)


def write_yaml(path, value):
    path.write_text(
        yaml.dump(value, Dumper=ContentDumper, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def sections_from(container):
    sections = []
    for field in container.select(".note-content > div"):
        heading = field.find(class_="note-content-field", recursive=False)
        value = field.find(class_="note-content-value", recursive=False)
        if heading is None or value is None:
            continue
        for formula in value.select(".katex"):
            tex = formula.find("annotation", attrs={"encoding": "application/x-tex"})
            if tex is not None:
                formula.replace_with("$" + tex.get_text() + "$")
        sections.append(
            {
                "heading": heading.get_text().strip(),
                "content": markdownify(
                    str(value), heading_style="ATX", bullets="-"
                ).strip(),
            }
        )
    return sections


def timestamp_from(meta):
    field = meta.select_one(".created-date")
    require(field is not None, "Missing creation timestamp in captured discussion")
    original = field.get_text(" ", strip=True)
    match = re.search(r"\d{1,2} [A-Za-z]{3} \d{4}, \d{2}:\d{2}", original)
    require(match is not None, "Unrecognized creation timestamp")
    created = datetime.strptime(match.group(), "%d %b %Y, %H:%M")
    return created.isoformat(timespec="minutes"), original


def parse_comment(comment):
    heading = comment.find("div", class_="heading", recursive=False)
    meta = comment.find("div", class_="subheading", recursive=False)
    content = comment.find("div", class_="note-content-container", recursive=False)
    require(heading is not None and heading.h4 is not None, "Missing comment heading")
    require(
        meta is not None and content is not None, "Missing comment metadata or content"
    )
    author = meta.select_one(".signatures")
    kind = meta.select_one(".invitation")
    require(author is not None and kind is not None, "Missing comment author or type")
    parent = comment.find_parent("div", class_="note")
    parent_title = comment.find("div", class_="parent-title", recursive=False)
    reply_heading = parent_title.find("h5") if parent_title else None
    created, original = timestamp_from(meta)
    return {
        "id": identifier(comment.get("data-id")),
        "title": heading.h4.get_text(" ", strip=True),
        "author": author.get_text(" ", strip=True).removeprefix("by "),
        "source_type": kind.get_text(" ", strip=True),
        "created_at": created,
        "timestamp_text": original,
        "reply_to": parent.get("data-id") if parent else None,
        "reply_title": reply_heading.get_text(" ", strip=True).removeprefix(
            "Replying to "
        )
        if reply_heading
        else None,
        "sections": sections_from(content),
    }


def reviewer_identity(author):
    match = re.match(r"(Reviewer|Action Editor|Area Chair)\s+([A-Za-z0-9_-]+)", author)
    require(match is not None, f"Unrecognized review author: {author}")
    return match.group(2), f"{match.group(1)} {match.group(2)}"


def normalized(value):
    return " ".join(value.split())


def resolve_replies(comments):
    for comment in comments:
        title = comment.pop("reply_title")
        if title is None:
            continue
        matches = [
            c
            for c in comments
            if normalized(c["title"]) == normalized(title) and c["id"] != comment["id"]
        ]
        require(len(matches) == 1, f"Cannot resolve reply target for {comment['id']}")
        comment["reply_to"] = matches[0]["id"]


def review_for(comment, by_id, reviews):
    current = comment
    visited = set()
    while current["reply_to"]:
        require(current["id"] not in visited, "Cyclic reply relationship")
        visited.add(current["id"])
        parent_id = current["reply_to"]
        require(parent_id in by_id, "Missing reply target")
        current = by_id[parent_id]
        if current["id"] in reviews:
            return current["id"]
    author_id, _ = reviewer_identity(current["author"])
    matches = [
        key for key, review in reviews.items() if review["reviewer_id"] == author_id
    ]
    require(len(matches) == 1, "Cannot associate discussion thread with a review")
    return matches[0]


def build_reviews(comments):
    reviews = {}
    for comment in comments:
        if comment["source_type"] not in {
            "Review",
            "Decision",
            "Official Review",
            "Meta Review",
        }:
            continue
        reviewer_id, label = reviewer_identity(comment["author"])
        reviews[comment["id"]] = {
            **comment,
            "reviewer_id": reviewer_id,
            "author": label,
            "conversation": [],
        }
    require(bool(reviews), "No OpenReview reviews or decisions found")
    by_id = {c["id"]: c for c in comments}
    for comment in comments:
        if comment["id"] in reviews:
            continue
        review = reviews[review_for(comment, by_id, reviews)]
        kind = (
            "author_response" if comment["author"] == "Authors" else "reviewer_comment"
        )
        entry = {**comment, "type": kind}
        if kind == "reviewer_comment":
            _, entry["author"] = reviewer_identity(comment["author"])
        review["conversation"].append(entry)
    for review in reviews.values():
        review["conversation"].sort(key=lambda c: (c["created_at"], c["id"]))
    return list(reviews.values())


def import_openreview(html_file, directory):
    root = Path(directory)
    require(not root.exists(), "Workspace already exists; nothing overwritten")
    source = Path(html_file)
    require(source.is_file(), "Missing HTML input")
    require(source.stat().st_size <= 20_000_000, "HTML input exceeds 20 MB")
    soup = BeautifulSoup(source.read_text(encoding="utf-8"), "html.parser")
    title = soup.select_one("#content h2") or soup.find("h2")
    require(title is not None, "Missing paper title")
    comments = [parse_comment(n) for n in soup.select("#forum-replies .note[data-id]")]
    require(
        bool(comments), "No loaded discussion comments found; capture the rendered page"
    )
    require(len({c["id"] for c in comments}) == len(comments), "Duplicate comment IDs")
    resolve_replies(comments)
    reviews = build_reviews(comments)
    require(
        len({r["reviewer_id"] for r in reviews}) == len(reviews),
        "Duplicate reviewer IDs",
    )
    manifest = {
        "version": 1,
        "source": "openreview",
        "title": title.get_text(" ", strip=True),
        "presentation": {"character_limit": 10000},
        "reviews": [
            {
                "id": r["reviewer_id"],
                "label": r["author"],
                "document": f"reviews/{r['id']}.yaml",
                "concerns": [],
            }
            for r in reviews
        ],
    }
    root.mkdir(parents=True)
    (root / "reviews").mkdir()
    for review in reviews:
        write_yaml(root / "reviews" / f"{review['id']}.yaml", review)
    write_yaml(root / "workspace.yaml", manifest)
    return len(comments), len(reviews)
