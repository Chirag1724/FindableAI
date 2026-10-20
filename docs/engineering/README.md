# Engineering Documentation Index

Welcome to the FindableAI engineering documentation hub. This directory contains technical references, operational runbooks, architecture decision records, and local onboarding guides grounded directly in the active codebase.

---

## Directory Contents

| Document | Description |
| :--- | :--- |
| [LIMITATIONS_AND_READINESS.md](LIMITATIONS_AND_READINESS.md) | **Canonical** implementation status, execution modes, retrieval truth, persistence map, and release readiness (hackathon vs beta vs production). |
| [FRONTEND_INTEGRITY_CONTRACT.md](FRONTEND_INTEGRITY_CONTRACT.md) | API fields the scan UI must use for real vs synthetic/partial audits (P0 honesty). |
| [ENVIRONMENT.md](ENVIRONMENT.md) | **Canonical** environment-variable reference derived from `config.py` and `.env.example`. |
| [SYSTEM_FLOW.md](SYSTEM_FLOW.md) | End-to-end architecture flow and lifecycle from URL submission through scoring and optional GitHub PR (with incomplete stages labeled). |
| [API_REFERENCE.md](API_REFERENCE.md) | REST and SSE endpoints, schemas, authentication, rate limits, and execution-mode notes. |
| [AI_WEBSITE_HEALTH_BRIEF.md](AI_WEBSITE_HEALTH_BRIEF.md) | **Canonical** on-demand AI Summary / Website Health Brief (architecture, API, config, cache, ops). |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker/Compose, env matrix, and deployment guidance. Existence of Dockerfiles ≠ verified production deploy. |
| [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md) | Local onboarding for Python, Node, PostgreSQL/pgvector, dev servers, and smoke testing. |
| [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) | ADRs (F-Score, Git push strategy, framework patches, DAG, BudgetGuard). |
| [DURABLE_JOBS.md](DURABLE_JOBS.md) | Durable scan job queue, lease semantics, and worker lifecycle. |
| [TESTING.md](TESTING.md) | Test philosophy, suite catalogs, and commands. Do not treat listed counts as a live CI certificate unless re-run. |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common failure modes (Playwright, Alembic, Groq limits, GitHub PAT, AI Summary). |
| [REMEDIATION_LIFECYCLE.md](REMEDIATION_LIFECYCLE.md) | Evidence-grounded remediation path, trust boundaries, and lifecycle states. |
| [ROADMAP.md](ROADMAP.md) | Near-term engineering priorities; read alongside LIMITATIONS_AND_READINESS (ROADMAP "delivered" rows can lag code truth). |

---

## Cross-Reference to System Design Playbooks

For high-level foundational context and historical team task allocations, refer to the parent documentation suite:

- [01_ARCHITECTURE_AND_SYSTEM_DESIGN.md](../01_ARCHITECTURE_AND_SYSTEM_DESIGN.md): Foundational system architecture, component boundaries, and data flow.
- [02_TECH_STACK_AND_IMPLEMENTATION.md](../02_TECH_STACK_AND_IMPLEMENTATION.md): Deep-dive into dependencies, data models, and prompt structures.
- [03_EXECUTION_PLAYBOOK.md](../03_EXECUTION_PLAYBOOK.md): Phase-by-phase development protocols and test checklists.
- [04_TEAM_TASK_ALLOCATION.md](../04_TEAM_TASK_ALLOCATION.md): Historical task assignment matrix and role ownership.
- [05_AI_LIGHTHOUSE_FEATURE_SPEC.md](../05_AI_LIGHTHOUSE_FEATURE_SPEC.md): AI Lighthouse per-engine readiness, crawler governance, and audits.
