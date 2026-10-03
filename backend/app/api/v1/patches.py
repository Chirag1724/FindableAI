import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.github.client import GitHubClientError, build_pygithub_client_from_token
from app.github.pr_engine import GitHubPRService, PREngineError
from app.schemas.github_pr import PREngineRequest
from app.schemas.patch import PullRequestResult
from app.schemas.patching import FormattedPatch, PatchFormatStatus, SchemaRemediationTarget

logger = logging.getLogger(__name__)

router = APIRouter()


class ApplyPatchRequest(BaseModel):
    patch_id: str
    github_repo_url: str
    target_branch: str = "main"


def _parse_github_repo_owner_name(url: str) -> str:
    cleaned = url.strip().rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    if "github.com/" in cleaned:
        cleaned = cleaned.split("github.com/")[-1]
    cleaned = cleaned.strip("/")
    parts = [p for p in cleaned.split("/") if p]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid GitHub repository URL format: '{url}'. Expected format: 'owner/repo' or 'https://github.com/owner/repo'"
        )
    return f"{parts[0]}/{parts[1]}"


@router.post("/apply-pr", response_model=PullRequestResult)
async def apply_patch_as_pr(request: ApplyPatchRequest):
    """Triggers autonomous GitHub Pull Request creation for a proposed patch."""
    if not request.github_repo_url or not request.github_repo_url.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No GitHub repository configured. Provide a valid repo URL to enable automated PR creation.",
        )

    try:
        source_repo = _parse_github_repo_owner_name(request.github_repo_url)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Required scopes for Personal Access Token (PAT):
    # - Classic PAT: 'repo' (or 'public_repo' for public repositories)
    # - Fine-Grained PAT: 'Pull requests' (Read & Write), 'Contents' (Read & Write), 'Metadata' (Read-only)
    token = settings.GITHUB_TOKEN.strip() if settings.GITHUB_TOKEN else ""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub integration token is not configured on server (GITHUB_TOKEN). Add a GitHub Personal Access Token (PAT with 'repo' scope) to environment variables to enable automated PR creation.",
        )

    patch = FormattedPatch(
        opportunity_id=request.patch_id,
        schema_type=SchemaRemediationTarget.LOCAL_BUSINESS,
        file_path="index.html",
        patch_text="",
        changed_lines=1,
        status=PatchFormatStatus.APPLIED,
        message="Direct patch remediation PR",
    )

    try:
        gh_client = build_pygithub_client_from_token(token)
        pr_service = GitHubPRService(gh_client)
        pr_request = PREngineRequest(
            source_repo=source_repo,
            target_branch=request.target_branch,
            scan_id=f"patch_{request.patch_id[:8]}",
            patches=[patch],
            commit_message=f"fix(discoverability): apply FindableAI remediation patch {request.patch_id}",
            pr_title=f"FindableAI: Machine Discoverability Remediation Patch ({request.patch_id})",
        )
        result = pr_service.create_remediation_pr(pr_request)
        return PullRequestResult(
            pr_url=result.pr_url,
            pr_number=result.pr_number,
            branch_name=result.generated_branch,
            title=f"FindableAI: Machine Discoverability Remediation Patch ({request.patch_id})",
            created_at=datetime.now(UTC),
        )
    except (PREngineError, GitHubClientError) as exc:
        logger.error("GitHub PR creation failed for patch %s: %s", request.patch_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub PR creation failed: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error during PR creation for patch %s", request.patch_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error creating GitHub PR: {exc}",
        ) from exc
