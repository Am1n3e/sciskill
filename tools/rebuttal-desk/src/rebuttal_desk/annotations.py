"""Validate exact-preserving annotation wrappers and expose safe highlights."""

import re
from html import escape
from html.parser import HTMLParser

TAG = re.compile(r"<(/?)science-skills-annotation\b([^>]*)>")


class Attributes(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attributes = attrs


def annotation_attributes(tag):
    parser = Attributes()
    parser.feed(tag)
    pairs = getattr(parser, "attributes", [])
    attrs = dict(pairs)
    if (
        len(pairs) != len(attrs)
        or not {"id", "type"} <= set(attrs)
        or set(attrs) - {"id", "type", "subtype"}
    ):
        raise ValueError("Annotations require id and type, with optional subtype")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", attrs["id"] or ""):
        raise ValueError("Invalid annotation ID")
    if attrs["type"] not in {"clarification", "change_request"}:
        raise ValueError("Annotation type must be clarification or change_request")
    if "subtype" in attrs and attrs["subtype"] not in {
        "manuscript_change",
        "additional_experiments",
    }:
        raise ValueError(
            "Annotation subtype must be manuscript_change or additional_experiments"
        )
    return attrs


def annotation_markup(original, annotated):
    if TAG.sub("", annotated) != original:
        raise ValueError("Annotated content changes the original text")
    parts, annotations = [], []
    position, opened = 0, None
    for match in TAG.finditer(annotated):
        parts.append(annotated[position : match.start()])
        if match[1]:
            if opened is None or match[2].strip():
                raise ValueError("Unmatched annotation closing tag")
            opened["source"] = annotated[opened.pop("start") : match.start()]
            annotations.append(opened)
            opened = None
            parts.append("</mark>")
        else:
            if opened is not None:
                raise ValueError("Annotations cannot overlap or nest")
            opened = {**annotation_attributes(match[0]), "start": match.end()}
            parts.append(
                '<mark class="review-annotation" data-annotation-id="'
                + escape(opened["id"], quote=True)
                + '" data-annotation-type="'
                + opened["type"]
                + (
                    '" data-annotation-subtype="'
                    + escape(opened["subtype"], quote=True)
                    if "subtype" in opened
                    else ""
                )
                + '">'
            )
        position = match.end()
    if opened is not None:
        raise ValueError("Unclosed annotation tag")
    parts.append(annotated[position:])
    return "".join(parts), annotations
