# Lumi Roadmap

This roadmap is the concrete path from Lumi's current grounded-agent foundation to a calmer, more reliable coding assistant that can compete on trust, edit quality, and workflow.

## Goal

Lumi should feel:

- repo-aware before it acts
- precise when it edits
- honest about risk
- resilient when checks fail
- visually consistent in the TUI
- measurable through benchmarks
- coherent across long-running tasks

## Current Baseline

Already in place:

- structured agent actions instead of free-form shell execution
- grouped preflight summaries and diff previews
- rollback and undo for filesystem actions
- repo-aware verification detection
- patch-oriented edit actions
- persisted little notes and starter-panel guidance
- task-memory persistence for prior runs

## Phase 1: Reliable Core

### 1. Repo-Aware Planning And Verification

Deliverables:

- detect frameworks, entrypoints, config files, package manager, and verification tools
- include that repo profile in planning context
- prefer `run_verify` over hardcoded check guesses

Acceptance criteria:

- planning context shows detected frameworks and key config files
- agent picks repo-native verification commands without user spelling them out
- broad tasks inspect repo shape before mutating files

### 2. Precise Patch/Edit Engine

Deliverables:

- multi-hunk patch application
- anchored context patching
- line-range patching with conflict detection
- structured JSON/YAML editors

Acceptance criteria:

- existing files are patched more often than fully rewritten
- ambiguous edits fail closed instead of guessing
- file diffs stay small for localized changes

### 3. Failure Recovery And Retry Logic

Deliverables:

- classify common failures
- request one bounded recovery plan
- retry the failed step after recovery

Acceptance criteria:

- common “fix test, rerun check” flows recover automatically once
- recovery stays bounded and visible in the transcript
- failure summaries include which checks failed

## Phase 2: Trust And Operator UX

### 4. Cleaner Approval And Diff UX

Deliverables:

- grouped plan summary before execution
- diff previews for file edits
- delete previews with counts
- review-only mode and rollback scope

Acceptance criteria:

- users can see reads, edits, deletes, and checks at a glance
- risky operations are previewed before execution
- failed runs can be rolled back with clear scope

### 5. TUI Consistency And Polish

Deliverables:

- unified starter/chat/approval visual system
- stable prompt placement
- cleaner transcript rendering
- useful but subtle `little notes`

Acceptance criteria:

- the UI no longer feels like separate stitched-together modes
- pending confirmations have their own obvious prompt state
- code blocks and transcript spacing are readable in long sessions

## Phase 3: Measurement And Continuity

### 6. Benchmark Suite

Deliverables:

- scenario set for scaffolding, file management, patching, and verification
- suite summary with pass rate, average score, recovery rate, and rollback rate
- benchmark scenarios checked into the repo

Acceptance criteria:

- Lumi can be scored against the same tasks across releases
- regressions are visible instead of anecdotal
- success is measured by both outcome and safety signals

### 7. Better Long-Running Task Memory

Deliverables:

- persist active objective
- persist touched files and failed checks while a run is active
- include active-task memory in planning context

Acceptance criteria:

- interrupted work can resume with useful context
- task memory is task-scoped, not just chat history
- recent failures are visible in future planning

## Stretch Work

These are the next steps once the seven core milestones above feel solid.

### 8. Smarter Repo Graph

- symbol graph for definitions/usages/tests
- likely target-file ranking by task
- better changed-file inspection

### 9. Safer File Operations

- richer move/copy/rename planning
- archive/delete flows with previews
- broader structured config editing

### 10. Benchmark-Gated Releases

- benchmark summary in CI
- release notes tied to benchmark movement
- regression thresholds before shipping

## Suggested Release Plan

### v0.4

- framework/config-aware repo profiling
- active task memory
- stronger benchmark helpers

### v0.5

- tighter retry and recovery heuristics
- better verification summaries
- benchmark scenarios expanded

### v0.6

- TUI approval/transcript unification
- better patch affordances and edit previews
- more polished long-session agent UX

## What “Claude Code Level” Means For Lumi

Lumi should:

- inspect the repo before editing
- choose the right files with less babysitting
- patch precisely instead of rewriting broadly
- run the right checks automatically
- recover once from common failures
- show exactly what it will change
- keep a calm, coherent UI
- remember active work across turns
