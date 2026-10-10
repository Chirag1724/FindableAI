"""Stage 4: deterministic patch validation — skipped ≠ passed."""

from __future__ import annotations

import uuid

from app.engines.patch_validator import (
    CheckStatus,
    PatchValidationResult,
    ValidationCheck,
    validate_patch_candidate,
    validate_repo_path,
)
from app.orchestration.remediation_lifecycle import (
    OUTCOME_FIXED,
    OUTCOME_INCONCLUSIVE,
    OUTCOME_UNRESOLVED,
    evaluate_verification_outcome,
)


def test_path_traversal_rejected():
    assert validate_repo_path("../etc/passwd").status == CheckStatus.FAILED
    assert validate_repo_path("index.html").status == CheckStatus.PASSED


def test_inconclusive_safety_critical_blocks_validated_pr():
    result = PatchValidationResult(
        checks=[
            ValidationCheck(
                name="html_parse",
                status=CheckStatus.INCONCLUSIVE,
                detail="no html/head/body nodes found",
                safety_critical=True,
            )
        ]
    )
    assert result.failed_critical is True
    assert result.eligible_for_validated_pr is False


def test_synthetic_blocks_validated_pr():
    result = validate_patch_candidate(
        file_path="index.html",
        patch_text="--- a/index.html\n+++ b/index.html\n",
        is_synthetic=True,
        require_evidence=False,
        current_file_content="<html><head></head><body></body></html>",
    )
    assert result.eligible_for_validated_pr is False


def test_missing_evidence_blocks():
    result = validate_patch_candidate(
        file_path="index.html",
        patch_text="--- a/index.html\n+++ b/index.html\n",
        is_synthetic=False,
        evidence_chunk_ids=[],
        known_scan_chunk_ids={str(uuid.uuid4())},
        require_evidence=True,
        current_file_content="<html><body>hi</body></html>",
    )
    assert result.eligible_for_validated_pr is False
    assert any(c.name == "evidence_grounding" and c.status == CheckStatus.FAILED for c in result.checks)


def test_owned_evidence_and_html_pass():
    cid = str(uuid.uuid4())
    html = '<html><head><script type="application/ld+json">{"@type":"Organization"}</script></head><body></body></html>'
    result = validate_patch_candidate(
        file_path="index.html",
        patch_text="--- a/index.html\n+++ b/index.html\n+x\n",
        is_synthetic=False,
        evidence_chunk_ids=[cid],
        known_scan_chunk_ids={cid},
        require_evidence=True,
        current_file_content=html,
    )
    assert result.eligible_for_validated_pr is True
    assert any(c.name == "jsonld_syntax" and c.status == CheckStatus.PASSED for c in result.checks)


def test_skipped_jsonld_is_not_passed_when_absent():
    result = validate_patch_candidate(
        file_path="index.html",
        patch_text="diff",
        require_evidence=False,
        current_file_content="<html><body>no ld</body></html>",
    )
    skipped = next(c for c in result.checks if c.name == "jsonld_syntax")
    assert skipped.status == CheckStatus.SKIPPED


def test_verification_never_fixes_on_pr_alone():
    outcome, _ops, _ = evaluate_verification_outcome(
        original_issue_keywords=["hours", "monday"],
        patched_content=None,
        validation_passed=True,
        operational_error=None,
    )
    assert outcome == OUTCOME_INCONCLUSIVE

    outcome2, _, _ = evaluate_verification_outcome(
        original_issue_keywords=["hours", "monday"],
        patched_content="<html>open monday 9am hours</html>",
        validation_passed=True,
    )
    assert outcome2 == OUTCOME_FIXED

    outcome3, _, _ = evaluate_verification_outcome(
        original_issue_keywords=["hours", "monday"],
        patched_content="<html>unrelated</html>",
        validation_passed=True,
    )
    assert outcome3 == OUTCOME_UNRESOLVED
