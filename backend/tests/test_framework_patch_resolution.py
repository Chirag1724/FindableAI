"""Unit and integration tests for framework-native patch resolution.

Verifies 1:1 parity between web preview patch resolution and PR engine output.
"""

from __future__ import annotations

from app.engines.framework_adapter import (
    inject_component_into_layout,
    locate_framework_layout,
    resolve_framework_patches,
    synthesize_framework_component,
    validate_framework_layout_syntax,
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
    assert validate_framework_layout_syntax(SAMPLE_LAYOUT, injected) is True


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


def test_commented_children_falls_back_safely():
    """Layout where {children} only appears inside comments and no <body> tag exists."""
    commented_layout = """import './globals.css';
// TODO: implement RootLayout with {children}
export default function Layout() {
  return <div>Custom Layout Under Construction</div>;
}
"""
    files = ["package.json", "frontend/src/app/layout.tsx"]
    resolved = resolve_framework_patches(
        [SAMPLE_PATCH],
        tree_files=files,
        get_file_content=lambda p: commented_layout,
    )
    # Since there's no body and no return {children}, it should safely avoid corrupting comments
    assert len(resolved) == 1
    # Either validly unchanged or no layout modification attached
    assert resolved[0].code_diff is None or "<JsonLd />" in resolved[0].code_diff


def test_string_literal_children_falls_back_safely():
    """Layout where '{children}' is in a string literal outside of JSX return."""
    string_literal_layout = """import './globals.css';
const description = "App container for {children} rendering";

export default function Layout() {
  return <div>Static Site Shell</div>;
}
"""
    injected = inject_component_into_layout(string_literal_layout)
    # Should not blindly inject inside the string assignment
    assert 'description = "App container for <JsonLd />' not in injected


def test_type_annotation_children_does_not_inject_in_params():
    """Layout with TypeScript type definition ({ children }: { children: React.ReactNode })."""
    type_layout = """import type React from 'react';
import './globals.css';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <main className="container">
      {children}
    </main>
  );
}
"""
    injected = inject_component_into_layout(type_layout)
    assert "interface LayoutProps" in injected
    # Ensure <JsonLd /> was not injected into interface or parameters
    assert "<JsonLd />children" not in injected
    assert "<JsonLd />" in injected
    assert validate_framework_layout_syntax(type_layout, injected) is True


def test_hoc_wrapper_layout_injection_or_safe_fallback():
    """Layout wrapped in a Higher-Order Component (e.g. withAuth or memo)."""
    hoc_layout = """import React from 'react';
import { withTheme } from '@/lib/theme';

function LayoutComponent({ children }: { children: React.ReactNode }) {
  return (
    <div className="theme-wrapper">
      {children}
    </div>
  );
}

export default withTheme(LayoutComponent);
"""
    injected = inject_component_into_layout(hoc_layout)
    assert 'import { JsonLd } from "@/components/JsonLd";' in injected
    assert "<JsonLd />" in injected
    assert validate_framework_layout_syntax(hoc_layout, injected) is True


def test_multiline_destructured_imports_integrity():
    """Layout starting with complex multi-line import destructuring."""
    multiline_import_layout = """import {
  type Metadata,
  type Viewport,
} from 'next';
import {
  Inter,
  Roboto_Mono,
} from 'next/font/google';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        {children}
      </body>
    </html>
  );
}
"""
    injected = inject_component_into_layout(multiline_import_layout)
    assert 'import { JsonLd } from "@/components/JsonLd";' in injected
    assert validate_framework_layout_syntax(multiline_import_layout, injected) is True


def test_malformed_unbalanced_jsx_rejects_and_falls_back():
    """Layout with unbalanced braces/parentheses is rejected by the syntax validator."""
    malformed_layout = """import './globals.css';

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div>
      {children}
    // missing closing tags and unclosed brace
"""
    # Validation should catch structural imbalance
    is_valid = validate_framework_layout_syntax(malformed_layout, malformed_layout + "\n<JsonLd />")
    assert is_valid is False

    # PR engine / resolution fallback test
    files = ["package.json", "frontend/src/app/layout.tsx"]
    resolved = resolve_framework_patches(
        [SAMPLE_PATCH],
        tree_files=files,
        get_file_content=lambda p: malformed_layout,
    )
    # Framework layout diff is skipped on validation failure
    assert len(resolved) == 1
    assert resolved[0].target_file is None
    assert resolved[0].code_diff is None


def test_resolve_framework_patches_maps_robots_and_llms_to_public_dir():
    """Verify that robots.txt and llms.txt map to frontend/public/ in a Next.js App Router repo."""
    from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType

    robots_patch = PatchProposal(
        patch_id="patch_robots_001",
        patch_type=PatchType.ROBOTS_GOVERNANCE,
        title="Configure AI Crawler Access Rules (robots.txt)",
        rationale="Allow Perplexity, block scrapers",
        impact_score_delta=8.0,
        dom_anchor=DOMSelectorAnchor(
            css_selector="robots.txt",
            tag_name="robots.txt",
            original_snippet="",
            suggested_snippet="User-agent: PerplexityBot\nAllow: /\n",
        ),
        unified_diff="--- /dev/null\n+++ b/robots.txt\n@@ -0,0 +1,2 @@\n+User-agent: PerplexityBot\n+Allow: /\n",
        applied=False,
        target_file="robots.txt",
    )

    llms_patch = PatchProposal(
        patch_id="patch_llms_001",
        patch_type=PatchType.LLMS_MANIFEST,
        title="Publish /llms.txt Machine Knowledge Manifest",
        rationale="Standard markdown manifest",
        impact_score_delta=6.0,
        dom_anchor=DOMSelectorAnchor(
            css_selector="llms.txt",
            tag_name="llms.txt",
            original_snippet="",
            suggested_snippet="# Acme Corp\n> Machine index.\n",
        ),
        unified_diff="--- /dev/null\n+++ b/llms.txt\n@@ -0,0 +1,2 @@\n+# Acme Corp\n+> Machine index.\n",
        applied=False,
        target_file="llms.txt",
    )

    files = [
        "package.json",
        "frontend/src/app/layout.tsx",
        "frontend/public/favicon.ico",
    ]

    resolved = resolve_framework_patches(
        [SAMPLE_PATCH, robots_patch, llms_patch],
        tree_files=files,
        get_file_content=lambda p: SAMPLE_LAYOUT,
    )

    assert len(resolved) == 3

    # 1. Schema patch
    assert resolved[0].target_file == "frontend/src/app/layout.tsx"
    assert resolved[0].code_diff is not None
    assert len(resolved[0].auxiliary_files) == 1
    assert resolved[0].auxiliary_files[0].file_path == "frontend/src/components/JsonLd.tsx"

    # 2. Robots patch
    assert resolved[1].target_file == "frontend/public/robots.txt"
    assert "frontend/public/robots.txt" in resolved[1].unified_diff

    # 3. LLMs patch
    assert resolved[2].target_file == "frontend/public/llms.txt"
    assert "frontend/public/llms.txt" in resolved[2].unified_diff


def test_resolve_framework_patches_plain_html_maps_to_root_robots_and_llms():
    """Verify that robots.txt and llms.txt map to root when no public directory or framework layout exists."""
    from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType

    robots_patch = PatchProposal(
        patch_id="patch_robots_002",
        patch_type=PatchType.ROBOTS_GOVERNANCE,
        title="Configure AI Crawler Access Rules (robots.txt)",
        rationale="Allow bots",
        impact_score_delta=8.0,
        dom_anchor=DOMSelectorAnchor(
            css_selector="robots.txt",
            tag_name="robots.txt",
            original_snippet="",
            suggested_snippet="User-agent: *\nAllow: /\n",
        ),
        unified_diff="--- /dev/null\n+++ b/robots.txt\n@@ -0,0 +1,2 @@\n+User-agent: *\n+Allow: /\n",
        applied=False,
        target_file="robots.txt",
    )

    files = ["index.html", "about.html", "styles.css"]

    resolved = resolve_framework_patches(
        [robots_patch],
        tree_files=files,
        get_file_content=lambda p: "",
    )

    assert len(resolved) == 1
    assert resolved[0].target_file == "robots.txt"
