"""Shared Framework-Native Code Transformation Engine.

Detects application frameworks (e.g. Next.js, React SPA) and synthesizes
framework-native components and layout diffs for 1:1 parity between Web UI
patch previews and GitHub Pull Requests.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
from collections.abc import Callable, Sequence
from typing import Any

from app.schemas.patch import PatchProposal

logger = logging.getLogger(__name__)

_IGNORED_PATH_PREFIXES = (
    "node_modules",
    ".git",
    ".next",
    "dist",
    "build",
    ".cache",
    ".turbo",
    "coverage",
    "vendor",
)

_SCRIPT_RE = re.compile(
    r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>[\s\S]*?</script>",
    re.IGNORECASE,
)


def locate_framework_layout(tree_files: Sequence[str]) -> tuple[str, str, str] | None:
    """Finds root framework layout file in tree_files.

    Returns (layout_file, component_file, import_path) or None.
    """
    if not tree_files:
        return None

    search_files = [
        f
        for f in tree_files
        if not any(
            f.lower().startswith(pfx) or f"/{pfx}" in f.lower() for pfx in _IGNORED_PATH_PREFIXES
        )
    ]

    layout_candidates = [
        "frontend/src/app/layout.tsx",
        "frontend/src/app/layout.jsx",
        "frontend/src/app/layout.js",
        "src/app/layout.tsx",
        "src/app/layout.jsx",
        "src/app/layout.js",
        "frontend/app/layout.tsx",
        "frontend/app/layout.jsx",
        "frontend/app/layout.js",
        "app/layout.tsx",
        "app/layout.jsx",
        "app/layout.js",
        "frontend/src/pages/_app.tsx",
        "src/pages/_app.tsx",
        "pages/_app.tsx",
    ]

    found_layout = None
    for cand in layout_candidates:
        for f in search_files:
            if f.lower() == cand.lower():
                found_layout = f
                break
        if found_layout:
            break

    if not found_layout:
        for f in search_files:
            if f.lower().endswith(("/app/layout.tsx", "/app/layout.jsx", "/app/layout.js")):
                found_layout = f
                break

    if not found_layout:
        return None

    norm = found_layout.replace("\\", "/")
    ext = ".tsx" if norm.endswith((".tsx", ".ts")) else ".jsx"

    if "/app/" in norm:
        prefix = norm.split("/app/")[0]
        component_file = f"{prefix}/components/JsonLd{ext}" if prefix else f"components/JsonLd{ext}"
    elif norm.startswith("app/"):
        component_file = f"components/JsonLd{ext}"
        prefix = ""
    elif "/pages/" in norm:
        prefix = norm.split("/pages/")[0]
        component_file = f"{prefix}/components/JsonLd{ext}" if prefix else f"components/JsonLd{ext}"
    elif norm.startswith("pages/"):
        component_file = f"components/JsonLd{ext}"
        prefix = ""
    else:
        prefix = norm.rsplit("/", 1)[0]
        component_file = f"{prefix}/JsonLd{ext}"

    if "src/" in norm:
        import_path = "@/components/JsonLd"
    elif prefix:
        import_path = "../components/JsonLd"
    else:
        import_path = "@/components/JsonLd"

    return (found_layout, component_file, import_path)


def extract_schema_objects(items: Sequence[Any]) -> list[dict[str, object]]:
    """Extract Schema.org JSON dictionaries from patches, strings, or DOM snippets."""
    schema_objs: list[dict[str, object]] = []

    for item in items:
        # 1. From FormattedPatch (has patched_html or patch_text)
        patched_html = getattr(item, "patched_html", None)
        if patched_html:
            for script in _SCRIPT_RE.findall(patched_html):
                inner = re.sub(r"^<script\b[^>]*>", "", script, flags=re.IGNORECASE)
                inner = re.sub(r"</script>$", "", inner.strip(), flags=re.IGNORECASE).strip()
                try:
                    parsed = json.loads(inner)
                    if parsed not in schema_objs:
                        schema_objs.append(parsed)
                except Exception:
                    pass

        # 2. From PatchProposal (has dom_anchor.suggested_snippet or unified_diff)
        dom_anchor = getattr(item, "dom_anchor", None)
        if dom_anchor and getattr(dom_anchor, "suggested_snippet", None):
            for script in _SCRIPT_RE.findall(dom_anchor.suggested_snippet):
                inner = re.sub(r"^<script\b[^>]*>", "", script, flags=re.IGNORECASE)
                inner = re.sub(r"</script>$", "", inner.strip(), flags=re.IGNORECASE).strip()
                try:
                    parsed = json.loads(inner)
                    if parsed not in schema_objs:
                        schema_objs.append(parsed)
                except Exception:
                    pass

        # 3. From raw patch_text or unified_diff
        raw_text = getattr(item, "patch_text", None) or getattr(item, "unified_diff", None) or ""
        if isinstance(raw_text, str) and "application/ld+json" in raw_text:
            lines = []
            capturing = False
            for line in raw_text.splitlines():
                if "<script" in line and "application/ld+json" in line:
                    capturing = True
                    continue
                if capturing and "</script>" in line:
                    capturing = False
                    continue
                if capturing:
                    clean = line.lstrip("+").rstrip()
                    lines.append(clean)
            if lines:
                try:
                    parsed = json.loads("\n".join(lines))
                    if parsed not in schema_objs:
                        schema_objs.append(parsed)
                except Exception:
                    pass

    return schema_objs


def synthesize_framework_component(items: Sequence[Any]) -> str:
    """Generates a type-safe React / Next.js JsonLd component with Schema.org payloads."""
    schema_objs = extract_schema_objects(items)

    if not schema_objs:
        return ""

    if len(schema_objs) == 1:
        final_schema = schema_objs[0]
    else:
        final_schema = {
            "@context": "https://schema.org",
            "@graph": schema_objs,
        }

    schema_json = json.dumps(final_schema, indent=2)
    indented_schema = "\n".join(
        "  " + line if i > 0 else line for i, line in enumerate(schema_json.splitlines())
    )

    return (
        "/**\n"
        " * Machine-generated Schema.org JSON-LD component by FindableAI.\n"
        " * Enhances discoverability for LLMs and AI Search Engines (SearchGPT, Perplexity, Google AI Overviews).\n"
        " */\n"
        "export function JsonLd() {\n"
        f"  const schema = {indented_schema};\n\n"
        "  return (\n"
        "    <script\n"
        '      type="application/ld+json"\n'
        "      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}\n"
        "    />\n"
        "  );\n"
        "}\n\n"
        "export default JsonLd;\n"
    )


def strip_comments_and_strings(code: str) -> str:
    """Strips comments and string literals to enable clean structural inspection."""
    output: list[str] = []
    i = 0
    n = len(code)
    while i < n:
        # Multi-line comment
        if code[i : i + 2] == "/*":
            end_idx = code.find("*/", i + 2)
            if end_idx == -1:
                break
            i = end_idx + 2
            continue
        # Single-line comment
        if code[i : i + 2] == "//":
            end_idx = code.find("\n", i + 2)
            if end_idx == -1:
                break
            i = end_idx
            continue
        # Template literal or string literal
        if code[i] in ('"', "'", "`"):
            quote = code[i]
            i += 1
            while i < n:
                if code[i] == "\\":
                    i += 2
                    continue
                if code[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        output.append(code[i])
        i += 1
    return "".join(output)


def check_balanced_delimiters(sanitized: str) -> bool:
    """Verifies that curly braces, parentheses, and square brackets are balanced."""
    stack: list[str] = []
    pairs = {"}": "{", ")": "(", "]": "["}
    for ch in sanitized:
        if ch in ("{", "(", "["):
            stack.append(ch)
        elif ch in ("}", ")", "]"):
            if not stack or stack[-1] != pairs[ch]:
                return False
            stack.pop()
    return len(stack) == 0


def validate_framework_layout_syntax(original_content: str, modified_content: str) -> bool:
    """Validates structural and lexical integrity of modified TSX/JSX layout.

    Acts as a heuristic safety net confirming balanced delimiters, clean import
    boundaries, and valid JSX element placement before code is committed to Git.
    """
    if not modified_content or not modified_content.strip():
        return False
    if modified_content == original_content:
        return True

    sanitized_mod = strip_comments_and_strings(modified_content)

    # 1. Delimiter balance check
    if not check_balanced_delimiters(sanitized_mod):
        logger.warning("Framework layout validation failed: unbalanced delimiters in modified layout")
        return False

    # 2. Injected import boundary check
    if 'import { JsonLd } from "' not in modified_content:
        logger.warning("Framework layout validation failed: missing JsonLd import statement")
        return False

    # Ensure import is at the start of a line (not spliced into another statement)
    if not re.search(r"^import\s+\{\s*JsonLd\s*\}\s+from\s+[\"'].*?[\"'];?", modified_content, re.MULTILINE):
        logger.warning("Framework layout validation failed: malformed import line boundary")
        return False

    # 3. Injected JSX component check
    if "<JsonLd />" not in sanitized_mod and "<JsonLd/>" not in sanitized_mod:
        logger.warning("Framework layout validation failed: <JsonLd /> not present in sanitized JSX")
        return False

    # Ensure <JsonLd /> is not inside an unclosed HTML attribute or type annotation
    if re.search(r"<\w+\s+[^>]*<JsonLd\s*/>", modified_content):
        logger.warning("Framework layout validation failed: <JsonLd /> nested inside tag opening attribute")
        return False

    # Ensure <JsonLd /> is not injected into a TypeScript type definition parameter
    if re.search(r"\{\s*<JsonLd\s*/>\s*children\s*:\s*React", modified_content):
        logger.warning("Framework layout validation failed: <JsonLd /> placed inside parameter type definition")
        return False

    return True


def inject_component_into_layout(
    layout_content: str,
    component_name: str = "JsonLd",
    import_path: str = "@/components/JsonLd",
) -> str:
    """Safely injects import and JSX tag into framework layout file."""
    if not layout_content or not layout_content.strip():
        return layout_content

    if f"<{component_name}" in layout_content or f'from "{import_path}"' in layout_content:
        return layout_content

    content = layout_content

    # 1. Inject import statement after the last top-level import block
    import_stmt = f'import {{ {component_name} }} from "{import_path}";'
    import_matches = list(re.finditer(r"^import\s+[\s\S]*?(?:;|\n)", content, re.MULTILINE))
    if import_matches:
        last_import = import_matches[-1]
        insert_idx = last_import.end()
        prefix = content[:insert_idx]
        if not prefix.endswith("\n"):
            import_stmt = "\n" + import_stmt
        import_stmt = import_stmt + "\n"
        content = prefix + import_stmt + content[insert_idx:]
    else:
        content = import_stmt + "\n\n" + content

    tag = f"<{component_name} />"

    # 2. Inject JSX tag into body or JSX return structure
    body_match = re.search(r"(<body\b[^>]*>)", content, re.IGNORECASE)
    if body_match:
        idx = body_match.end()
        content = content[:idx] + f"\n        {tag}" + content[idx:]
    else:
        # Avoid injecting into TypeScript type definitions like ({ children }: { children: React.ReactNode })
        return_match = re.search(r"\breturn\b\s*[\s\S]*", content)
        if return_match:
            return_body = return_match.group(0)
            child_idx_in_return = return_body.find("{children}")
            if child_idx_in_return != -1:
                abs_idx = return_match.start() + child_idx_in_return
                content = content[:abs_idx] + f"{tag}\n        " + content[abs_idx:]

    return content


def generate_git_diff(original: str, modified: str, file_path: str) -> str:
    """Generates standard git-compatible unified diff."""
    orig_lines = original.splitlines(keepends=True)
    mod_lines = modified.splitlines(keepends=True)
    diff = difflib.unified_diff(
        orig_lines,
        mod_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    return "".join(diff)


def resolve_framework_patches(
    patches: Sequence[PatchProposal],
    tree_files: Sequence[str],
    get_file_content: Callable[[str], str],
) -> list[PatchProposal]:
    """Decorates patch proposals with framework-native file targets and exact git diffs.

    Ensures 1:1 parity between UI preview and the code committed by the PR Engine.
    """
    if not patches or not tree_files:
        return list(patches)

    framework_target = locate_framework_layout(tree_files)
    if not framework_target:
        return list(patches)

    layout_file, component_file, import_path = framework_target

    try:
        remote_layout = get_file_content(layout_file)
    except Exception as exc:
        logger.info("Could not fetch %s for framework patch resolution: %s", layout_file, exc)
        return list(patches)

    component_content = synthesize_framework_component(patches)
    if not component_content:
        return list(patches)

    patched_layout = inject_component_into_layout(
        remote_layout,
        component_name="JsonLd",
        import_path=import_path,
    )

    # Post-injection syntax validation safety net
    if not validate_framework_layout_syntax(remote_layout, patched_layout):
        logger.warning(
            "Framework layout validation failed for %s; skipping direct layout modification",
            layout_file,
        )
        return list(patches)

    layout_diff = generate_git_diff(remote_layout, patched_layout, layout_file)
    framework_name = "nextjs_app_router" if "/app/" in layout_file else "nextjs_pages"

    resolved: list[PatchProposal] = []
    for i, patch in enumerate(patches):
        p_dict = patch.model_dump()
        if i == 0:
            # Primary patch carries the layout modification and the new component auxiliary file
            p_dict["target_file"] = layout_file
            p_dict["code_diff"] = layout_diff
            p_dict["framework"] = framework_name
            p_dict["auxiliary_files"] = [
                {
                    "file_path": component_file,
                    "content": component_content,
                    "action": "create",
                }
            ]
        else:
            # Secondary patches contribute to the consolidated PR without duplicating the layout.tsx diff block
            p_dict["target_file"] = None
            p_dict["code_diff"] = None
            p_dict["framework"] = None
            p_dict["auxiliary_files"] = []
        resolved.append(PatchProposal(**p_dict))

    return resolved
