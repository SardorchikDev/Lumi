# Lumi v0.5.0: Forge

## Release Name

**Forge**

## Goal

Move Lumi from a terminal chat assistant into a terminal coding workbench.

## Shipped Pillars

### 1. Workbench Commands

- `/build`
- `/learn`
- `/review` workspace routing
- `/fixci`
- `/ship`
- `/jobs`

### 2. Repo Intelligence

- workspace inspection
- symbol indexing
- dependency hints from imports
- hotspot detection
- impact-file suggestions
- suggested test targets
- cached architecture digest

### 3. Project Memory

- read conventions from `LUMI.md`
- persist decisions
- persist recent runs
- persist artifact history

### 4. Background Execution

- queued Workbench jobs in the TUI
- live status summaries
- side pane for active and completed jobs

### 5. Artifact Generation

- commit title
- PR description
- release notes
- changelog entry
- test summary
- architecture summary

## Command Behavior

### `/build <task>`

1. inspect workspace
2. build a risk-aware plan
3. find relevant files and checks
4. execute through the agent path
5. store run metadata
6. generate ship-ready artifacts

### `/learn [topic]`

1. inspect workspace
2. index repo symbols and imports
3. summarize architecture and conventions
4. surface hotspots, impact files, and tests
5. cache the intelligence snapshot

### `/review workspace`

1. inspect workspace
2. collect relevant files and checks
3. run review-oriented planning
4. surface risk, warnings, and suggested checks

### `/fixci [goal]`

1. inspect workspace and verification commands
2. plan around CI, lint, type, or test failures
3. execute through the agent path
4. record result and artifacts

### `/ship [goal]`

1. inspect workspace
2. run detected verification commands
3. summarize verification state
4. generate release artifacts
5. store artifact history

## TUI Integration

- background job queue inside `LumiTUI`
- Workbench pane with live job summaries
- command palette entries for all Workbench commands
- system-message rendering for completed Workbench runs

## CLI Integration

- classic CLI help updated with Workbench commands
- `/build`, `/learn`, `/fixci`, and `/ship` available outside the TUI
- workspace review routes through Workbench when appropriate

## Reports

- `/status` includes Workbench summary
- `/doctor` includes Workbench summary
- prompt identity mentions Workbench capabilities

## Release Surface

- app branding updated to `Lumi v0.5.0: Forge`
- README refreshed around Forge Workbench
- rebirth remains available as a profile, not the primary release name

## Validation Target

- `ruff check .`
- `pytest -q`
- `python scripts/benchmark_gate.py --config configs/benchmark_gate.json`
- `python scripts/rebirth_audit.py --strict`
