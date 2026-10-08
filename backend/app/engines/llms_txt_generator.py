from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def _clean_title(title: str, default: str = "Enterprise Business") -> str:
    cleaned = title.strip()
    if "|" in cleaned:
        cleaned = cleaned.split("|")[0].strip()
    if "-" in cleaned:
        cleaned = cleaned.split("-")[0].strip()
    return cleaned or default


def _categorize_urls(urls: list[str]) -> dict[str, list[tuple[str, str, str]]]:
    """
    Categorize discovered URLs into Docs, Product, and Legal sections.
    Returns dict mapping category -> list of (title, url, description).
    """
    categories: dict[str, list[tuple[str, str, str]]] = {
        "Docs": [],
        "Product": [],
        "Legal": [],
        "Resources": [],
    }

    for u in urls:
        parsed = urlparse(u)
        path = parsed.path.lower().strip("/")
        if not path:
            continue

        parts = path.split("/")
        slug = parts[-1].replace("-", " ").replace("_", " ").title()

        if any(k in path for k in ["doc", "docs", "guide", "tutorial", "api", "reference", "sdk"]):
            categories["Docs"].append(
                (slug or "Documentation", u, "Technical documentation and integration guides")
            )
        elif any(
            k in path for k in ["pricing", "plan", "features", "solutions", "product", "demo"]
        ):
            categories["Product"].append(
                (slug or "Product Overview", u, "Product details, capabilities, and pricing")
            )
        elif any(
            k in path
            for k in ["privacy", "terms", "tos", "legal", "security", "compliance", "policy"]
        ):
            categories["Legal"].append(
                (slug or "Policies", u, "Legal, compliance, and terms of service")
            )
        else:
            categories["Resources"].append(
                (slug or "Overview", u, "General information and resources")
            )

    return categories


def generate_llms_txt(
    domain: str,
    title: str = "",
    description: str = "",
    crawled_urls: list[str] | None = None,
    business_facts: dict[str, Any] | None = None,
) -> str:
    """
    Synthesize a Jeremy Howard compliant /llms.txt manifest per Doc 5 §6.
    """
    site_title = _clean_title(title, default=domain or "FindableAI Target")
    desc = description.strip() or f"Official machine-readable knowledge index for {site_title}."

    urls = crawled_urls or []
    categorized = _categorize_urls(urls)

    lines: list[str] = [
        f"# {site_title}",
        "",
        f"> {desc}",
        "",
    ]

    # Add core business contact/facts if present
    if business_facts:
        contact_points = []
        if business_facts.get("phone"):
            contact_points.append(f"Phone: {business_facts['phone']}")
        if business_facts.get("email"):
            contact_points.append(f"Email: {business_facts['email']}")
        if business_facts.get("address"):
            contact_points.append(f"Location: {business_facts['address']}")
        if contact_points:
            lines.extend(
                [
                    "## Organization Information",
                    "",
                    f"- **Verified Contacts:** {', '.join(contact_points)}",
                    "",
                ]
            )

    # Section ordering
    ordered_sections = ["Docs", "Product", "Legal", "Resources"]
    for sec in ordered_sections:
        items = categorized.get(sec, [])
        if not items:
            continue
        lines.append(f"## {sec}")
        lines.append("")
        for name, url, summary in items[:6]:
            lines.append(f"- [{name}]({url}): {summary}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def generate_llms_full_txt(
    domain: str,
    title: str = "",
    description: str = "",
    chunks: list[Any] | None = None,
    crawled_urls: list[str] | None = None,
) -> str:
    """
    Generate /llms-full.txt flattening DOM content for single-fetch AI agent ingestion (§6.1).
    """
    site_title = _clean_title(title, default=domain or "FindableAI Target")
    desc = description.strip() or f"Complete flattened factual content for {site_title}."

    lines: list[str] = [
        f"# {site_title} - Full Knowledge Corpus",
        "",
        f"> {desc}",
        "",
        "---",
        "",
    ]

    if chunks:
        seen_texts: set[str] = set()
        for i, chunk in enumerate(chunks):
            content = getattr(chunk, "content", "")
            if not content:
                continue
            normalized = " ".join(content.split())
            if len(normalized) < 20 or normalized in seen_texts:
                continue
            seen_texts.add(normalized)

            url = getattr(chunk, "url", domain)
            tag = getattr(chunk, "tag", "section")
            lines.extend(
                [
                    f"### Entry {i + 1} ({tag.upper()} from {url})",
                    "",
                    normalized,
                    "",
                ]
            )
    else:
        urls = crawled_urls or []
        for u in urls[:10]:
            lines.extend(
                [
                    f"### Page: {u}",
                    "",
                    f"Verified resource located at {u}.",
                    "",
                ]
            )

    return "\n".join(lines).strip() + "\n"
