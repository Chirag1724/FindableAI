"""GitHub PR Engine (P2-3.5).

Thin execution adapter around validated Phase 3.1-3.4 artifacts.
Uses P2-3.6 for PR body Markdown. Performs no intelligence decisions.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Sequence

from app.github.client import GitHubClient, GitHubClientError
from app.github.pr_markdown import generate_pr_markdown
from app.schemas.github_pr import (
    PREngineRequest,
    PREngineResult,
    PRFileChange,
    PRReportData,
    ValidatedRepoFileUpdate,
)
from app.schemas.intelligence import EvidenceReference
from app.schemas.patching import FormattedPatch, PatchFormatStatus

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIXES = (".html", ".htm")
_BRANCH_SAFE = re.compile(r"[^a-zA-Z0-9._/-]+")
_SCRIPT_RE = re.compile(
    r"<script\b[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>.*?</script>\s*",
    re.IGNORECASE | re.DOTALL,
)
_HEAD_CLOSE = re.compile(r"</head\s*>", re.IGNORECASE)
_BODY_CLOSE = re.compile(r"</body\s*>", re.IGNORECASE)


class PREngineError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "pr_engine_error"
        super().__init__(message)


def normalize_repo_path(path: str) -> str:
    """Normalize to POSIX repo-relative path; reject traversal and absolutes."""
    if not isinstance(path, str) or not path.strip():
        raise PREngineError("empty path", reason="invalid_path")
    raw = path.strip().replace("\\", "/")
    if re.match(r"^[a-zA-Z]:/", raw) or re.match(r"^[a-zA-Z]:", path.strip()):
        raise PREngineError(f"Windows drive path rejected: {path}", reason="invalid_path")
    if raw.startswith("/") or raw.startswith("~"):
        raise PREngineError(f"absolute path rejected: {path}", reason="invalid_path")
    if "://" in raw:
        raise PREngineError(f"URL path rejected: {path}", reason="invalid_path")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise PREngineError(f"path traversal rejected: {path}", reason="invalid_path")
    if not parts:
        raise PREngineError(f"empty normalized path: {path}", reason="invalid_path")
    normalized = "/".join(parts)
    if not normalized.lower().endswith(_ALLOWED_SUFFIXES):
        raise PREngineError(
            f"unsupported file type (HTML only): {normalized}",
            reason="unsupported_file",
        )
    return normalized


def sanitize_branch_segment(value: str) -> str:
    cleaned = _BRANCH_SAFE.sub("-", value.strip()).strip("-./")
    cleaned = cleaned.replace("..", ".")
    if not cleaned:
        raise PREngineError("branch identifier empty after sanitize", reason="invalid_branch")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip("-./")
    return cleaned


def build_feature_branch_name(scan_id: str) -> str:
    return f"findableai/remediation/{sanitize_branch_segment(scan_id)}"


def _extract_ldjson_scripts(html: str) -> list[str]:
    return [m.group(0).strip() + "\n" for m in _SCRIPT_RE.finditer(html)]


def _insert_scripts(base_html: str, scripts: Sequence[str]) -> str:
    block = "".join(scripts)
    if not block:
        return base_html
    head = _HEAD_CLOSE.search(base_html)
    if head:
        idx = head.start()
        prefix = base_html[:idx]
        insertion = block if prefix.endswith("\n") else "\n" + block
        return prefix + insertion + base_html[idx:]
    body = _BODY_CLOSE.search(base_html)
    if body:
        idx = body.start()
        prefix = base_html[:idx]
        insertion = block if prefix.endswith("\n") else "\n" + block
        return prefix + insertion + base_html[idx:]
    raise PREngineError(
        "HTML lacks </head> and </body>; cannot apply patches",
        reason="missing_insertion_point",
    )


def combine_patches_for_file(
    *,
    base_html: str,
    patches: Sequence[FormattedPatch],
) -> str:
    """Deterministically merge APPLIED patches for one file against remote base."""
    ordered = sorted(patches, key=lambda p: p.opportunity_id)
    scripts: list[str] = []
    seen: set[str] = set()
    base_scripts = set(_extract_ldjson_scripts(base_html))
    for patch in ordered:
        if patch.status is not PatchFormatStatus.APPLIED:
            continue
        if patch.patched_html is None:
            raise PREngineError(
                f"APPLIED patch missing patched_html: {patch.opportunity_id}",
                reason="invalid_patch",
            )
        for script in _extract_ldjson_scripts(patch.patched_html):
            if script in base_scripts:
                continue
            key = script.strip()
            if key in seen:
                continue
            seen.add(key)
            scripts.append(script if script.endswith("\n") else script + "\n")
    return _insert_scripts(base_html, scripts)


def validate_and_prepare_updates(
    patches: Sequence[FormattedPatch],
) -> dict[str, list[FormattedPatch]]:
    """Group APPLIED patches by normalized path; reject invalid/conflicting sets."""
    if not patches:
        raise PREngineError("patch set is empty", reason="empty_patch_set")

    by_path: dict[str, list[FormattedPatch]] = defaultdict(list)
    for patch in patches:
        if not isinstance(patch, FormattedPatch):
            raise PREngineError("invalid patch type", reason="invalid_patch")
        if patch.status is PatchFormatStatus.NOOP:
            continue
        if patch.status is PatchFormatStatus.CONFLICT:
            raise PREngineError(
                f"patch conflict for {patch.opportunity_id}: {patch.message}",
                reason="patch_conflict",
            )
        if patch.status is PatchFormatStatus.ERROR:
            raise PREngineError(
                f"patch error for {patch.opportunity_id}: {patch.message}",
                reason="patch_error",
            )
        if patch.status is not PatchFormatStatus.APPLIED:
            raise PREngineError(
                f"unsupported patch status: {patch.status}",
                reason="unsupported_patch",
            )
        if not patch.opportunity_id.strip():
            raise PREngineError("patch missing opportunity_id", reason="invalid_patch")
        path = normalize_repo_path(patch.file_path)
        by_path[path].append(patch)

    if not by_path:
        raise PREngineError(
            "no APPLIED patches to commit (only no-ops)",
            reason="empty_patch_set",
        )
    return dict(sorted(by_path.items(), key=lambda item: item[0]))


def build_report_data(
    request: PREngineRequest, file_updates: Sequence[ValidatedRepoFileUpdate]
) -> PRReportData:
    """Assemble PRReportData from Phase 3.4 projections and pipeline metadata."""
    if request.projections:
        current = request.projections[0].current_score
        # Independent projections: report the best (max) projected improvement.
        best = max(request.projections, key=lambda p: p.projected_score)
        projected = best.projected_score
        delta = projected - current
    elif request.current_score is not None and request.projected_score is not None:
        current = request.current_score
        projected = request.projected_score
        delta = projected - current
    elif request.opportunities:
        current = request.current_score or 0.0
        opp_delta = sum(o.impact for o in request.opportunities)
        projected = min(100.0, current + opp_delta)
        delta = projected - current
    else:
        current = 0.0
        projected = 0.0
        delta = 0.0

    gaps: list[str] = []
    for opp in request.opportunities:
        if opp.schema_target is not None:
            gaps.append(f"Missing {opp.schema_target.value}")
        else:
            gaps.append(opp.title)
    if not gaps and request.patches:
        for p in request.patches:
            gaps.append(f"Missing {p.schema_type.value}")
    # Stable unique
    seen_gaps: set[str] = set()
    ordered_gaps: list[str] = []
    for gap in gaps:
        if gap not in seen_gaps:
            seen_gaps.add(gap)
            ordered_gaps.append(gap)

    evidence: list[EvidenceReference] = []
    seen_ev: set[tuple[str, str]] = set()
    for opp in request.opportunities:
        for ref in opp.evidence.evidence_references:
            key = (ref.chunk_id, ref.dom_path)
            if key in seen_ev:
                continue
            seen_ev.add(key)
            evidence.append(ref)
    for evaluation in request.intent_evaluations:
        for ref in evaluation.evidence:
            key = (ref.chunk_id, ref.dom_path)
            if key in seen_ev:
                continue
            seen_ev.add(key)
            evidence.append(ref)

    file_changes = [
        PRFileChange(
            path=update.path,
            summary="Added Schema.org JSON-LD: " + ", ".join(t.value for t in update.schema_types),
            opportunity_ids=list(update.opportunity_ids),
            schema_types=[t.value for t in update.schema_types],
        )
        for update in file_updates
    ]

    opp_titles = [o.title for o in request.opportunities]
    if not opp_titles and request.patches:
        opp_titles = [p.message for p in request.patches if p.message]

    return PRReportData(
        scan_id=request.scan_id,
        current_score=current,
        projected_score=projected,
        delta=delta,
        detected_gaps=ordered_gaps,
        intent_evaluations=list(request.intent_evaluations),
        evidence_items=evidence,
        file_changes=file_changes,
        opportunity_titles=opp_titles,
    )


def resolve_target_file(tree_files: Sequence[str], path_hint: str) -> tuple[str | None, str]:
    """Search tree_files for target match.

    Returns (resolved_path, kind) where kind is:
      - 'html': direct HTML target found
      - 'framework': framework component found (.tsx, .jsx, .vue, .astro, .svelte, .js, .ts)
      - 'none': no match or ambiguous matches
    """
    if not tree_files:
        return (None, "none")

    # 1. Exact match
    for f in tree_files:
        if f.lower() == path_hint.lower():
            if f.lower().endswith((".html", ".htm")):
                return (f, "html")
            return (f, "framework")

    # 2. Heuristic Stem Search
    stem = path_hint.replace("\\", "/").rsplit("/", 1)[-1].split(".")[0].lower()
    if stem in ("index", "home", "root", "default"):
        # Root page search
        html_roots = [
            f for f in tree_files
            if f.lower() in ("public/index.html", "index.html", "index.htm", "static/index.html", "src/index.html")
        ]
        if html_roots:
            return (html_roots[0], "html")

        framework_roots = [
            f for f in tree_files
            if f.lower() in (
                "app/page.tsx", "app/page.jsx", "app/page.js", "app/layout.tsx",
                "src/app/page.tsx", "src/app/page.jsx", "src/app/page.js",
                "pages/index.tsx", "pages/index.jsx", "pages/index.js",
                "src/pages/index.tsx", "src/pages/index.jsx",
                "src/app.vue", "src/app.tsx", "src/app.jsx",
            )
        ]
        if framework_roots:
            return (framework_roots[0], "framework")

    # For other stems (e.g. 'about', 'pricing', 'contact', 'events', 'faq')
    html_matches = [
        f for f in tree_files
        if f.lower().endswith((".html", ".htm")) and (
            f.lower().endswith(f"/{stem}.html") or f.lower().endswith(f"/{stem}.htm") or f.lower() == f"{stem}.html"
        )
    ]
    if len(html_matches) == 1:
        return (html_matches[0], "html")

    framework_exts = (".tsx", ".jsx", ".vue", ".astro", ".svelte", ".js", ".ts")
    framework_matches = [
        f for f in tree_files
        if f.lower().endswith(framework_exts) and (
            f"/{stem}/page." in f"/{f.lower()}"
            or f"/{stem}." in f"/{f.lower()}"
            or f"/{stem}/index." in f"/{f.lower()}"
            or f.lower().endswith(f"/{stem}")
        )
    ]
    if len(framework_matches) == 1:
        return (framework_matches[0], "framework")

    return (None, "none")


def generate_remediation_guide(
    request: PREngineRequest,
    grouped_patches: dict[str, list[FormattedPatch]],
    matched_files: dict[str, tuple[str | None, str]],
) -> str:
    lines = [
        "# FindableAI Machine Discoverability Remediation Guidelines",
        "",
        f"Scan ID: `{request.scan_id}`",
        "",
        "> [!NOTE]",
        "> Automated direct HTML injection was skipped because target source files are framework components (.tsx, .jsx, .vue, .astro) or require developer placement. Follow the code snippets and schema definitions below to implement the recommended enhancements in your source codebase.",
        "",
        "## Recommended Schema.org Microdata & Component Patches",
        "",
    ]
    for path, patches in grouped_patches.items():
        resolved_path, kind = matched_files.get(path, (None, "none"))
        target_display = f"`{resolved_path}` ({kind})" if resolved_path else f"`{path}` (unmatched route)"
        lines.append(f"### Target: {target_display}")
        lines.append("")
        for p in patches:
            lines.append(f"#### Opportunity: {p.opportunity_id} - Schema `{p.schema_type.value}`")
            if p.message:
                lines.append(f"**Rationale:** {p.message}")
                lines.append("")
            if p.patched_html:
                lines.append("```html")
                lines.append(p.patched_html.strip())
                lines.append("```")
                lines.append("")
            if p.patch_text:
                lines.append("<details>")
                lines.append("<summary>View Suggested Code Diff</summary>")
                lines.append("")
                lines.append("```diff")
                lines.append(p.patch_text.strip())
                lines.append("```")
                lines.append("</details>")
                lines.append("")
    return "\n".join(lines) + "\n"


class GitHubPRService:
    """Orchestrates fork → branch → apply validated patches → commit → PR."""

    def __init__(self, github_client: GitHubClient) -> None:
        self._client = github_client

    def create_remediation_pr(self, request: PREngineRequest) -> PREngineResult:
        if not isinstance(request, PREngineRequest):
            raise PREngineError("request must be PREngineRequest", reason="invalid_input")

        # --- Local validation before any mutation ---
        grouped = validate_and_prepare_updates(request.patches)
        branch_name = build_feature_branch_name(request.scan_id)

        try:
            login = self._client.get_authenticated_login()
        except GitHubClientError as exc:
            raise PREngineError(str(exc), reason=exc.reason) from exc
        if not login:
            raise PREngineError("authentication failure", reason="auth_failure")

        try:
            source = self._client.get_repository(request.source_repo)
        except GitHubClientError as exc:
            raise PREngineError(str(exc), reason=exc.reason) from exc

        target_branch = request.target_branch.strip()
        if not target_branch:
            raise PREngineError("target_branch required", reason="invalid_branch")

        can_push_directly = self._client.has_push_access(source)
        if can_push_directly:
            work_repo = source
            head_label = branch_name
            find_head_labels = [branch_name, f"{login}:{branch_name}", f"{source.owner_login}:{branch_name}"]
        else:
            try:
                fork = self._client.get_or_create_fork(source)
            except GitHubClientError as exc:
                raise PREngineError(str(exc), reason=exc.reason) from exc
            if fork.owner_login != login:
                raise PREngineError(
                    "fork owner does not match authenticated user",
                    reason="wrong_fork",
                )
            if fork.full_name.split("/", 1)[1] != source.full_name.split("/", 1)[1]:
                raise PREngineError("fork name mismatch", reason="wrong_fork")
            work_repo = fork
            head_label = f"{login}:{branch_name}"
            find_head_labels = [f"{login}:{branch_name}"]

        # Idempotency: existing open PR for same head/base
        existing = None
        for h_label in find_head_labels:
            try:
                existing = self._client.find_open_pull(source, head_full=h_label, base=target_branch)
            except GitHubClientError as exc:
                raise PREngineError(str(exc), reason=exc.reason) from exc
            if existing is not None:
                break

        if existing is not None:
            report = self._build_report_for_existing(request, grouped)
            body = generate_pr_markdown(report)
            return PREngineResult(
                source_repository=source.full_name,
                fork_repository=work_repo.full_name,
                target_branch=target_branch,
                generated_branch=branch_name,
                commit_sha="",
                pr_number=existing.number,
                pr_url=existing.url,
                changed_files=sorted(grouped.keys()),
                applied_opportunity_ids=self._opportunity_ids(grouped),
                current_score=report.current_score,
                projected_score=report.projected_score,
                delta=report.delta,
                pr_body=body,
                reused_existing_pr=True,
                markdown_scan_id=request.scan_id,
            )

        try:
            base_sha = self._client.get_branch_sha(work_repo, target_branch)
        except GitHubClientError:
            # Fall back to work_repo default branch tip when target only exists on source
            try:
                base_sha = self._client.get_branch_sha(work_repo, work_repo.default_branch)
            except GitHubClientError as exc:
                raise PREngineError(str(exc), reason=exc.reason) from exc

        if self._client.branch_exists(work_repo, branch_name):
            raise PREngineError(
                f"feature branch already exists: {branch_name}",
                reason="branch_exists",
            )

        # Fetch repo file tree to check for exact/heuristic file matches
        try:
            tree_files = self._client.list_files(work_repo, ref=target_branch)
        except GitHubClientError:
            try:
                tree_files = self._client.list_files(work_repo, ref=work_repo.default_branch)
            except GitHubClientError:
                tree_files = []

        matched_files: dict[str, tuple[str | None, str]] = {}
        for path in grouped:
            matched_files[path] = resolve_target_file(tree_files, path)

        # Check if all patches match actual HTML files that can be directly patched
        all_html_matches = (
            len(tree_files) > 0
            and all(kind == "html" and res_path is not None for res_path, kind in matched_files.values())
        )

        prepared: list[ValidatedRepoFileUpdate] = []
        guidance_mode = not all_html_matches

        if not guidance_mode:
            try:
                for path, path_patches in grouped.items():
                    target_file_path = matched_files[path][0] or path
                    try:
                        remote = self._client.get_file(work_repo, target_file_path, ref=target_branch)
                    except GitHubClientError:
                        remote = self._client.get_file(work_repo, target_file_path, ref=work_repo.default_branch)

                    new_content = combine_patches_for_file(
                        base_html=remote.content,
                        patches=path_patches,
                    )
                    if new_content == remote.content:
                        raise PREngineError(
                            f"patch produced no content change for {target_file_path}",
                            reason="noop_after_merge",
                        )
                    prepared.append(
                        ValidatedRepoFileUpdate(
                            path=target_file_path,
                            content=new_content,
                            opportunity_ids=[p.opportunity_id for p in path_patches],
                            schema_types=[p.schema_type for p in path_patches],
                        )
                    )
            except (PREngineError, GitHubClientError) as prep_err:
                logger.info("Direct HTML patch preparation failed, falling back to guidance PR: %s", prep_err)
                guidance_mode = True
                prepared = []

        if guidance_mode:
            guide_path = "docs/FINDABLE_AI_REMEDIATION.md"
            guide_content = generate_remediation_guide(request, grouped, matched_files)
            prepared = [
                ValidatedRepoFileUpdate(
                    path=guide_path,
                    content=guide_content,
                    opportunity_ids=self._opportunity_ids(grouped),
                    schema_types=[p.schema_type for patches in grouped.values() for p in patches],
                )
            ]
            report = build_report_data(request, prepared)
            body = (
                "> [!NOTE]\n"
                "> **Action Required:** Target source files for one or more recommendations are framework components "
                "(.tsx, .jsx, .vue, .astro) or could not be auto-modified directly without risking syntax corruption. "
                f"Complete remediation guidelines, Schema.org payloads, and DOM insertion points have been committed to `{guide_path}` in this branch.\n\n"
                + generate_pr_markdown(report)
            )
        else:
            report = build_report_data(request, prepared)
            body = generate_pr_markdown(report)

        # --- Mutations ---
        try:
            self._client.create_branch(work_repo, branch_name, base_sha)
        except GitHubClientError as exc:
            raise PREngineError(str(exc), reason=exc.reason) from exc

        commit_sha = base_sha
        for update in prepared:
            remote_sha = None
            try:
                remote = self._client.get_file(work_repo, update.path, ref=branch_name)
                remote_sha = remote.sha
            except GitHubClientError:
                remote_sha = None
            try:
                commit_sha = self._client.create_or_update_file(
                    work_repo,
                    path=update.path,
                    content=update.content,
                    message=request.commit_message,
                    branch=branch_name,
                    sha=remote_sha,
                )
            except GitHubClientError as exc:
                raise PREngineError(str(exc), reason=exc.reason) from exc

        try:
            pull = self._client.create_pull(
                source,
                title=request.pr_title,
                body=body,
                head=head_label,
                base=target_branch,
            )
        except GitHubClientError as exc:
            raise PREngineError(str(exc), reason=exc.reason) from exc

        logger.info(
            "Created remediation PR %s for scan %s (files=%d, direct_push=%s, guidance_mode=%s)",
            pull.number,
            request.scan_id,
            len(prepared),
            can_push_directly,
            guidance_mode,
        )
        return PREngineResult(
            source_repository=source.full_name,
            fork_repository=work_repo.full_name,
            target_branch=target_branch,
            generated_branch=branch_name,
            commit_sha=commit_sha,
            pr_number=pull.number,
            pr_url=pull.url,
            changed_files=[u.path for u in prepared],
            applied_opportunity_ids=self._opportunity_ids(grouped),
            current_score=report.current_score,
            projected_score=report.projected_score,
            delta=report.delta,
            pr_body=body,
            reused_existing_pr=False,
            markdown_scan_id=request.scan_id,
        )

    def _build_report_for_existing(
        self,
        request: PREngineRequest,
        grouped: dict[str, list[FormattedPatch]],
    ) -> PRReportData:
        updates = [
            ValidatedRepoFileUpdate(
                path=path,
                content="",
                opportunity_ids=[p.opportunity_id for p in patches],
                schema_types=[p.schema_type for p in patches],
            )
            for path, patches in grouped.items()
        ]
        return build_report_data(request, updates)

    @staticmethod
    def _opportunity_ids(grouped: dict[str, list[FormattedPatch]]) -> list[str]:
        ids: list[str] = []
        for patches in grouped.values():
            for patch in patches:
                if patch.opportunity_id not in ids:
                    ids.append(patch.opportunity_id)
        return sorted(ids)


def create_github_pr_service_from_settings() -> GitHubPRService:
    """App-boundary factory using centralized settings (token never logged)."""
    from app.core.config import settings
    from app.github.client import build_pygithub_client_from_token

    client = build_pygithub_client_from_token(settings.GITHUB_TOKEN)
    return GitHubPRService(client)
