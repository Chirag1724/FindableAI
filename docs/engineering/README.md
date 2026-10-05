# Engineering Documentation Index

Welcome to the FindableAI engineering documentation hub. This directory contains technical references, operational runbooks, architecture decision records, and local onboarding guides grounded directly in the active codebase.

---

## Directory Contents

| Document | Description |
| :--- | :--- |
| [SYSTEM_FLOW.md](SYSTEM_FLOW.md) | Comprehensive end-to-end architecture flow, Mermaid sequence diagram, and step-by-step lifecycle from URL submission to GitHub PR. |
| [API_REFERENCE.md](API_REFERENCE.md) | Technical reference for all REST and Server-Sent Events (SSE) endpoints, schemas, authentication, rate limits, and status codes. |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Production infrastructure architecture, multi-stage Docker containers, environment variable matrix, Playwright dependencies, and security headers. |
| [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) | Step-by-step onboarding guide for configuring Python 3.11+, Node 20+, PostgreSQL/pgvector, Redis, and local development servers. |
| [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) | Formal Architecture Decision Records (ADRs) detailing the F-Score formula, Git push strategies, framework route fallbacks, and DAG state orchestration. |
| [TESTING.md](TESTING.md) | Test philosophy, coverage metrics, test suite breakdowns (pytest and Vitest), mock fixtures, and execution commands. |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Root-cause analysis and verified fixes for Playwright headless binaries, lxml parsing, Alembic imports, GitHub PAT scopes, and Groq rate limits. |
| [ROADMAP.md](ROADMAP.md) | Current implementation audit against the Phase 5-8 release gate, highlighting delivered components and forward-looking scalability initiatives. |

---

## Cross-Reference to System Design Playbooks

For high-level foundational context and historical team task allocations, refer to the parent documentation suite:

- [01_ARCHITECTURE_AND_SYSTEM_DESIGN.md](../01_ARCHITECTURE_AND_SYSTEM_DESIGN.md): Foundational system architecture, component boundaries, and data flow.
- [02_TECH_STACK_AND_IMPLEMENTATION.md](../02_TECH_STACK_AND_IMPLEMENTATION.md): Deep-dive into dependencies, data models, and prompt structures.
- [03_EXECUTION_PLAYBOOK.md](../03_EXECUTION_PLAYBOOK.md): Phase-by-phase development protocols and test checklists.
- [04_TEAM_TASK_ALLOCATION.md](../04_TEAM_TASK_ALLOCATION.md): Historical task assignment matrix and role ownership.
