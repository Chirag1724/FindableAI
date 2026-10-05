# Security Policy

FindableAI treats security as a core architectural invariant. Because our platform combines headless browser automation, multi-tenant LLM inference, untrusted web ingestion, and automated code-patch generation (GitHub PRs), we enforce a defense-in-depth model across every pipeline boundary.

## 1. Supported Versions

Security updates and patches are actively maintained for the following versions:

| Version | Supported          | Security Maintenance Level |
| :---    | :---               | :---                       |
| `main`  | :white_check_mark: | Active development & critical hotfixes |
| `< 1.0` | :white_check_mark: | Latest release tag only    |

## 2. Threat Model & Defense-in-Depth Posture

FindableAI handles high-leverage integrations. Vulnerability disclosures should reference our critical boundary defenses:

### 2.1 Server-Side Request Forgery (SSRF) & Crawler Isolation
* **Boundary:** Playwright headless browser & crawler workers.
* **Invariant:** Crawler sessions must never hit internal network ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), `localhost` / `127.0.0.1`, link-local addresses, or cloud metadata endpoints (`169.254.169.254`).
* **Reporting Trigger:** Any technique bypassing domain/IP resolution checks or egress network policies to access loopback or intranet services.

### 2.2 Indirect Prompt Injection & Untrusted Ingestion
* **Boundary:** DOM chunk extraction, synthetic intent generation, and NLI verification engines.
* **Invariant:** Raw web content crawled from target domains is untrusted. Extracted text chunks passed into LLMs (`FactExtractor`, NLI entailment classifiers, evaluator judges) must not execute system instructions, override prompt delimiters, or compromise orchestrator control flow.
* **Reporting Trigger:** Direct demonstration of adversarial payload extraction causing data exfiltration, unauthorized API operations, or privilege escalation.

### 2.3 Downstream Supply Chain & GitHub App Permissions
* **Boundary:** Autonomous pull request and patch generation engine.
* **Invariant:** GitHub tokens must adhere strictly to the principle of least privilege (`contents: write`, `pull_requests: write` scoped solely to the target repository). Patches must never inject untrusted binary blobs or arbitrary external scripts without AST validation.
* **Reporting Trigger:** Token leak vectors, cross-repository authorization bypasses, or patch tampering vulnerabilities.

### 2.4 Credential & Secret Management
* **Boundary:** LLM provider keys (OpenAI, Anthropic, Gemini, Groq) and database connection strings.
* **Invariant:** No secret may be logged in trace telemetry, exposed via frontend client bundles, or persisted unencrypted in database tables.

## 3. Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues, discussions, or pull requests.**

### Preferred Channel: GitHub Security Advisories
1. Navigate to the repository's **Security** tab.
2. Select **Advisories** and click **Report a vulnerability**.
3. Include detailed steps to reproduce the issue.

### Alternative Channel: Security Contact
If you cannot use GitHub Security Advisories, send an encrypted report to:
* **Email:** `security@findable.ai`
* **Subject:** `[Vulnerability Report] FindableAI - <Brief Title>`

### Required Report Contents
To expedite triage, include:
* **Description:** Impact and root cause summary.
* **Component Affected:** Target engine, API endpoint, or crawler module (e.g., `backend/app/engines/...`).
* **Reproduction Steps:** Minimal, deterministic Proof-of-Concept (PoC) payload, script, or cURL command.
* **Mitigation Recommendation:** Suggested architectural or code-level fix (if available).

## 4. Response & Remediation SLA

Our security engineering team commits to the following timelines for validated vulnerabilities:

* **Initial Acknowledgement:** Within **24–48 hours** of report receipt.
* **Triage & Severity Assessment:** Within **72 hours** (CVSS v3.1 scoring).
* **Remediation & Patch Deployment:**
  * **Critical (CVSS 9.0–10.0):** Hotfix release within **7 business days**.
  * **High (CVSS 7.0–8.9):** Fix within **14 business days**.
  * **Medium / Low (CVSS < 7.0):** Scheduled in the subsequent minor release cycle.
* **Coordinated Disclosure:** We request a **90-day embargo** period prior to public disclosure, unless mutually agreed otherwise.

## 5. Scope & Rules of Engagement

### In Scope
* `backend/` FastAPI application, routing, and middleware.
* Crawler networking isolation and SSRF filters.
* Engine-level validation (data ingestion, fact extraction, code-patch sanitization).
* Authentication, authorization, and tenant isolation logic.
* Secrets exposure or unintended credential leakage.

### Out of Scope
* General non-deterministic LLM hallucination (unless directly weaponized for arbitrary code execution, privilege escalation, or unauthorized data exfiltration).
* Volumetric Denial of Service (DoS/DDoS) against public staging or demo instances.
* Social engineering attacks against maintainers or contributors.
* Issues in third-party hosted services (e.g., Cloudflare, upstream LLM provider outages) outside our implementation control.

## 6. Safe Harbor

We consider security research conducted under this policy to be:
* **Authorized** in terms of computer crime statutes (e.g., CFAA).
* **Protected** from legal action by FindableAI maintainers, provided you act in good faith, avoid privacy violations, destroy any discovered confidential data immediately, and give us reasonable time to remediate before public disclosure.
