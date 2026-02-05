---
name: tdd
description: Strict red-green-refactor cycle for a single task or feature. Write the failing test first, always.
---

# /tdd — Single Task TDD

Implement exactly one task or feature using strict test-driven development. No shortcuts.

## Input

The user will provide one of:
- A task description or ID (e.g., "TASK-05" or "add position sizing to risk manager")
- A file path to modify
- A bug to fix

## The Loop

```
RED    → Write a failing test that defines the expected behavior
       → Run it, confirm it FAILS (if it passes, your test is wrong)

GREEN  → Write the MINIMUM code to make the test pass
       → Run it, confirm it PASSES
       → Run the full module suite, confirm no regressions

REFACTOR → Clean up only if needed (remove duplication, improve naming)
         → Run tests again, confirm still passing
```

## Rules

1. **Test first, always.** Never write implementation before the test.
2. **Minimal implementation.** Don't write more code than the test demands.
3. **Run tests after every change.** Hooks handle this for Edit/Write, but verify manually for complex changes.
4. **One behavior per test.** Each test should verify exactly one thing.
5. **Fix failures immediately.** If a test breaks, stop and fix before continuing.

## Test Location Convention

| Source file | Test file |
|------------|-----------|
| `backend/src/{module}/foo.py` | `backend/tests/{module}/test_foo.py` |
| `agents/{name}.py` | `agents/tests/test_{name}.py` |

## Output

When done, report:
- What was implemented (1 sentence)
- Test file path and test count
- All tests passing (yes/no + count)
