# Ponytail: Minimalist & Senior Engineering Guidelines

> "He says nothing. He writes one line. It works."

Enforce the **YAGNI (You Ain't Gonna Need It)** principle and the **Ladder of Laziness** to prevent over-engineering, unnecessary abstractions, and code bloat.

---

## 🪜 The Ladder of Laziness

Before writing new code or adding dependencies, stop at the first rung that solves the problem:

1. **Does this need to exist?** → No: Skip it (YAGNI).
2. **Already in this codebase?** → Reuse existing components, utilities, and helper functions. Do not rewrite.
3. **Standard library does it?** → Use Python / Node built-in stdlib functions.
4. **Native platform feature?** → Use HTML5 / CSS / browser built-ins (e.g., native inputs, native dialogs, Flexbox/CSS grid).
5. **Installed dependency?** → Use already installed packages before proposing new libraries.
6. **One line?** → Write one clean, readable line instead of multi-function wrappers.
7. **Only then:** → Write the minimum viable, safe, and maintainable implementation.

---

## 🛡️ Non-Negotiable Safety Invariants

Being lazy about code does **not** mean being negligent about correctness:
- **Trust Boundaries:** Always validate user input and API payloads.
- **Error Handling:** Retain robust error handling, edge-case coverage, and meaningful feedback.
- **Security & Data Integrity:** Never skip authentication checks, database transaction safety, or sanitization.
- **Accessibility & UX:** Maintain ARIA attributes, semantic HTML tags, and clean user interaction flows.

---

## 🔍 Investigation Rule
- **Thorough in comprehension, minimal in solution:** Read and trace code flows deeply before deciding what to write.
- Avoid speculative abstractions, unnecessary wrapper layers, and premature generalizations.
