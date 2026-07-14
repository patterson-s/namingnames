#!/usr/bin/env python3

import difflib
import html
from typing import List, Optional, Tuple


def find_surface_form_spans(
    text: str, chunk_start: int, chunk_text: str, surface_forms: List[str]
) -> List[Tuple[int, int]]:
    """Locate every occurrence of any surface form inside chunk_text, mapped to
    absolute offsets in the full speech `text`. Mirrors app/api/speeches.py."""
    spans = []
    for entity in surface_forms:
        entity = entity.strip()
        if not entity:
            continue
        offset = 0
        while True:
            idx = chunk_text.find(entity, offset)
            if idx == -1:
                idx = chunk_text.lower().find(entity.lower(), offset)
                if idx == -1:
                    break
            abs_start = chunk_start + idx
            abs_end = chunk_start + idx + len(entity)
            if abs_end > len(text):
                break
            spans.append((abs_start, abs_end))
            offset = idx + len(entity)
    return spans


def find_quote_span(chunk_text: str, chunk_start: int, quote: str) -> Optional[Tuple[int, int]]:
    """2-tier fallback: exact substring, then difflib longest-match (ratio >= 0.85).
    Returns None if no adequate match (caller should render as plain blockquote)."""
    if not quote or not chunk_text:
        return None

    idx = chunk_text.find(quote)
    if idx != -1:
        return (chunk_start + idx, chunk_start + idx + len(quote))

    matcher = difflib.SequenceMatcher(None, chunk_text, quote)
    match = matcher.find_longest_match(0, len(chunk_text), 0, len(quote))
    if len(quote) > 0 and match.size / len(quote) >= 0.85:
        return (chunk_start + match.a, chunk_start + match.a + match.size)
    return None


def dedupe_spans(spans: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    seen: List[Tuple[int, int]] = []
    for start, end in sorted(spans):
        if any(not (end <= s or start >= e) for s, e in seen):
            continue
        seen.append((start, end))
    return seen


def render_speech_html(text: str, target_spans: List[Tuple[int, int]], quote_spans: List[Tuple[int, int]]) -> str:
    """Builds HTML for the full speech: target_spans wrapped in bold, quote_spans
    wrapped in <mark>. Target-bold wins over evidence-mark on overlap."""
    target_spans = dedupe_spans(target_spans)
    quote_spans = [qs for qs in dedupe_spans(quote_spans) if not any(not (qs[1] <= t[0] or qs[0] >= t[1]) for t in target_spans)]

    markers = [(s, e, "target") for s, e in target_spans] + [(s, e, "quote") for s, e in quote_spans]
    markers.sort()

    out = []
    pos = 0
    for start, end, kind in markers:
        if start < pos:
            continue
        out.append(html.escape(text[pos:start]))
        segment = html.escape(text[start:end])
        if kind == "target":
            out.append(f'<b class="target-bold">{segment}</b>')
        else:
            out.append(f'<mark class="evidence">{segment}</mark>')
        pos = end
    out.append(html.escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")
