#!/usr/bin/env python3
"""Evidence-quote offset finding against the FULL speech text.

The UNGDC corpus hard-wraps lines with newlines mid-sentence, while the model
returns quotes with whitespace normalized. So matching must be
whitespace-insensitive: we normalize both sides (collapsing every run of
whitespace to a single space) and map the match back to original-text offsets.
"""

import difflib
from typing import List, Optional, Tuple

Span = Tuple[int, int]


def _normalize_ws(text: str) -> Tuple[str, List[int]]:
    """Return (normalized_text, pos) where each normalized char at index i came
    from original index pos[i]. Runs of whitespace collapse to a single ' '
    mapped to the run's first character."""
    chars: List[str] = []
    pos: List[int] = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isspace():
            chars.append(" ")
            pos.append(i)
            while i < n and text[i].isspace():
                i += 1
        else:
            chars.append(text[i])
            pos.append(i)
            i += 1
    return "".join(chars), pos


def find_quote_span(text: str, quote: str) -> Optional[Span]:
    """Locate `quote` in `text`, tolerant of whitespace differences. Returns
    original-text (start, end) offsets, or None if no adequate match."""
    if not quote or not text:
        return None

    idx = text.find(quote)
    if idx != -1:
        return (idx, idx + len(quote))

    norm, pos = _normalize_ws(text)
    nq = " ".join(quote.split())
    if not nq:
        return None

    j = norm.find(nq)
    if j != -1:
        last = j + len(nq) - 1
        return (pos[j], pos[last] + 1)

    matcher = difflib.SequenceMatcher(None, norm, nq)
    match = matcher.find_longest_match(0, len(norm), 0, len(nq))
    if match.size / len(nq) >= 0.85:
        last = match.a + match.size - 1
        return (pos[match.a], pos[last] + 1)
    return None


def dedupe_spans(spans: List[Span]) -> List[Span]:
    seen: List[Span] = []
    for start, end in sorted(spans):
        if any(not (end <= s or start >= e) for s, e in seen):
            continue
        seen.append((start, end))
    return seen
