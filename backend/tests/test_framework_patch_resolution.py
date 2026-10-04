"""Unit and integration tests for framework-native patch resolution.

Verifies 1:1 parity between web preview patch resolution and PR engine output.
"""

from __future__ import annotations

from app.engines.framework_adapter import (
    inject_component_into_layout,
    locate_framework_layout,
    resolve_framework_patches,
    synthesize_framework_component,
)
from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType

SAMPLE_PATCH = PatchProposal(
    patch_id="patch_test_123",
    patch_type=PatchType.SCHEMA_MICRODATA,
    title="Inject Schema.org LocalBusiness JSON-LD",
    rationale="Missing JSON-LD microdata degrades AI discoverability.",
    impact_score_delta=6.5,
    dom_anchor=DOMSelectorAnchor(
        css_selector="head",
        tag_name="head",
        original_snippet="<head>",
        suggested_snippet='<head><script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"FindableAI"}</script>',
    ),
    unified_diff='--- a/index.html\n+++ b/index.html\n@@ -1,3 +1,4 @@\n <head>\n+<script type="application/ld+json">{"@context":"https://schema.org","@type":"LocalBusiness","name":"FindableAI"}</script>\n </head>',
    applied=False,
)

SAMPLE_LAYOUT = """import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'My App',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
"""


def test_locate_framework_layout_app_router():
    files = [
        "README.md",
        "package.json",
        "frontend/src/app/globals.css",
        "frontend/src/app/layout.tsx",
        "frontend/src/app/page.tsx",
    ]
    target = locate_framework_layout(files)
    assert target is not None
    layout_file, component_file, import_path = target
    assert layout_file == "frontend/src/app/layout.tsx"
    assert component_file == "frontend/src/components/JsonLd.tsx"
    assert import_path == "@/components/JsonLd"


def test_synthesize_framework_component_typescript():
    component_code = synthesize_framework_component([SAMPLE_PATCH])
    assert component_code is not None
    assert "export function JsonLd()" in component_code
    assert "application/ld+json" in component_code
    assert "dangerouslySetInnerHTML" in component_code
    assert "FindableAI" in component_code


def test_inject_component_into_layout():
    injected = inject_component_into_layout(
        SAMPLE_LAYOUT,
        component_name="JsonLd",
        import_path="@/components/JsonLd",
    )
    assert 'import { JsonLd } from "@/components/JsonLd";' in injected
    assert "<JsonLd />" in injected


def test_resolve_framework_patches_end_to_end():
    files = [
        "package.json",
        "frontend/src/app/layout.tsx",
        "frontend/src/app/page.tsx",
    ]

    def mock_get_content(path: str) -> str:
        if path == "frontend/src/app/layout.tsx":
            return SAMPLE_LAYOUT
        raise FileNotFoundError(path)

    resolved = resolve_framework_patches(
        [SAMPLE_PATCH],
        tree_files=files,
        get_file_content=mock_get_content,
    )

    assert len(resolved) == 1
    p = resolved[0]
    assert p.target_file == "frontend/src/app/layout.tsx"
    assert p.code_diff is not None
    assert 'import { JsonLd } from "@/components/JsonLd";' in p.code_diff
    assert "<JsonLd />" in p.code_diff
    assert p.framework == "nextjs_app_router"
    assert len(p.auxiliary_files) == 1
    assert p.auxiliary_files[0].file_path == "frontend/src/components/JsonLd.tsx"
    assert p.auxiliary_files[0].action == "create"
    assert "export function JsonLd()" in p.auxiliary_files[0].content


def test_resolve_framework_patches_fallback_when_no_framework():
    # Plain static site with no nextjs layout
    files = ["index.html", "style.css", "main.js"]

    resolved = resolve_framework_patches(
        [SAMPLE_PATCH],
        tree_files=files,
        get_file_content=lambda p: "",
    )

    assert len(resolved) == 1
    assert resolved[0].target_file is None
    assert resolved[0].unified_diff == SAMPLE_PATCH.unified_diff


def test_resolve_framework_patches_multiple_patches_deduplicates_layout_diff():
    """Verify that multiple patches in a scan do not duplicate the identical layout.tsx diff."""
    files = ["package.json", "frontend/src/app/layout.tsx"]
    patch_2 = SAMPLE_PATCH.model_copy(
        update={"patch_id": "patch_002", "title": "Inject FAQ Schema"}
    )

    resolved = resolve_framework_patches(
        [SAMPLE_PATCH, patch_2],
        tree_files=files,
        get_file_content=lambda p: SAMPLE_LAYOUT,
    )

    assert len(resolved) == 2
    # Primary patch has framework target and auxiliary component
    assert resolved[0].target_file == "frontend/src/app/layout.tsx"
    assert resolved[0].code_diff is not None
    assert len(resolved[0].auxiliary_files) == 1

    # Secondary patch does NOT duplicate the layout diff or auxiliary file
    assert resolved[1].target_file is None
    assert resolved[1].code_diff is None
    assert len(resolved[1].auxiliary_files) == 0
    assert resolved[1].framework is None
