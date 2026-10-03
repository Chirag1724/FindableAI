"""Injectable GitHub client abstractions for P2-3.5.

Production adapter uses PyGithub; tests inject fakes. No tokens are logged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


class GitHubClientError(Exception):
    def __init__(self, message: str, *, reason: str | None = None) -> None:
        self.reason = reason or "github_client_error"
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class RepoRef:
    full_name: str
    default_branch: str
    owner_login: str


@dataclass(frozen=True, slots=True)
class FileContent:
    path: str
    content: str
    sha: str


@dataclass(frozen=True, slots=True)
class PullRef:
    number: int
    url: str
    head_ref: str
    base_ref: str
    title: str


class GitHubClient(Protocol):
    def get_authenticated_login(self) -> str: ...

    def get_repository(self, full_name: str) -> RepoRef: ...

    def has_push_access(self, repo: RepoRef) -> bool: ...

    def get_or_create_fork(self, source: RepoRef) -> RepoRef: ...

    def get_branch_sha(self, repo: RepoRef, branch: str) -> str: ...

    def branch_exists(self, repo: RepoRef, branch: str) -> bool: ...

    def create_branch(self, repo: RepoRef, branch: str, from_sha: str) -> None: ...

    def get_file(self, repo: RepoRef, path: str, *, ref: str) -> FileContent: ...

    def create_or_update_file(
        self,
        repo: RepoRef,
        *,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None,
    ) -> str: ...

    def find_open_pull(
        self,
        source: RepoRef,
        *,
        head_full: str,
        base: str,
    ) -> PullRef | None: ...

    def create_pull(
        self,
        source: RepoRef,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PullRef: ...


@dataclass
class FakeRepoState:
    default_branch: str = "main"
    branches: dict[str, str] = field(default_factory=dict)
    files: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)
    pulls: list[PullRef] = field(default_factory=list)
    fork_of: str | None = None
    allow_push: bool | None = None
    allow_fork: bool = True


class FakeGitHubClient:
    """In-memory GitHub client for unit/integration tests (no network)."""

    def __init__(
        self,
        *,
        login: str = "bot-user",
        repos: dict[str, FakeRepoState] | None = None,
    ) -> None:
        self._login = login
        self._repos: dict[str, FakeRepoState] = repos or {}
        self.calls: list[str] = []

    def seed_repo(
        self,
        full_name: str,
        *,
        default_branch: str = "main",
        files: dict[str, str] | None = None,
        fork_of: str | None = None,
        allow_push: bool | None = None,
        allow_fork: bool = True,
    ) -> None:
        sha = "base-sha-001"
        state = FakeRepoState(
            default_branch=default_branch,
            fork_of=fork_of,
            allow_push=allow_push,
            allow_fork=allow_fork,
        )
        state.branches[default_branch] = sha
        branch_files: dict[str, tuple[str, str]] = {}
        for path, content in (files or {}).items():
            branch_files[path] = (content, f"sha-{path}")
        state.files[default_branch] = branch_files
        self._repos[full_name] = state

    def get_authenticated_login(self) -> str:
        self.calls.append("get_authenticated_login")
        return self._login

    def get_repository(self, full_name: str) -> RepoRef:
        self.calls.append(f"get_repository:{full_name}")
        state = self._repos.get(full_name)
        if state is None:
            raise GitHubClientError(f"repository not found: {full_name}", reason="not_found")
        owner = full_name.split("/", 1)[0]
        return RepoRef(
            full_name=full_name,
            default_branch=state.default_branch,
            owner_login=owner,
        )

    def has_push_access(self, repo: RepoRef) -> bool:
        self.calls.append(f"has_push_access:{repo.full_name}")
        state = self._repos.get(repo.full_name)
        if state is not None and state.allow_push is not None:
            return state.allow_push
        # Fallback for API responses/tokens that omit permissions object: same-owner indicates direct push access
        return repo.owner_login.lower() == self._login.lower()

    def get_or_create_fork(self, source: RepoRef) -> RepoRef:
        self.calls.append(f"get_or_create_fork:{source.full_name}")
        source_state = self._repos.get(source.full_name)
        if source_state is not None and not source_state.allow_fork:
            raise GitHubClientError(
                "Forking is disabled for this repository",
                reason="forking_disabled",
            )
        fork_name = f"{self._login}/{source.full_name.split('/', 1)[1]}"
        existing = self._repos.get(fork_name)
        if existing is not None:
            if existing.fork_of and existing.fork_of != source.full_name:
                raise GitHubClientError(
                    "fork points at unexpected source repository",
                    reason="wrong_fork",
                )
            return self.get_repository(fork_name)
        if source_state is None:
            raise GitHubClientError(f"repository not found: {source.full_name}", reason="not_found")
        fork_state = FakeRepoState(
            default_branch=source_state.default_branch,
            fork_of=source.full_name,
        )
        tip = source_state.branches[source_state.default_branch]
        fork_state.branches[source_state.default_branch] = tip
        fork_state.files[source_state.default_branch] = dict(
            source_state.files.get(source_state.default_branch, {})
        )
        self._repos[fork_name] = fork_state
        return self.get_repository(fork_name)

    def get_branch_sha(self, repo: RepoRef, branch: str) -> str:
        self.calls.append(f"get_branch_sha:{repo.full_name}:{branch}")
        state = self._repos[repo.full_name]
        if branch not in state.branches:
            raise GitHubClientError(f"branch not found: {branch}", reason="branch_not_found")
        return state.branches[branch]

    def branch_exists(self, repo: RepoRef, branch: str) -> bool:
        return branch in self._repos[repo.full_name].branches

    def create_branch(self, repo: RepoRef, branch: str, from_sha: str) -> None:
        self.calls.append(f"create_branch:{repo.full_name}:{branch}")
        state = self._repos[repo.full_name]
        if branch in state.branches:
            raise GitHubClientError(f"branch already exists: {branch}", reason="branch_exists")
        state.branches[branch] = from_sha
        source_branch = state.default_branch
        for name, sha in state.branches.items():
            if sha == from_sha and name != branch:
                source_branch = name
                break
        state.files[branch] = dict(state.files.get(source_branch, {}))

    def get_file(self, repo: RepoRef, path: str, *, ref: str) -> FileContent:
        self.calls.append(f"get_file:{repo.full_name}:{path}@{ref}")
        state = self._repos[repo.full_name]
        files = state.files.get(ref, {})
        if path not in files:
            raise GitHubClientError(f"file not found: {path}", reason="file_not_found")
        content, sha = files[path]
        return FileContent(path=path, content=content, sha=sha)

    def create_or_update_file(
        self,
        repo: RepoRef,
        *,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None,
    ) -> str:
        del message
        self.calls.append(f"update_file:{repo.full_name}:{path}@{branch}")
        state = self._repos[repo.full_name]
        if branch not in state.branches:
            raise GitHubClientError(f"branch not found: {branch}", reason="branch_not_found")
        files = state.files.setdefault(branch, {})
        if path in files:
            _old, old_sha = files[path]
            if sha is None or sha != old_sha:
                raise GitHubClientError(
                    "file update conflict (stale SHA)",
                    reason="file_conflict",
                )
        elif sha is not None:
            raise GitHubClientError(
                "file update conflict (unexpected SHA for create)",
                reason="file_conflict",
            )
        new_sha = f"sha-{path}-{len(content)}"
        files[path] = (content, new_sha)
        state.branches[branch] = f"commit-{branch}-{new_sha}"
        return state.branches[branch]

    def find_open_pull(
        self,
        source: RepoRef,
        *,
        head_full: str,
        base: str,
    ) -> PullRef | None:
        self.calls.append(f"find_open_pull:{source.full_name}:{head_full}->{base}")
        state = self._repos[source.full_name]
        for pull in state.pulls:
            if pull.head_ref == head_full and pull.base_ref == base:
                return pull
        return None

    def create_pull(
        self,
        source: RepoRef,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PullRef:
        del body
        self.calls.append(f"create_pull:{source.full_name}:{head}->{base}")
        state = self._repos[source.full_name]
        number = len(state.pulls) + 1
        pull = PullRef(
            number=number,
            url=f"https://github.com/{source.full_name}/pull/{number}",
            head_ref=head,
            base_ref=base,
            title=title,
        )
        state.pulls.append(pull)
        return pull


class PyGithubClient:
    """Thin PyGithub adapter. Constructed at the app boundary with a token."""

    def __init__(self, github: object, *, fork_ready_attempts: int = 5) -> None:
        self._github = github
        self._fork_ready_attempts = max(1, fork_ready_attempts)

    def get_authenticated_login(self) -> str:
        try:
            user = self._github.get_user()  # type: ignore[attr-defined]
            return str(user.login)
        except Exception as exc:
            raise GitHubClientError(
                f"GitHub authentication failure (invalid or expired token): {exc}",
                reason="auth_failure",
            ) from exc

    def get_repository(self, full_name: str) -> RepoRef:
        try:
            repo = self._github.get_repo(full_name)  # type: ignore[attr-defined]
        except Exception as exc:
            raise GitHubClientError(
                f"repository not found: {full_name}",
                reason="not_found",
            ) from exc
        return RepoRef(
            full_name=repo.full_name,
            default_branch=repo.default_branch,
            owner_login=repo.owner.login,
        )

    def has_push_access(self, repo: RepoRef) -> bool:
        try:
            gh_repo = self._github.get_repo(repo.full_name)  # type: ignore[attr-defined]
            perms = getattr(gh_repo, "permissions", None)
            if perms and (getattr(perms, "push", False) or getattr(perms, "admin", False)):
                return True
            login = self.get_authenticated_login()
            # Fallback for API responses/tokens that omit permissions object: same-owner indicates direct push access
            return repo.owner_login.lower() == login.lower()
        except Exception:
            return False

    def get_or_create_fork(self, source: RepoRef) -> RepoRef:
        login = self.get_authenticated_login()
        fork_name = f"{login}/{source.full_name.split('/', 1)[1]}"
        try:
            fork = self._github.get_repo(fork_name)  # type: ignore[attr-defined]
            parent = getattr(fork, "parent", None)
            if parent is not None and parent.full_name != source.full_name:
                raise GitHubClientError(
                    "existing fork does not match source repository",
                    reason="wrong_fork",
                )
            return RepoRef(
                full_name=fork.full_name,
                default_branch=fork.default_branch,
                owner_login=fork.owner.login,
            )
        except GitHubClientError:
            raise
        except Exception:
            try:
                source_repo = self._github.get_repo(source.full_name)  # type: ignore[attr-defined]
                fork = source_repo.create_fork()
            except Exception as exc:
                raise GitHubClientError(
                    f"failed to create repository fork (forking may be disabled or token lacks permission): {exc}",
                    reason="forking_disabled",
                ) from exc
            for _ in range(self._fork_ready_attempts):
                try:
                    ready = self._github.get_repo(fork.full_name)  # type: ignore[attr-defined]
                    _ = ready.get_branch(ready.default_branch)
                    return RepoRef(
                        full_name=ready.full_name,
                        default_branch=ready.default_branch,
                        owner_login=ready.owner.login,
                    )
                except Exception:
                    time.sleep(0.5)
            raise GitHubClientError(
                "fork created but not ready within retry budget",
                reason="fork_not_ready",
            ) from None

    def get_branch_sha(self, repo: RepoRef, branch: str) -> str:
        gh_repo = self._github.get_repo(repo.full_name)  # type: ignore[attr-defined]
        ref = gh_repo.get_branch(branch)
        return str(ref.commit.sha)

    def branch_exists(self, repo: RepoRef, branch: str) -> bool:
        gh_repo = self._github.get_repo(repo.full_name)  # type: ignore[attr-defined]
        try:
            gh_repo.get_branch(branch)
            return True
        except Exception:
            return False

    def create_branch(self, repo: RepoRef, branch: str, from_sha: str) -> None:
        gh_repo = self._github.get_repo(repo.full_name)  # type: ignore[attr-defined]
        if self.branch_exists(repo, branch):
            raise GitHubClientError(f"branch already exists: {branch}", reason="branch_exists")
        gh_repo.create_git_ref(ref=f"refs/heads/{branch}", sha=from_sha)

    def get_file(self, repo: RepoRef, path: str, *, ref: str) -> FileContent:
        gh_repo = self._github.get_repo(repo.full_name)  # type: ignore[attr-defined]
        try:
            content_file = gh_repo.get_contents(path, ref=ref)
        except Exception as exc:
            raise GitHubClientError(f"file not found: {path}", reason="file_not_found") from exc
        if isinstance(content_file, list):
            raise GitHubClientError(f"path is a directory: {path}", reason="is_directory")
        raw = content_file.decoded_content
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        return FileContent(path=path, content=text, sha=str(content_file.sha))

    def create_or_update_file(
        self,
        repo: RepoRef,
        *,
        path: str,
        content: str,
        message: str,
        branch: str,
        sha: str | None,
    ) -> str:
        gh_repo = self._github.get_repo(repo.full_name)  # type: ignore[attr-defined]
        try:
            if sha is None:
                result = gh_repo.create_file(path, message, content, branch=branch)
            else:
                result = gh_repo.update_file(path, message, content, sha, branch=branch)
        except Exception as exc:
            raise GitHubClientError(
                "file update failed",
                reason="file_update_failed",
            ) from exc
        commit = result.get("commit")
        return str(getattr(commit, "sha", "") or "")

    def find_open_pull(
        self,
        source: RepoRef,
        *,
        head_full: str,
        base: str,
    ) -> PullRef | None:
        gh_repo = self._github.get_repo(source.full_name)  # type: ignore[attr-defined]
        pulls = gh_repo.get_pulls(state="open", base=base)
        for pull in pulls:
            label = f"{pull.head.repo.owner.login}:{pull.head.ref}"
            if pull.head.label == head_full or label == head_full:
                return PullRef(
                    number=int(pull.number),
                    url=str(pull.html_url),
                    head_ref=head_full,
                    base_ref=base,
                    title=str(pull.title),
                )
        return None

    def create_pull(
        self,
        source: RepoRef,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> PullRef:
        gh_repo = self._github.get_repo(source.full_name)  # type: ignore[attr-defined]
        try:
            pull = gh_repo.create_pull(title=title, body=body, head=head, base=base)
        except Exception as exc:
            raise GitHubClientError("PR creation failed", reason="pr_create_failed") from exc
        return PullRef(
            number=int(pull.number),
            url=str(pull.html_url),
            head_ref=head,
            base_ref=base,
            title=str(pull.title),
        )


def build_pygithub_client_from_token(token: str) -> PyGithubClient:
    """Application-boundary helper. Never log the token."""
    if not token or not token.strip():
        raise GitHubClientError("GitHub token is required", reason="auth_failure")
    import github
    from github import Github

    if hasattr(github, "Auth") and hasattr(github.Auth, "Token"):
        return PyGithubClient(Github(auth=github.Auth.Token(token.strip())))
    return PyGithubClient(Github(token.strip()))
