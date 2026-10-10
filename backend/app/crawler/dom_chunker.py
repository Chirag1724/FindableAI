import logging
from dataclasses import dataclass

from bs4 import BeautifulSoup, Comment, Tag

logger = logging.getLogger(__name__)

# Primary semantic HTML tags used for chunking boundaries
SEMANTIC_CHUNK_TAGS = {
    "section",
    "article",
    "main",
    "table",
    "tr",
    "dl",
    "header",
    "footer",
    "nav",
    "aside",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
}

# Elements to strip completely before extracting content
IGNORE_TAGS = {"script", "style", "svg", "noscript", "iframe", "canvas"}


@dataclass
class ChunkData:
    url: str
    dom_path: str
    content: str
    tag: str
    word_count: int


class DOMChunker:
    """
    Structural DOM Chunker that splits HTML at semantic tag boundaries
    and constructs unambiguous, verifiable CSS selector paths for each chunk.
    """

    def __init__(self, min_word_count: int = 3, max_word_count: int = 300):
        self.min_word_count = min_word_count
        self.max_word_count = max_word_count

    def clean_soup(self, soup: BeautifulSoup) -> None:
        """Strip non-content elements and comments from DOM tree in-place."""
        for tag_name in IGNORE_TAGS:
            for el in soup.find_all(tag_name):
                el.decompose()

        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

    def get_css_selector(self, element: Tag) -> str:
        """
        Derive a unique, DevTools-verifiable CSS selector path for an element
        by recursively traversing up through its DOM parents.
        """
        path_parts: list[str] = []
        current: Tag | None = element

        while current and current.name and current.name not in ("[document]", "html"):
            tag_name = current.name.lower()
            element_id = current.get("id")

            # If element has a valid unique ID, stop walking up
            if (
                element_id
                and isinstance(element_id, str)
                and not element_id.startswith(("ember", "ng-", ":"))
            ):
                # Escape spaces or special characters in ID if necessary
                safe_id = element_id.strip()
                path_parts.insert(0, f"{tag_name}#{safe_id}")
                break

            # Handle class names if present
            raw_classes = current.get("class")
            classes: list[str] = []
            if isinstance(raw_classes, list):
                classes = [str(c) for c in raw_classes]
            elif isinstance(raw_classes, str):
                classes = [raw_classes]

            # Filter out dynamic/utility hashes (e.g. Tailwind variants or dynamic IDs)
            clean_classes = [c for c in classes if not c.startswith("_") and ":" not in c]

            selector = tag_name
            if clean_classes:
                # Use up to 2 classes to avoid brittle selector paths
                selector += "." + ".".join(clean_classes[:2])

            # Calculate nth-of-type position relative to sibling elements
            if current.parent and hasattr(current.parent, "children"):
                siblings = [
                    s
                    for s in current.parent.children
                    if isinstance(s, Tag) and s.name and s.name.lower() == tag_name
                ]
                if len(siblings) > 1:
                    try:
                        index = siblings.index(current) + 1
                        selector += f":nth-of-type({index})"
                    except ValueError:
                        pass

            path_parts.insert(0, selector)

            if tag_name == "body":
                break

            current = current.parent if isinstance(current.parent, Tag) else None

        if path_parts:
            return " > ".join(path_parts)
        name = getattr(element, "name", None)
        return str(name).lower() if name else "unknown"

    def chunk(self, html: str, url: str) -> list[ChunkData]:
        """
        Parse HTML and decompose it into semantic chunks with CSS selector paths.
        """
        if not html or not html.strip():
            return []

        soup = BeautifulSoup(html, "lxml")
        self.clean_soup(soup)

        chunks: list[ChunkData] = []
        seen_texts: set[str] = set()

        # Find all candidates matching semantic tags
        candidates = soup.find_all(SEMANTIC_CHUNK_TAGS)

        for element in candidates:
            # Skip container tags if they contain smaller semantic child candidates
            # (unless it's a table row or card article)
            if element.name in ("main", "section", "table", "dl", "ul", "ol"):
                has_semantic_child = any(
                    child.name in SEMANTIC_CHUNK_TAGS and child != element
                    for child in element.find_all(SEMANTIC_CHUNK_TAGS)
                )
                if has_semantic_child:
                    continue

            text = element.get_text(separator=" ", strip=True)
            words = text.split()
            word_count = len(words)

            if word_count < self.min_word_count:
                continue

            # Deduplicate exact duplicate chunk texts on the same page
            normalized_text = " ".join(words)
            if normalized_text in seen_texts:
                continue

            seen_texts.add(normalized_text)

            dom_path = self.get_css_selector(element)

            chunks.append(
                ChunkData(
                    url=url,
                    dom_path=dom_path,
                    content=normalized_text,
                    tag=element.name.lower(),
                    word_count=word_count,
                )
            )

        return chunks
