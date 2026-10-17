"""In-memory DOM context compressor and prompt pruner (Ladder of Laziness / Standard Library first)."""

from __future__ import annotations

import re

# Common English stop words to exclude when extracting query anchor keywords
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "when",
        "at",
        "by",
        "for",
        "with",
        "about",
        "against",
        "between",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "to",
        "from",
        "up",
        "down",
        "in",
        "out",
        "on",
        "off",
        "over",
        "under",
        "again",
        "further",
        "once",
        "here",
        "there",
        "where",
        "why",
        "how",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "can",
        "will",
        "just",
        "should",
        "now",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "having",
        "do",
        "does",
        "did",
        "doing",
        "would",
        "could",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "am",
        "it",
        "its",
    }
)

_SVG_RE = re.compile(r"<svg[\s\S]*?</svg>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_COOKIE_BANNER_RE = re.compile(
    r"(?i)\b(we use cookies|cookie policy|accept (all )?cookies|manage cookies|cookie settings|privacy preferences)\b[^\n.!?]*",
)
_MULTI_WS_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n\s*\n")


def clean_dom_noise(text: str) -> str:
    """Strips SVG tags, residual HTML markers, cookie notices, and excess whitespace."""
    if not text:
        return ""
    # Strip SVGs and raw tags if present
    cleaned = _SVG_RE.sub(" ", text)
    cleaned = _TAG_RE.sub(" ", cleaned)
    # Strip boilerplate cookie notices
    cleaned = _COOKIE_BANNER_RE.sub("", cleaned)
    # Normalize spaces and newlines
    cleaned = _MULTI_WS_RE.sub(" ", cleaned)
    cleaned = _MULTI_NL_RE.sub("\n", cleaned)
    return cleaned.strip()


def extract_query_keywords(query: str) -> set[str]:
    """Extracts non-stopword tokens from the query for sentence relevance matching."""
    tokens = re.findall(r"\b[a-zA-Z0-9_\-$%]{3,}\b", query.lower())
    return {t for t in tokens if t not in _STOP_WORDS}


def compress_chunk_for_query(content: str, query: str, max_chars: int = 240) -> str:
    """Extracts the most query-relevant sentences from a chunk to minimize prompt tokens."""
    cleaned = clean_dom_noise(content)
    if len(cleaned) <= max_chars:
        return cleaned

    keywords = extract_query_keywords(query)
    if not keywords:
        return cleaned[:max_chars].rsplit(" ", 1)[0] + "..."

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    if len(sentences) <= 1:
        return cleaned[:max_chars].rsplit(" ", 1)[0] + "..."

    # Score sentences by keyword hits
    scored: list[tuple[int, int, str]] = []
    for i, s in enumerate(sentences):
        s_tokens = set(re.findall(r"\b[a-zA-Z0-9_\-$%]{3,}\b", s.lower()))
        score = len(s_tokens & keywords)
        scored.append((score, i, s))

    # Sort descending by score; pick highest scoring sentence
    scored.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    best_score, best_idx, best_sentence = scored[0]

    if best_score == 0:
        # No keyword matches, return beginning of chunk
        return cleaned[:max_chars].rsplit(" ", 1)[0] + "..."

    # Assemble context: best sentence + adjacent sentence if it fits
    selected = [best_sentence]
    current_len = len(best_sentence)

    if best_idx + 1 < len(sentences):
        next_s = sentences[best_idx + 1]
        if current_len + len(next_s) + 1 <= max_chars:
            selected.append(next_s)
            current_len += len(next_s) + 1

    if best_idx - 1 >= 0:
        prev_s = sentences[best_idx - 1]
        if current_len + len(prev_s) + 1 <= max_chars:
            selected.insert(0, prev_s)

    result = " ".join(selected).strip()
    if len(result) > max_chars:
        result = result[:max_chars].rsplit(" ", 1)[0] + "..."
    return result
