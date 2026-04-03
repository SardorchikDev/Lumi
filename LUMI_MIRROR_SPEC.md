# Lumi v0.7.0: Operator

Operator is the Python-side Claude-parity release.

It is not the language rewrite. It is the release that closes the highest-value workflow gaps first, makes parity measurable, and prepares Lumi for the Bun/TypeScript/Ink rewrite that will become `v1.0.0: Native`.

The file name stays `LUMI_MIRROR_SPEC.md` to avoid churn in existing references, but the current release name is `Operator`.

## Release Naming

- `v0.7.0: Operator`
  - Python release
  - focused on workflow parity, command parity, and subsystem parity
  - goal: make Lumi feel close enough to Claude Code that the remaining rewrite is mostly architectural, not product-definition work
- `v1.0.0: Native`
  - Bun/TypeScript/Ink rewrite
  - goal: move Lumi onto the same kind of runtime shape Claude Code uses for the deepest parity layers: bridge, richer tasking, denser TUI control, and plugin lifecycle symmetry

## Success Criteria

Operator is successful when:

- Lumi covers the high-value Claude command surface used in daily coding work
- permissions are rule-based instead of ad hoc
- tasks and agents are first-class execution units
- repo navigation becomes semantic, not only grep-based
- git workflows are operator-grade, not prompt hacks
- parity is tracked by audit, not anecdotes
- the later rewrite can preserve behavior instead of redefining it

## The 17 Workstreams

### 1. Wildcard Tool Permission Engine

Deliverables:

- rule grammar like `Bash(git *)`, `FileEdit(src/**)`, `FileRead(*)`
- permission modes: `default`, `plan`, `bypass`, `auto`
- persisted approval rules with audit logs
- batch approval for full plans
- terminal and future IDE permission prompts

Acceptance:

- risky operations are explainable before execution
- repeated trusted operations stop prompting every time
- approvals can be inspected and revoked cleanly

### 2. Explicit Tool Registry

Deliverables:

- typed tool registry with schemas and capability metadata
- read-only vs destructive flags
- concurrency-safety declarations
- command-to-tool routing instead of mixed UI/runtime logic

Acceptance:

- tools become the main execution unit
- permissions attach to tools, not random command branches
- tasks and agents can reuse the same tool contracts

### 3. Git Workflow Suite

Deliverables:

- `/commit`
- `/commit-push-pr`
- `/branch`
- `/pr_comments`
- `/rewind`
- stronger `/diff`

Acceptance:

- Lumi can complete normal git loops without shell babysitting
- PR feedback can be addressed from inside Lumi
- rollback is safe and visible

### 4. Code Quality Command Suite

Deliverables:

- `/security-review`
- `/advisor`
- `/bughunter`
- stronger multi-pass `/review`
- read-only review tool presets

Acceptance:

- review output is specific, ranked, and actionable
- architecture and security questions stop piggybacking on generic chat prompts

### 5. Session And Context Parity

Deliverables:

- `/summary`
- `/share` replacement surface
- stronger `/session`
- rename/tag/delete flows
- better `/compact`
- session metadata: files, commands, model, TL;DR

Acceptance:

- users can resume and inspect prior sessions with real structure
- long chats degrade gracefully instead of becoming noise

### 6. Background Task Engine

Deliverables:

- persistent task model: queued, running, blocked, done, failed, canceled
- output capture and retrieval
- stop/retry support
- separate shell, verification, and agent task types

Acceptance:

- `/tasks` stops being a thin report and becomes a real execution surface
- background work survives across operator attention shifts

### 7. Sub-Agent Orchestration

Deliverables:

- spawned worker agents with scoped context
- plan mode and execution mode
- message passing and merge-back
- teammate/parallel agent support

Acceptance:

- complex work can be decomposed instead of overloading one loop
- users can inspect what each agent is doing

### 8. LSP Repo Intelligence

Deliverables:

- go-to-definition
- find references
- symbol search
- rename preview
- call graph and impact views

Acceptance:

- Lumi can answer “where is this used?” with more than grep
- multi-file refactors become safer

### 9. IDE Bridge

Deliverables:

- bridge transport layer
- session runner and message protocol
- permission proxy
- diff and file-open handoff
- VS Code and JetBrains path

Acceptance:

- Lumi can act as a backend, not only a standalone terminal app

### 10. Full Settings Layer

