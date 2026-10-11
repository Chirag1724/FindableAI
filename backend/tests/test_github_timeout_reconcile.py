"""Ambiguous GitHub timeout must not create a second PR when one already exists."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.v1.scans import _reconcile_github_pr_after_timeout
from app.github.client import FakeGitHubClient
from app.github.pr_engine import build_feature_branch_name


@pytest.mark.asyncio
async def test_reconcile_finds_existing_open_pr():
    client = FakeGitHubClient(login="bot")
    client.seed_repo("acme/site", allow_push=True)
    source = client.get_repository("acme/site")
    branch = build_feature_branch_name("scan_abc")
    client.create_branch(source, branch, client.get_branch_sha(source, "main"))
    pull = client.create_pull(
        source,
        title="t",
        body="b",
        head=branch,
        base="main",
    )

    result = await _reconcile_github_pr_after_timeout(
        gh_client=client,
        source_repo="acme/site",
        target_branch="main",
        scan_id="scan_abc",
        scan_uuid=None,
        idem_key="key",
        formatted_patches=[SimpleNamespace(file_path="index.html")],
        all_validation_checks=[],
        base_sha="sha0",
    )
    assert result is not None
    assert result.pr_number == pull.number
    assert result.pr_url == pull.url
    # Reconcile must not open another PR.
    assert len(client._repos["acme/site"].pulls) == 1


@pytest.mark.asyncio
async def test_reconcile_miss_returns_none():
    client = FakeGitHubClient(login="bot")
    client.seed_repo("acme/site")
    result = await _reconcile_github_pr_after_timeout(
        gh_client=client,
        source_repo="acme/site",
        target_branch="main",
        scan_id="scan_missing",
        scan_uuid=None,
        idem_key="key",
        formatted_patches=[],
        all_validation_checks=[],
        base_sha=None,
    )
    assert result is None


@pytest.mark.asyncio
async def test_reconcile_null_client():
    assert (
        await _reconcile_github_pr_after_timeout(
            gh_client=None,
            source_repo="a/b",
            target_branch="main",
            scan_id="s",
            scan_uuid=None,
            idem_key="k",
            formatted_patches=[],
            all_validation_checks=[],
            base_sha=None,
        )
        is None
    )
