# Agent Guidelines — FindableAI

## 1. Core Principles
- **Minimalist & Pragmatic (YAGNI):** Implement the simplest solution that directly solves the problem. Avoid speculative abstractions, wrapper bloat, and premature optimizations.
- **Reuse first:** Check the codebase and standard libraries for existing components, utilities, and dependencies before creating new ones.
- **Surgical changes:** Keep diffs focused on the task at hand. Do not rewrite functioning adjacent code or reformat unrelated files.

## 2. Domain & Safety Invariants
- **Canonical F-Score:** \(F = 0.40 S_{ans} + 0.30 S_{con} + 0.20 S_{str} + 0.10 S_{acc}\) with sub-scores already scaled 0–100 (see ADR-001).
- **Documentation truthfulness:** Prefer [docs/engineering/LIMITATIONS_AND_READINESS.md](docs/engineering/LIMITATIONS_AND_READINESS.md) over marketing claims when describing runtime behavior.
- **Non-negotiable safety:** Never compromise input validation, security boundaries, database transaction integrity, or accessibility (ARIA, semantic HTML).

## 3. Tech Stack Reference
- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, Vitest.
- **Backend:** FastAPI, Python 3.11+, SQLAlchemy, PostgreSQL, Pytest.