Deliverables:

- `/privacy-settings`
- `/output-style`
- `/color`
- `/keybindings`
- `/vim`
- `/statusline`
- `/env`
- `/sandbox-toggle`
- stronger `/config`

Acceptance:

- runtime behavior is operator-controlled instead of hardcoded defaults

### 11. Usage And Telemetry Surfaces

Deliverables:

- `/stats`
- `/usage`
- `/extra-usage`
- `/rate-limit-options`
- clearer session and task accounting

Acceptance:

- users can understand cost, context, and usage drift during long sessions

### 12. Install, Init, And Upgrade Flows

Deliverables:

- `/init`
- `/init-verifiers`
- `/upgrade`
- `/release-notes`
- `/onboarding`
- `/terminalSetup`

Acceptance:

- new projects bootstrap faster
- verification hooks are standardized
- self-upgrade is visible and maintainable

### 13. Plugin And Skill Lifecycle Parity

Deliverables:

- plugin install/update/remove flow
- bundled high-value skills
- safer hook boundaries
- stronger marketplace metadata and trust review

Acceptance:

- plugins feel like managed runtime extensions, not loose files

### 14. Remote And Device Handoff Layer

Deliverables:

- `/remote-env`
- `/remote-setup`
- replacements for `/desktop`, `/mobile`, `/teleport`
- session handoff contracts

Acceptance:

- users can move work between environments cleanly
- non-local workflows are not terminal-only dead ends

### 15. TUI Control-Density Parity

Deliverables:

- richer statusline
- configurable keybindings
- vim mode
- denser panes for tasks, agents, permissions, diffs, and context
- more coherent prompt/status layout

Acceptance:

- Lumi feels like an operator console, not a chat app wearing ANSI

### 16. Missing Command Parity Backlog

High-value commands to close during Operator:

- `/commit`
- `/commit-push-pr`
- `/branch`
- `/pr_comments`
- `/rewind`
- `/security-review`
- `/advisor`
- `/bughunter`
- `/summary`
- `/plan`
- `/ultraplan`
- `/stats`
- `/usage`
- `/privacy-settings`
- `/init`
- `/upgrade`
- `/keybindings`
- `/vim`
- `/statusline`
- `/bridge`
- `/ide`

Lower-priority or infra-bound commands:

- `/share`
- `/login`
- `/logout`
- `/oauth-refresh`
- `/desktop`
- `/mobile`
- `/teleport`
- `/remote-env`
- `/remote-setup`
- `/thinkback`
- `/thinkback-play`

### 17. Parity And Regression Audit

Deliverables:

- exact command parity audit
- subsystem parity matrix
- workflow parity scorecard
- machine-readable JSON output
- optional CI enforcement later

Acceptance:

- every parity claim can be checked in a script
- regressions become visible immediately

## Execution Order

### Phase 1: Control Plane

- 1. permission engine
- 2. tool registry
- 3. git workflow suite
- 4. code quality suite

### Phase 2: Runtime Core

- 5. session/context parity
- 6. background task engine
- 7. sub-agent orchestration
- 8. LSP repo intelligence

### Phase 3: Operator Surfaces

- 9. IDE bridge
- 10. full settings layer
- 11. usage/telemetry surfaces
- 12. install/init/upgrade flows
- 13. plugin and skill lifecycle parity
- 14. remote and device handoff
- 15. TUI control-density parity

### Phase 4: Audit And Rewrite Gate

- 16. missing command parity cleanup
- 17. parity/regression audit
- freeze behavior
- then rewrite to `v1.0.0: Native`

## Rewrite Gate For v1.0.0: Native

The language switch should happen only after Operator establishes:

- stable tool contracts
- stable permission contracts
- stable task/agent contracts
- stable command definitions
- stable settings schema
- stable parity audit criteria

If those are not locked first, the rewrite becomes a moving target and wastes time.

## Current Repo Entry Points

- CLI: `main.py`
- TUI: `src/tui/app.py`
- workbench/runtime: `src/utils/workbench.py`
- parity helpers: `src/utils/claude_parity.py`
- roadmap: `ROADMAP.md`
- audit command: `scripts/claude_parity_audit.py`

## Operating Rule

Operator is not allowed to claim Claude parity based on look-and-feel alone. It must close workflow, command, and subsystem gaps in measurable terms before the rewrite begins.
