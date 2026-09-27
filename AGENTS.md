# Agent Instructions & Guidelines

## Ponytail: Minimalist & Senior Engineering Guidelines

> "He says nothing. He writes one line. It works."

When writing or refactoring code in this repository, always apply the **Ladder of Laziness**:

1. **Does this need to exist?** → No: Skip it (YAGNI).
2. **Already in this codebase?** → Reuse existing components, utilities, and helper functions.
3. **Standard library does it?** → Use standard library features.
4. **Native platform feature?** → Use HTML5 / CSS / browser built-ins.
5. **Installed dependency?** → Use existing dependencies before adding new ones.
6. **One line?** → Write one clean, readable line instead of multi-function wrappers.
7. **Only then:** → Write the minimum viable, safe, and maintainable implementation.

### Safety Invariants
- Never compromise input validation, security, database transactional integrity, or accessibility.
