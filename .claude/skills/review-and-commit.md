---
name: review-and-commit
description: Self-validate, run Codex/Gemini review gates, and commit on pass. One-stop quality gate.
---

# /review-and-commit — Validate, Review, Commit

A one-stop workflow that self-checks, submits to external reviewers, and commits only when everything passes.

## Workflow

### Step 1: Self-Validation

Run these checks BEFORE touching external reviewers:

**If tasks.md was modified:**
- [ ] All task IDs use `[TASK-XX]` bracket format
- [ ] Every task has an explicit file path
- [ ] Every spec requirement has at least one task covering it
- [ ] No duplicate or overlapping tasks

**If code was modified:**
- [ ] All new functions have corresponding tests
- [ ] Run relevant module tests: all pass
- [ ] No hardcoded secrets, credentials, or absolute paths
- [ ] Imports are correct, no circular dependencies

**If specs/design docs were modified:**
- [ ] All referenced file paths exist or marked "to be created"
- [ ] No contradictions between sections
- [ ] Tech choices match the project tech stack

Fix any issues found. Do not proceed until self-check passes.

### Step 2: Full Test Suite

```bash
cd backend && python -m pytest tests/ -x -q -m 'not timescaledb'
```

If any test fails, fix it and re-run. Do not proceed to review with failing tests.

### Step 3: External Review

Run both reviewers in parallel:

1. **Codex**: `codex review "Review the changes for correctness, test coverage, and compliance with project specs"`
2. **Gemini**: `gemini -p "Review the changes for scope creep, over-engineering, and architectural issues"`

**Evaluation:**
- Both PASS → proceed to commit
- Either FAIL → fix issues, re-run self-validation, then re-submit
- Disagreement → prefer the conservative outcome
- Max 3 review rounds — escalate to human if still failing

### Step 4: Commit

- Create a feature branch if not already on one (never commit to master/main)
- Stage only relevant files (no `.env`, credentials, or generated files)
- Write a concise commit message describing the "why"
- Run `git commit` (let pre-commit hooks run — do NOT use `--no-verify`)

### Output

Report:
- Self-check results (pass/fail per item)
- Test suite results (total tests, passed, failed)
- Reviewer verdicts (Codex: PASS/FAIL, Gemini: PASS/FAIL)
- Commit SHA and branch name
