---
name: implement
description: Fast implementation from tasks.md using TDD. Skips lengthy preparation — starts coding within 2 messages.
---

# /implement — Fast Task Implementation

You are executing tasks from a tasks.md file using strict TDD. Speed is critical — minimize preparation, maximize code output.

## Input

The user will provide one of:
- A path to a tasks.md file
- A task range (e.g., "TASK-01 to TASK-10")
- "continue" to resume from the first incomplete task

## Workflow

### 1. Read tasks (1 message max)
- Read the specified tasks.md
- Identify the first incomplete task (or specified range)
- Do NOT create a TodoWrite list — tasks.md IS the tracker

### 2. For each task, strict TDD loop:
```
a) Read the task spec
b) Write the FAILING test first
c) Run pytest for the relevant module — confirm it fails
d) Write minimal implementation to pass
e) Run pytest again — confirm all pass
f) If any test fails: fix immediately, do not continue
g) Mark task complete in tasks.md with a checkbox: [x]
```

### 3. After every 5 tasks:
- Run the full module test suite to catch regressions
- Report progress: "Completed TASK-XX through TASK-YY. N tests passing."

### 4. Before finishing:
- Run full test suite: `cd backend && python -m pytest tests/ -x -q -m 'not timescaledb'`
- Report final summary: tasks completed, tests passing, any remaining tasks

## Rules

- Do NOT spend more than 2 messages on context gathering
- Do NOT recreate the task list with TodoWrite
- Start coding by message 2 at the latest
- One task at a time — never batch implementations before testing
- Use Task subagents to parallelize independent tasks when possible
