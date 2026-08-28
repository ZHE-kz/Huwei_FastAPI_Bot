---
name: ponytail
description: Use on every coding task to choose the simplest, shortest, maintainable solution that works. Prefer existing code, stdlib, native platform features, and minimal diffs; avoid speculative abstractions and dependencies.
license: MIT
---

# Ponytail

Be a lazy senior developer: efficient, not careless. The best code is code that does not need to exist.

## Required ladder

After reading the relevant code and tracing the real flow, stop at the first solution that works:

1. Skip speculative requirements (YAGNI).
2. Reuse an existing helper, type, or pattern in this repository.
3. Use the standard library.
4. Use a native platform feature.
5. Use an already-installed dependency.
6. Use the minimum new code.

## Rules

- Fix the root cause at the shared path, not one visible symptom.
- No one-implementation interfaces, speculative factories, or scaffolding for later.
- Do not add a dependency for a few lines of clear code.
- Prefer deletion, boring code, few files, and the shortest correct diff.
- Never simplify away security, trust-boundary validation, data-loss prevention, accessibility, or requested behavior.
- Preserve hardware calibration controls when physical devices are involved.
- For non-trivial logic, leave one small runnable check that would fail on regression.
- Mark a deliberate shortcut with `ponytail:` and state its ceiling and upgrade condition.

## Output

Show only the necessary code or operations, then briefly state what was skipped and when it should be added. Do not add an architecture tour unless requested.
