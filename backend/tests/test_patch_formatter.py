"""Unit tests for P2-3.3 patch formatter."""

from __future__ import annotations

from app.engines.jsonld_generator import dumps_jsonld
from app.engines.patch_formatter import (
    PatchFormatter,
    format_jsonld_patch,
    wrap_jsonld_script,
)
from app.schemas.patching import (
    GeneratedJsonLd,
    PatchFormatStatus,
    SchemaRemediationTarget,
)


def _generated(
    *,
    opportunity_id: str = "missing_schema:FAQPage",
    schema_type: SchemaRemediationTarget = SchemaRemediationTarget.FAQ_PAGE,
    payload: dict | None = None,
) -> GeneratedJsonLd:
    body = payload or {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Hours?",
                "acceptedAnswer": {"@type": "Answer", "text": "10-10"},
            }
        ],
    }
    return GeneratedJsonLd(
        opportunity_id=opportunity_id,
        schema_type=schema_type,
        payload=body,
        json_text=dumps_jsonld(body),
    )


def test_insert_before_head():
    html = "<html><head><title>T</title></head><body></body></html>"
    result = format_jsonld_patch(_generated(), html=html)
    assert result.status is PatchFormatStatus.APPLIED
    assert result.insertion_location == "before_head"
    assert "application/ld+json" in result.patched_html
    assert result.patched_html.index("ld+json") < result.patched_html.lower().index("</head>")


def test_fallback_before_body():
    html = "<html><body><p>Hi</p></body></html>"
    result = format_jsonld_patch(_generated(), html=html)
    assert result.insertion_location == "before_body"
    assert result.status is PatchFormatStatus.APPLIED


def test_missing_insertion_points_error():
    html = "<html><p>no closers</p></html>"
    result = format_jsonld_patch(_generated(), html=html)
    assert result.status is PatchFormatStatus.ERROR
    assert "insertion" in result.message.lower() or "head" in result.message.lower()


def test_ld_json_wrapper():
    script = wrap_jsonld_script('{"@type":"FAQPage"}\n')
    assert 'type="application/ld+json"' in script
    assert script.strip().startswith("<script")
    assert script.strip().endswith("</script>")


def test_valid_unified_diff():
    html = "<html><head></head><body></body></html>"
    result = format_jsonld_patch(_generated(), html=html, file_path="index.html")
    assert result.patch_text.startswith("--- a/index.html")
    assert "+++ b/index.html" in result.patch_text
    assert "@@" in result.patch_text
    assert result.changed_lines > 0


def test_only_intended_lines_change():
    html = "<html><head>\n<title>Keep</title>\n</head><body>Body</body></html>"
    result = format_jsonld_patch(_generated(), html=html)
    assert "<title>Keep</title>" in result.patched_html
    assert "Body" in result.patched_html
    # Diff should not rewrite the title line as a change pair beyond context
    assert result.patched_html.count("<title>Keep</title>") == 1


def test_identical_block_noop():
    gen = _generated()
    html = (
        "<html><head>"
        f'<script type="application/ld+json">{gen.json_text}</script>'
        "</head><body></body></html>"
    )
    result = format_jsonld_patch(gen, html=html)
    assert result.status is PatchFormatStatus.NOOP
    assert result.is_noop is True
    assert result.patch_text == ""


def test_conflicting_block_no_overwrite():
    existing = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "Different?",
                "acceptedAnswer": {"@type": "Answer", "text": "No"},
            }
        ],
    }
    html = (
        "<html><head>"
        f'<script type="application/ld+json">{dumps_jsonld(existing)}</script>'
        "</head><body></body></html>"
    )
    result = format_jsonld_patch(_generated(), html=html)
    assert result.status is PatchFormatStatus.CONFLICT
    assert result.patched_html is None


def test_deterministic_output():
    html = "<html><head></head><body></body></html>"
    a = format_jsonld_patch(_generated(), html=html)
    b = format_jsonld_patch(_generated(), html=html)
    assert a.patch_text == b.patch_text
    assert a.patched_html == b.patched_html


def test_stable_ordering_multiple():
    html = "<html><head></head><body></body></html>"
    g1 = _generated(
        opportunity_id="missing_schema:Menu",
        schema_type=SchemaRemediationTarget.MENU,
        payload={"@context": "https://schema.org", "@type": "Menu", "name": "Dinner"},
    )
    g2 = _generated(opportunity_id="missing_schema:FAQPage")
    result = PatchFormatter().format_all([g2, g1], html=html)
    assert [p.opportunity_id for p in result.patches] == [
        "missing_schema:FAQPage",
        "missing_schema:Menu",
    ]


def test_unicode_content():
    gen = _generated(
        payload={
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": "मूल्य?",
                    "acceptedAnswer": {"@type": "Answer", "text": "₹500"},
                }
            ],
        }
    )
    html = "<html><head></head><body></body></html>"
    result = format_jsonld_patch(gen, html=html)
    assert "₹500" in result.patched_html


def test_file_path_metadata():
    result = format_jsonld_patch(
        _generated(),
        html="<html><head></head><body></body></html>",
        file_path="pages/home.html",
    )
    assert result.file_path == "pages/home.html"
    assert "a/pages/home.html" in result.patch_text
