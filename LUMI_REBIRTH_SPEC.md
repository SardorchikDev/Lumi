# Lumi - rebirth Upgrade Spec

## Goal
Make Lumi match and exceed modern coding-agent workflows: safe autonomous edits, multi-agent reasoning, repo tooling, plugin governance, and high-signal diagnostics.

## Priority Sequence
1. Foundation hardening
- Keep deterministic agent actions and rollback-safe file edits.
- Enforce benchmark and regression gates in CI.
- Keep provider/model routing stable across TUI and classic CLI.

2. Capability parity visibility
- Add a single capability matrix (`/rebirth`) so users can verify what is ready.
- Track readiness score and expose it in `/status` and `/doctor`.
- Add machine-readable audit (`scripts/rebirth_audit.py`) for CI or release checks.

3. Workflow ergonomics
- Add a rebirth profile toggle (`/rebirth on|off`) to apply best-practice defaults quickly.
- Keep `/mode vessel` CLI handoff workflows visible in the rebirth quickstart.
- Keep benchmark scenarios discoverable from `/benchmark`.

4. Product identity + polish
- Ship visible branding as **Lumi - rebirth** in docs and TUI headers.
- Keep existing slash-command and plugin compatibility.
- Maintain test coverage for all new behavior.

## Done In This Pass
- Added `src/utils/rebirth.py` capability engine and readiness summary.
- Added `/rebirth` command in TUI and classic CLI handling.
- Added rebirth readiness lines into `/status` and `/doctor`.
- Added `configs/rebirth_profile.json` defaults.
- Added `scripts/rebirth_audit.py` for strict and JSON audits.
- Updated docs and command references for the rebirth flow.

## Release Verification
1. `./venv/bin/pytest -q`
2. `python scripts/benchmark_gate.py --config configs/benchmark_gate.json`
3. `python scripts/rebirth_audit.py --strict`
