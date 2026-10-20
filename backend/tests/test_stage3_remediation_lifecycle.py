"""Stage 3: remediation lifecycle FSM, patch safety, verification honesty."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from app.core.auth import TenantContext
from app.core.budget import LLMBudgetExceededError
from app.engines.patch_validator import (
    CheckStatus,
    validate_no_secrets,
    validate_patch_candidate,
    validate_repo_path,
)
from app.orchestration.remediation_budget import (
    assert_github_mutation_not_tied_to_llm_budget,
    budget_guard_from_scan_usage,
    reserve_remediation_llm_call,
)
from app.orchestration.remediation_lifecycle import (
    OUTCOME_FIXED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_UNRESOLVED,
    STATE_BLOCKED,
    STATE_FAILED,
    STATE_MUTATING,
    STATE_PR_OPEN,
    STATE_PR_PERSIST_FAILED,
    STATE_READY,
    STATE_VALIDATION_FAILED,
    STATE_VERIFIED,
    STATE_VERIFYING,
    IdempotencyScopeConflict,
    InvalidLifecycleTransition,
    assert_valid_transition,
    can_transition,
    evaluate_verification_outcome,
    lifecycle_state_for_verification_outcome,
    make_idempotency_key,
    persist_verification_run,
    upsert_remediation_run,
)


def _admin_request() -> Request:
    req = Request({"type": "http", "headers": [], "method": "POST", "path": "/"})
    req.state.tenant = TenantContext(is_system_admin=True)
    return req


def test_lifecycle_transition_graph_allows_happy_path():
    assert can_transition(None, STATE_MUTATING)
    assert can_transition(STATE_MUTATING, STATE_PR_OPEN)
    assert can_transition(STATE_PR_OPEN, STATE_VERIFYING)
    assert can_transition(STATE_VERIFYING, STATE_VERIFIED)
    assert_valid_transition(STATE_PR_OPEN, STATE_VERIFYING)


def test_lifecycle_rejects_illegal_transitions():
    assert not can_transition(STATE_VALIDATION_FAILED, STATE_PR_OPEN)
    assert not can_transition(STATE_VERIFIED, STATE_MUTATING)
    with pytest.raises(InvalidLifecycleTransition):
        assert_valid_transition(STATE_READY, STATE_PR_OPEN)


def test_verification_outcome_maps_to_lifecycle_states():
    assert lifecycle_state_for_verification_outcome(OUTCOME_FIXED) == STATE_VERIFIED
    assert lifecycle_state_for_verification_outcome(OUTCOME_UNRESOLVED) == STATE_FAILED
    assert lifecycle_state_for_verification_outcome(OUTCOME_INCONCLUSIVE) == STATE_BLOCKED


def test_projected_score_is_not_verification():
    outcome, ops, detail = evaluate_verification_outcome(
        original_issue_keywords=["hours", "open"],
        patched_content="<html><body>Welcome</body></html>",
        validation_passed=True,
    )
    assert outcome == OUTCOME_UNRESOLVED
    assert ops == "ok"
    assert "acceptance" in detail.lower() or "lacks" in detail.lower()


def test_pr_open_alone_never_marks_fixed():
    outcome, ops, _detail = evaluate_verification_outcome(
        original_issue_keywords=None,
        patched_content=None,
        validation_passed=True,
        operational_error=None,
    )
    assert outcome == OUTCOME_INCONCLUSIVE
    assert ops == "skipped"


def test_path_policy_rejects_workflows_env_lockfiles_unc():
    assert validate_repo_path(".github/workflows/deploy.yml").status == CheckStatus.FAILED
    assert validate_repo_path(".env").status == CheckStatus.FAILED
    assert validate_repo_path("package-lock.json").status == CheckStatus.FAILED
    assert validate_repo_path("//server/share/index.html").status == CheckStatus.FAILED
    assert validate_repo_path("index\x00.html").status == CheckStatus.FAILED
    assert validate_repo_path("index.html").status == CheckStatus.PASSED
    assert validate_repo_path("src/app/page.tsx").status == CheckStatus.PASSED


def test_path_normalization_rejects_traversal_variants():
    assert validate_repo_path("foo/../../etc/passwd").status == CheckStatus.FAILED
    assert validate_repo_path("C:/Windows/system32/file.html").status == CheckStatus.FAILED
    assert validate_repo_path("/abs/index.html").status == CheckStatus.FAILED


def test_secret_patterns_block_patch():
    leak = (
        "--- a/index.html\n+++ b/index.html\n+<!-- ghp_abcdefghijklmnopqrstuvwxyz0123456789 -->\n"
    )
    check = validate_no_secrets(leak)
    assert check.status == CheckStatus.FAILED
    assert check.safety_critical is True

    result = validate_patch_candidate(
        file_path="index.html",
        patch_text=leak,
        is_synthetic=False,
        require_evidence=False,
        current_file_content="<html><body></body></html>",
    )
    assert result.eligible_for_validated_pr is False
    assert any(c.name == "no_secrets" and c.status == CheckStatus.FAILED for c in result.checks)


def test_empty_and_oversized_patches_fail():
    empty = validate_patch_candidate(
        file_path="index.html",
        patch_text="",
        require_evidence=False,
        current_file_content="<html></html>",
    )
    assert empty.eligible_for_validated_pr is False
    huge = validate_patch_candidate(
        file_path="index.html",
        patch_text="+" + ("x" * 250_000),
        require_evidence=False,
        current_file_content="<html></html>",
    )
    assert huge.eligible_for_validated_pr is False


def _session_returning(row):
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = row
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_upsert_idempotent_retry_same_scan_identity():
    """Identical retries must reuse the same scan identity in the key and row."""
    scan_id = uuid.uuid4()
    key = make_idempotency_key(str(scan_id), "owner/repo", "main")
    session = _session_returning(None)
    created = await upsert_remediation_run(
        session,
        scan_id=scan_id,
        idempotency_key=key,
        repo_full_name="owner/repo",
        base_branch="main",
        lifecycle_state=STATE_MUTATING,
    )
    assert created.lifecycle_state == STATE_MUTATING
    assert created.scan_id == scan_id

    existing = SimpleNamespace(
        id=uuid.uuid4(),
        scan_id=scan_id,
        lifecycle_state=STATE_PR_PERSIST_FAILED,
        pr_number=42,
        pr_url="https://github.com/owner/repo/pull/42",
        repo_full_name="owner/repo",
        base_sha=None,
        head_branch=None,
        head_sha=None,
        changed_files=[],
        validation_results=[],
        error="persist failed",
        updated_at=None,
        state_revision=1,
    )
    session = _session_returning(existing)
    recovered = await upsert_remediation_run(
        session,
        scan_id=scan_id,  # same scan — not a new random UUID
        idempotency_key=key,
        repo_full_name="owner/repo",
        base_branch="main",
        lifecycle_state=STATE_MUTATING,
    )
    assert recovered.lifecycle_state == STATE_PR_OPEN
    assert recovered.scan_id == scan_id
    assert recovered.error is None


@pytest.mark.asyncio
async def test_idempotency_cross_scan_isolation():
    """Different scans must not share remediation idempotency state."""
    scan_a = uuid.uuid4()
    scan_b = uuid.uuid4()
    key_a = make_idempotency_key(str(scan_a), "owner/repo", "main")
    key_b = make_idempotency_key(str(scan_b), "owner/repo", "main")
    assert key_a != key_b

    existing = SimpleNamespace(
        id=uuid.uuid4(),
        scan_id=scan_a,
        lifecycle_state=STATE_PR_OPEN,
        pr_number=1,
        pr_url="https://github.com/owner/repo/pull/1",
        repo_full_name="owner/repo",
        base_sha=None,
        head_branch="b",
        head_sha="abc",
        changed_files=[],
        validation_results=[],
        error=None,
        updated_at=None,
        state_revision=2,
    )
    session = _session_returning(existing)
    with pytest.raises(IdempotencyScopeConflict):
        await upsert_remediation_run(
            session,
            scan_id=scan_b,
            idempotency_key=key_a,  # hostile reuse of scan A's key
            repo_full_name="owner/repo",
            base_branch="main",
            lifecycle_state=STATE_MUTATING,
        )


@pytest.mark.asyncio
async def test_idempotency_cross_repo_isolation():
    scan_id = uuid.uuid4()
    key = make_idempotency_key(str(scan_id), "owner/repo-a", "main")
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        scan_id=scan_id,
        lifecycle_state=STATE_MUTATING,
        pr_number=None,
        pr_url=None,
        repo_full_name="owner/repo-a",
        base_sha=None,
        head_branch=None,
        head_sha=None,
        changed_files=[],
        validation_results=[],
        error=None,
        updated_at=None,
        state_revision=0,
    )
    session = _session_returning(existing)
    with pytest.raises(IdempotencyScopeConflict):
        await upsert_remediation_run(
            session,
            scan_id=scan_id,
            idempotency_key=key,
            repo_full_name="owner/repo-b",
            base_branch="main",
            lifecycle_state=STATE_PR_OPEN,
        )


@pytest.mark.asyncio
async def test_upsert_rejects_illegal_transition():
    scan_id = uuid.uuid4()
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        scan_id=scan_id,
        lifecycle_state=STATE_VALIDATION_FAILED,
        pr_number=None,
        pr_url=None,
        repo_full_name="owner/repo",
        base_sha=None,
        head_branch=None,
        head_sha=None,
        changed_files=[],
        validation_results=[],
        error="blocked",
        updated_at=None,
        state_revision=0,
    )
    session = _session_returning(existing)
    with pytest.raises(InvalidLifecycleTransition):
        await upsert_remediation_run(
            session,
            scan_id=scan_id,
            idempotency_key=make_idempotency_key(str(scan_id), "owner/repo", "main"),
            repo_full_name="owner/repo",
            base_branch="main",
            lifecycle_state=STATE_PR_OPEN,
        )


@pytest.mark.asyncio
async def test_persist_verification_forces_heuristic_honesty():
    session = _session_returning(None)
    row = await persist_verification_run(
        session,
        scan_id=uuid.uuid4(),
        remediation_run_id=uuid.uuid4(),
        evaluated_revision="abc123",
        issue_outcome=OUTCOME_FIXED,
        operational_status="ok",
        detail="heuristic hit",
        fully_verified=True,
        is_full_rescan=True,
    )
    assert row.fully_verified is False
    assert row.is_full_rescan is False
    assert row.verification_method == "heuristic_post_pr"


def test_idempotency_key_includes_scan_repo_branch():
    assert make_idempotency_key("scan_1", "a/b", "main") == "scan_1|a/b|main"
    assert make_idempotency_key("scan_1", "a/b", "main") != make_idempotency_key(
        "scan_2", "a/b", "main"
    )


@pytest.mark.asyncio
async def test_remediation_llm_budget_exhaustion_blocks_provider_call():
    from app.core.config import settings

    guard = budget_guard_from_scan_usage(llm_calls_made=settings.MAX_LLM_CALLS_PER_SCAN)
    with pytest.raises(LLMBudgetExceededError):
        await reserve_remediation_llm_call(guard)

    assert_github_mutation_not_tied_to_llm_budget(would_call_llm=False, guard=guard)
    with pytest.raises(LLMBudgetExceededError):
        assert_github_mutation_not_tied_to_llm_budget(would_call_llm=True, guard=guard)


@pytest.mark.asyncio
async def test_e2e_lifecycle_negative_unsafe_patch_never_mutates(monkeypatch):
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_mod
    from app.schemas.intelligence import (
        EntailmentStatus,
        EvidenceReference,
        IntentCategory,
        IntentEvaluation,
    )
    from app.schemas.patch import DOMSelectorAnchor, PatchProposal, PatchType
    from app.schemas.scan import ScanResponse, ScanStatus

    scan_id = f"scan_{uuid.uuid4().hex}"
    chunk_id = str(uuid.uuid4())
    record = ScanResponse(
        scan_id=scan_id,
        target_url="https://example.com",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        remediation_eligible=True,
        execution_mode="real_llm",
        result_source="real_pipeline",
        outcome="success",
        patches_source="assembler",
        repo_url="https://github.com/example/demo",
        intents=[
            IntentEvaluation(
                intent_id="intent_1",
                query="Hours?",
                category=IntentCategory.AVAILABILITY,
                persona="cto",
                status=EntailmentStatus.SUPPORTED,
                reasoning="ok",
                evidence=[
                    EvidenceReference(
                        chunk_id=chunk_id,
                        dom_path="main > p",
                        rank=1,
                        excerpt="Open 9-5",
                    )
                ],
                confidence=0.9,
            )
        ],
        patches=[
            PatchProposal(
                patch_id="patch_bad",
                patch_type=PatchType.SCHEMA_MICRODATA,
                title="Leak secrets",
                rationale="bad",
                impact_score_delta=1.0,
                dom_anchor=DOMSelectorAnchor(
                    css_selector="head",
                    tag_name="head",
                    original_snippet="",
                    suggested_snippet="",
                ),
                unified_diff=(
                    "--- a/index.html\n+++ b/index.html\n+<!-- AKIAIOSFODNN7EXAMPLEXX -->\n"
                ),
                target_file="index.html",
                is_synthetic=False,
            )
        ],
    )
    scans_mod.SCANS_DB[scan_id] = record
    monkeypatch.setattr(
        scans_mod.settings,
        "GITHUB_TOKEN",
        "ghs_test_token_not_used",
        raising=False,
    )

    create_called = {"n": 0}

    class _Boom:
        def create_remediation_pr(self, *_a, **_k):
            create_called["n"] += 1
            raise AssertionError("GitHub must not be called for unsafe patches")

    monkeypatch.setattr(scans_mod, "GitHubPRService", lambda *_a, **_k: _Boom())
    monkeypatch.setattr(scans_mod, "build_pygithub_client_from_token", lambda *_a, **_k: object())
    monkeypatch.setattr(scans_mod, "resolve_scan_uuid", lambda _sid: None)
    monkeypatch.setattr(scans_mod, "_authorize_scan_ref", AsyncMock(return_value=None))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await scans_mod.apply_scan_patch(scan_id, _admin_request())
    # Phase 3: no durable UUID → cache-only eligibility rejects (422), never GitHub.
    assert exc_info.value.status_code in (400, 422)
    assert create_called["n"] == 0
    scans_mod.SCANS_DB.pop(scan_id, None)


@pytest.mark.asyncio
async def test_verify_maps_unresolved_to_failed_lifecycle(monkeypatch):
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_mod
    from app.schemas.scan import ScanResponse, ScanStatus

    scan_uuid = uuid.uuid4()
    scan_id = str(scan_uuid)
    run_id = uuid.uuid4()
    run = SimpleNamespace(
        id=run_id,
        idempotency_key=make_idempotency_key(scan_id, "owner/repo", "main"),
        repo_full_name="owner/repo",
        base_branch="main",
        head_branch="findableai/remediation/x",
        head_sha="deadbeef",
        pr_number=7,
        pr_url="https://github.com/owner/repo/pull/7",
        lifecycle_state=STATE_PR_OPEN,
        changed_files=["index.html"],
        state_revision=0,
    )
    scans_mod.SCANS_DB[scan_id] = ScanResponse(
        scan_id=scan_id,
        target_url="https://example.com",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
        remediation_eligible=True,
        intents=[],
        patches=[],
    )
    monkeypatch.setattr(scans_mod, "resolve_scan_uuid", lambda _s: scan_uuid)
    monkeypatch.setattr(scans_mod.settings, "GITHUB_TOKEN", "token", raising=False)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def begin(self):
            return self

    class _SessionFactory:
        def __call__(self):
            return _Session()

    states: list[str] = []

    async def _get_runs(_s, _sid):
        return [run]

    async def _upsert(_s, **kwargs):
        states.append(kwargs["lifecycle_state"])
        run.lifecycle_state = kwargs["lifecycle_state"]
        if kwargs.get("head_sha"):
            run.head_sha = kwargs["head_sha"]
        return run

    async def _persist(_s, **kwargs):
        return SimpleNamespace(
            id=uuid.uuid4(),
            scan_id=scan_uuid,
            remediation_run_id=run_id,
            evaluated_revision=kwargs.get("evaluated_revision") or "deadbeef",
            issue_outcome=kwargs["issue_outcome"],
            operational_status=kwargs["operational_status"],
            detail=kwargs["detail"],
            fresh_evidence=kwargs.get("fresh_evidence") or [],
            created_at=datetime.now(UTC),
            verification_method="heuristic_post_pr",
            fully_verified=False,
            is_full_rescan=False,
        )

    class _File:
        content = "<html><body>no keywords here</body></html>"
        sha = "deadbeef"

    class _Gh:
        def get_repository(self, _n):
            return object()

        def get_file(self, _r, _p, ref=None):
            assert ref == "deadbeef"
            return _File()

        def get_branch_sha(self, _r, _b):
            return "deadbeef"

    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", _SessionFactory())
    monkeypatch.setattr(scans_mod, "get_runs_for_scan", _get_runs)
    monkeypatch.setattr(scans_mod, "upsert_remediation_run", _upsert)
    monkeypatch.setattr(scans_mod, "persist_verification_run", _persist)
    monkeypatch.setattr(scans_mod, "build_pygithub_client_from_token", lambda *_a, **_k: _Gh())
    monkeypatch.setattr(scans_mod, "_authorize_scan_ref", AsyncMock(return_value=scan_uuid))

    from app.schemas.remediation import VerifyRemediationRequest

    out = await scans_mod.verify_scan_remediation(
        scan_id,
        _admin_request(),
        VerifyRemediationRequest(acceptance_keywords=["hours", "opentable"]),
    )
    assert out.issue_outcome == OUTCOME_UNRESOLVED
    assert out.fully_verified is False
    assert out.evaluated_revision == "deadbeef"
    assert STATE_VERIFYING in states
    assert STATE_FAILED in states
    assert STATE_VERIFIED not in states
    scans_mod.SCANS_DB.pop(scan_id, None)


@pytest.mark.asyncio
async def test_verify_blocks_when_pr_head_moves(monkeypatch):
    from datetime import UTC, datetime

    from app.api.v1 import scans as scans_mod
    from app.schemas.remediation import VerifyRemediationRequest
    from app.schemas.scan import ScanResponse, ScanStatus

    scan_uuid = uuid.uuid4()
    scan_id = str(scan_uuid)
    run_id = uuid.uuid4()
    run = SimpleNamespace(
        id=run_id,
        idempotency_key=make_idempotency_key(scan_id, "owner/repo", "main"),
        repo_full_name="owner/repo",
        base_branch="main",
        head_branch="findableai/remediation/x",
        head_sha="sha_old",
        pr_number=7,
        pr_url="https://github.com/owner/repo/pull/7",
        lifecycle_state=STATE_PR_OPEN,
        changed_files=["index.html"],
        state_revision=0,
    )
    scans_mod.SCANS_DB[scan_id] = ScanResponse(
        scan_id=scan_id,
        target_url="https://example.com",
        status=ScanStatus.COMPLETED,
        created_at=datetime.now(UTC),
        remediation_eligible=True,
        intents=[],
        patches=[],
    )
    monkeypatch.setattr(scans_mod, "resolve_scan_uuid", lambda _s: scan_uuid)
    monkeypatch.setattr(scans_mod.settings, "GITHUB_TOKEN", "token", raising=False)

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def begin(self):
            return self

    class _SessionFactory:
        def __call__(self):
            return _Session()

    async def _get_runs(_s, _sid):
        return [run]

    async def _upsert(_s, **kwargs):
        run.lifecycle_state = kwargs["lifecycle_state"]
        return run

    async def _persist(_s, **kwargs):
        return SimpleNamespace(
            id=uuid.uuid4(),
            scan_id=scan_uuid,
            remediation_run_id=run_id,
            evaluated_revision=kwargs.get("evaluated_revision"),
            issue_outcome=kwargs["issue_outcome"],
            operational_status=kwargs["operational_status"],
            detail=kwargs["detail"],
            fresh_evidence=[],
            created_at=datetime.now(UTC),
            verification_method="heuristic_post_pr",
            fully_verified=False,
            is_full_rescan=False,
        )

    class _File:
        content = "<html><body>hours opentable</body></html>"
        sha = "sha_old"

    class _Gh:
        def get_repository(self, _n):
            return object()

        def get_file(self, _r, _p, ref=None):
            return _File()

        def get_branch_sha(self, _r, _b):
            return "sha_new"  # tip moved

    monkeypatch.setattr(scans_mod, "AsyncSessionLocal", _SessionFactory())
    monkeypatch.setattr(scans_mod, "get_runs_for_scan", _get_runs)
    monkeypatch.setattr(scans_mod, "upsert_remediation_run", _upsert)
    monkeypatch.setattr(scans_mod, "persist_verification_run", _persist)
    monkeypatch.setattr(scans_mod, "build_pygithub_client_from_token", lambda *_a, **_k: _Gh())
    monkeypatch.setattr(scans_mod, "_authorize_scan_ref", AsyncMock(return_value=scan_uuid))

    out = await scans_mod.verify_scan_remediation(
        scan_id,
        _admin_request(),
        VerifyRemediationRequest(acceptance_keywords=["hours", "opentable"]),
    )
    assert out.issue_outcome == OUTCOME_INCONCLUSIVE
    assert out.fully_verified is False
    assert "moved" in (out.detail or "").lower() or "stale" in (out.detail or "").lower()
    scans_mod.SCANS_DB.pop(scan_id, None)
