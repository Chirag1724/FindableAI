"""Unit tests for P2-3.5 GitHub PR Engine (mocked GitHub only)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.github.client import FakeGitHubClient, GitHubClientError, build_pygithub_client_from_token
from app.github.pr_engine import (
    GitHubPRService,
    PREngineError,
    build_feature_branch_name,
    combine_patches_for_file,
    normalize_repo_path,
    validate_and_prepare_updates,
)
from app.schemas.github_pr import PREngineRequest
from app.schemas.intelligence import EntailmentStatus, IntentEvaluation
from app.schemas.patching import (
    FormattedPatch,
    PatchFormatStatus,
    ProjectedScoreResult,
    RemediationKind,
    RemediationOpportunity,
    SchemaRemediationTarget,
)
from app.schemas.scoring import SchemaOrgReport, SchemaTypeResult, ScoreBreakdown, ScoreWeights

BASE_HTML = "<html><head><title>T</title></head><body>Hi</body></html>"


def _score_breakdown(f: float = 40.0) -> ScoreBreakdown:
    report = SchemaOrgReport(
        total_blocks=0,
        valid_blocks=0,
        invalid_blocks=0,
        malformed_blocks=0,
        required_types=["FAQPage"],
        types=[
            SchemaTypeResult(
                schema_type="FAQPage",
                present=False,
                valid=False,
                occurrences=0,
                source_count=0,
            )
        ],
        score=0.0,
        issues=[],
    )
    return ScoreBreakdown(
        f_score=f,
        s_ans=f,
        s_con=100.0,
        s_str=0.0,
        s_acc=50.0,
        weights=ScoreWeights(),
        schema_report=report,
    )


def _projection(
    *,
    opportunity_id: str = "missing_schema:FAQPage",
    current: float = 40.0,
    projected: float = 55.0,
) -> ProjectedScoreResult:
    cur = _score_breakdown(current)
    proj = _score_breakdown(projected)
    return ProjectedScoreResult(
        opportunity_id=opportunity_id,
        schema_type=SchemaRemediationTarget.FAQ_PAGE,
        current_score=current,
        projected_score=projected,
        delta=projected - current,
        current_breakdown=cur,
        projected_breakdown=proj,
        patch_reference="index.html",
    )


def _opp() -> RemediationOpportunity:
    impact, confidence, difficulty = 80.0, 1.0, 2
    return RemediationOpportunity(
        opportunity_id="missing_schema:FAQPage",
        kind=RemediationKind.MISSING_SCHEMA,
        title="Add FAQPage schema",
        reason="missing FAQPage",
        impact=impact,
        confidence=confidence,
        difficulty=difficulty,
        priority=(impact * confidence) / difficulty,
        schema_target=SchemaRemediationTarget.FAQ_PAGE,
        dedupe_key="MISSING_SCHEMA|FAQPage",
    )


def _applied_patch(
    *,
    opportunity_id: str = "missing_schema:FAQPage",
    schema: SchemaRemediationTarget = SchemaRemediationTarget.FAQ_PAGE,
    file_path: str = "index.html",
    patched: str | None = None,
) -> FormattedPatch:
    html = patched or (
        "<html><head><title>T</title>\n"
        '<script type="application/ld+json">\n'
        '{"@context":"https://schema.org","@type":"FAQPage",'
        '"mainEntity":[{"@type":"Question","name":"Q?",'
        '"acceptedAnswer":{"@type":"Answer","text":"A"}}]}\n'
        "</script>\n</head><body>Hi</body></html>"
    )
    return FormattedPatch(
        opportunity_id=opportunity_id,
        schema_type=schema,
        file_path=file_path,
        patch_text="--- a/index.html\n+++ b/index.html\n",
        changed_lines=5,
        insertion_location="before_head",
        is_noop=False,
        status=PatchFormatStatus.APPLIED,
        message="ok",
        patched_html=html,
    )


def _request(**overrides: object) -> PREngineRequest:
    data: dict[str, Any] = dict(
        source_repo="acme/demo-site",
        target_branch="main",
        scan_id="scan-42",
        patches=[_applied_patch()],
        projections=[_projection()],
        opportunities=[_opp()],
        intent_evaluations=[
            IntentEvaluation(
                intent_id="i1",
                query="FAQ?",
                status=EntailmentStatus.UNKNOWN,
                reasoning="x",
                evidence=[],
                confidence=0.5,
            )
        ],
    )
    data.update(overrides)
    return PREngineRequest(**data)  # type: ignore[arg-type]


def _service() -> tuple[GitHubPRService, FakeGitHubClient]:
    client = FakeGitHubClient(login="bot-user")
    client.seed_repo("acme/demo-site", files={"index.html": BASE_HTML})
    return GitHubPRService(client), client


# --- path / branch ---


def test_normalize_path_accepts_relative_html():
    assert normalize_repo_path("pages/index.html") == "pages/index.html"
    assert normalize_repo_path(r"pages\about.html") == "pages/about.html"


@pytest.mark.parametrize(
    "bad",
    [
        "C:/Users/x/index.html",
        "/etc/passwd",
        "../../README.md",
        "foo/../../bar.html",
        "script.js",
        "",
    ],
)
def test_normalize_path_rejects_unsafe(bad: str):
    with pytest.raises(PREngineError):
        normalize_repo_path(bad)


def test_branch_name_deterministic_and_sanitized():
    assert build_feature_branch_name("scan-42") == "findableai/remediation/scan-42"
    assert ".." not in build_feature_branch_name("a/../b")
    assert build_feature_branch_name("scan-42") == build_feature_branch_name("scan-42")


# --- patch validation ---


def test_validate_rejects_conflict_and_error_status():
    with pytest.raises(PREngineError, match="conflict"):
        validate_and_prepare_updates(
            [
                FormattedPatch(
                    opportunity_id="x",
                    schema_type=SchemaRemediationTarget.FAQ_PAGE,
                    file_path="index.html",
                    status=PatchFormatStatus.CONFLICT,
                    message="conflict",
                )
            ]
        )


def test_validate_skips_noop_only_set():
    with pytest.raises(PREngineError, match="no APPLIED"):
        validate_and_prepare_updates(
            [
                FormattedPatch(
                    opportunity_id="x",
                    schema_type=SchemaRemediationTarget.FAQ_PAGE,
                    file_path="index.html",
                    status=PatchFormatStatus.NOOP,
                    is_noop=True,
                    message="noop",
                    patched_html=BASE_HTML,
                )
            ]
        )


def test_combine_multiple_patches_same_file():
    p1 = _applied_patch(opportunity_id="a")
    p2_html = (
        "<html><head><title>T</title>\n"
        '<script type="application/ld+json">\n'
        '{"@type":"LocalBusiness","name":"N","telephone":"1"}\n'
        "</script>\n</head><body>Hi</body></html>"
    )
    p2 = _applied_patch(
        opportunity_id="b",
        schema=SchemaRemediationTarget.LOCAL_BUSINESS,
        patched=p2_html,
    )
    merged = combine_patches_for_file(base_html=BASE_HTML, patches=[p2, p1])
    assert merged.count("application/ld+json") == 2
    assert "FAQPage" in merged
    assert "LocalBusiness" in merged


# --- engine flow ---


def test_create_pr_happy_path():
    service, client = _service()
    result = service.create_remediation_pr(_request())
    assert result.pr_number == 1
    assert result.source_repository == "acme/demo-site"
    assert result.fork_repository == "bot-user/demo-site"
    assert result.generated_branch == "findableai/remediation/scan-42"
    assert result.commit_sha
    assert result.changed_files == ["index.html"]
    assert "42.0" in result.pr_body or "40.0" in result.pr_body
    assert "index.html" in result.pr_body
    assert any(c.startswith("create_pull:") for c in client.calls)
    assert result.reused_existing_pr is False
    # fork file updated
    fork_files = client._repos["bot-user/demo-site"].files[result.generated_branch]
    assert "FAQPage" in fork_files["index.html"][0]


def test_reuses_existing_pr():
    service, client = _service()
    first = service.create_remediation_pr(_request())
    # Seed duplicate open PR state already created; second call should reuse
    second = service.create_remediation_pr(_request())
    assert second.reused_existing_pr is True
    assert second.pr_number == first.pr_number
    create_calls = [c for c in client.calls if c.startswith("create_pull:")]
    assert len(create_calls) == 1


def test_branch_collision_rejected():
    service, client = _service()
    service.create_remediation_pr(_request(scan_id="scan-dup"))
    # Clear pulls so idempotency does not short-circuit, but leave branch
    client._repos["acme/demo-site"].pulls.clear()
    with pytest.raises(PREngineError, match="already exists"):
        service.create_remediation_pr(_request(scan_id="scan-dup"))


def test_missing_file_produces_guidance_pr():
    service, _client = _service()
    result = service.create_remediation_pr(_request(patches=[_applied_patch(file_path="missing.html")]))
    assert result.pr_number == 1
    assert result.changed_files == ["docs/FINDABLE_AI_REMEDIATION.md"]
    assert "docs/FINDABLE_AI_REMEDIATION.md" in result.pr_body


def test_repo_not_found():
    client = FakeGitHubClient()
    service = GitHubPRService(client)
    with pytest.raises(PREngineError) as exc:
        service.create_remediation_pr(_request())
    assert exc.value.reason == "not_found"


def test_auth_token_builder_rejects_empty():
    with pytest.raises(GitHubClientError) as exc:
        build_pygithub_client_from_token("")
    assert exc.value.reason == "auth_failure"


def test_no_token_logged(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)
    service, _ = _service()
    service.create_remediation_pr(_request())
    joined = " ".join(r.message for r in caplog.records)
    assert "ghp_" not in joined
    assert "Bearer" not in joined


def test_invalid_source_repo_schema():
    with pytest.raises(ValueError):
        PREngineRequest(
            source_repo="noslash",
            target_branch="main",
            scan_id="s",
            patches=[_applied_patch()],
            projections=[_projection()],
        )


def test_absolute_path_rejected_before_mutation():
    service, client = _service()
    with pytest.raises(PREngineError, match="path"):
        service.create_remediation_pr(_request(patches=[_applied_patch(file_path="../index.html")]))
    assert not any(c.startswith("create_branch:") for c in client.calls)


def test_create_pr_direct_push_same_repo():
    # User owns the repo (or has push access); creates branch directly on source without fork
    client = FakeGitHubClient(login="acme-bot")
    client.seed_repo("acme-bot/demo-site", files={"index.html": BASE_HTML}, allow_push=True)
    service = GitHubPRService(client)

    req = _request(source_repo="acme-bot/demo-site", scan_id="scan-direct-1")
    result = service.create_remediation_pr(req)

    assert result.source_repository == "acme-bot/demo-site"
    assert result.fork_repository == "acme-bot/demo-site"  # Direct push - work repo is source repo
    assert result.generated_branch == "findableai/remediation/scan-direct-1"
    assert result.pr_number == 1
    # Check no get_or_create_fork call was made
    assert not any(c.startswith("get_or_create_fork:") for c in client.calls)
    # Check create_pull used clean branch name as head (not owner:branch)
    assert "create_pull:acme-bot/demo-site:findableai/remediation/scan-direct-1->main" in client.calls


def test_create_pr_fork_fallback_when_no_push_access():
    # User lacks direct push access to source repo; must create fork
    client = FakeGitHubClient(login="contributor-user")
    client.seed_repo("upstream-org/target-site", files={"index.html": BASE_HTML}, allow_push=False)
    service = GitHubPRService(client)

    req = _request(source_repo="upstream-org/target-site", scan_id="scan-fork-1")
    result = service.create_remediation_pr(req)

    assert result.source_repository == "upstream-org/target-site"
    assert result.fork_repository == "contributor-user/target-site"
    assert any(c.startswith("get_or_create_fork:upstream-org/target-site") for c in client.calls)
    assert "create_pull:upstream-org/target-site:contributor-user:findableai/remediation/scan-fork-1->main" in client.calls


def test_create_pr_forking_disabled_raises_error():
    # User lacks direct push access AND forking is disabled on target repo
    client = FakeGitHubClient(login="external-user")
    client.seed_repo(
        "private-org/secret-site",
        files={"index.html": BASE_HTML},
        allow_push=False,
        allow_fork=False,
    )
    service = GitHubPRService(client)

    req = _request(source_repo="private-org/secret-site", scan_id="scan-disabled-1")
    with pytest.raises(PREngineError) as exc:
        service.create_remediation_pr(req)
    assert exc.value.reason == "forking_disabled"


def test_create_pr_framework_source_file_produces_guidance_pr():
    # When a framework file like app/about/page.tsx is found, engine produces guidance PR instead of direct JSX injection
    client = FakeGitHubClient(login="acme-bot")
    client.seed_repo(
        "acme-bot/nextjs-app",
        files={"app/about/page.tsx": "export default function Page() { return <div>About</div>; }"},
        allow_push=True,
    )
    service = GitHubPRService(client)

    req = _request(
        source_repo="acme-bot/nextjs-app",
        scan_id="scan-nextjs-1",
        patches=[_applied_patch(file_path="about.html")],
    )
    result = service.create_remediation_pr(req)

    assert result.source_repository == "acme-bot/nextjs-app"
    assert result.changed_files == ["docs/FINDABLE_AI_REMEDIATION.md"]
    assert result.pr_number == 1
    assert "docs/FINDABLE_AI_REMEDIATION.md" in result.pr_body
    # Verify no direct update was attempted on app/about/page.tsx
    assert not any("update_file:acme-bot/nextjs-app:app/about/page.tsx" in c for c in client.calls)


def test_create_pr_fuzzy_html_match_in_public_dir():
    # When HTML file is in public/index.html instead of root index.html, it auto-locates and commits direct diff to public/index.html
    client = FakeGitHubClient(login="acme-bot")
    client.seed_repo("acme-bot/static-app", files={"public/index.html": BASE_HTML}, allow_push=True)
    service = GitHubPRService(client)

    req = _request(
        source_repo="acme-bot/static-app",
        scan_id="scan-public-1",
        patches=[_applied_patch(file_path="index.html")],
    )
    result = service.create_remediation_pr(req)

    assert result.source_repository == "acme-bot/static-app"
    assert result.changed_files == ["public/index.html"]
    assert result.pr_number == 1
