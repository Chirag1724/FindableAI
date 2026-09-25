"""GitHub PR automation package (P2-3.5 / P2-3.6)."""

from app.github.client import FakeGitHubClient, GitHubClientError, PyGithubClient
from app.github.pr_engine import (
    GitHubPRService,
    PREngineError,
    build_feature_branch_name,
    normalize_repo_path,
)
from app.github.pr_markdown import PRMarkdownError, generate_pr_markdown

__all__ = [
    "FakeGitHubClient",
    "GitHubClientError",
    "GitHubPRService",
    "PREngineError",
    "PRMarkdownError",
    "PyGithubClient",
    "build_feature_branch_name",
    "generate_pr_markdown",
    "normalize_repo_path",
]
