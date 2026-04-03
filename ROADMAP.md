# Lumi Roadmap

Lumi's next program is not cosmetic polish. It is a Claude-parity push followed by a runtime rewrite.

## Release Path

- `v0.5.0: Forge`
  - historical baseline
  - repo-aware workbench, project memory, hooks, skills, and background execution baseline
- `v0.6.0: Mirror`
  - historical parity-mapping release
  - closed the highest-value command, workflow, and subsystem gaps against Claude Code
- `v0.7.0: Operator`
  - current release
  - execution-focused Python release
  - closes the highest-value command, workflow, and subsystem gaps against Claude Code
- `v1.0.0: Native`
  - Bun/TypeScript/Ink rewrite
  - reimplements Lumi on a runtime shape closer to Claude Code once Operator behavior is stable

## Operator Goal

Operator should make Lumi feel close enough to Claude Code in real use that the later rewrite is mainly architectural, not a product redesign.

That means closing gaps in:

- permission rules
- tool architecture
- git workflows
- code review surfaces
- sessions and context control
- tasks and agents
- repo intelligence
- IDE bridge foundations
- settings, usage, and install flows
- TUI control density
- measurable parity auditing

## The 17 Operator Workstreams

1. Wildcard tool permission engine
2. Explicit tool registry
3. Git workflow suite
4. Code-quality command suite
5. Session and context parity
6. Background task engine
7. Sub-agent orchestration
8. LSP repo intelligence
9. IDE bridge
10. Full settings layer
11. Usage and telemetry surfaces
12. Install, init, and upgrade flows
13. Plugin and skill lifecycle parity
14. Remote and device handoff layer
15. TUI control-density parity
16. Missing command parity cleanup
17. Parity and regression audit

Full spec: [LUMI_MIRROR_SPEC.md](/home/sardorchikdev/Lumi/LUMI_MIRROR_SPEC.md)

## Execution Order

### Phase 1: Control Plane

- permission engine
- tool registry
- git workflow suite
- code-quality suite

### Phase 2: Runtime Core

- session/context parity
- background task engine
- sub-agent orchestration
- LSP repo intelligence

### Phase 3: Operator Surfaces

- IDE bridge
- settings layer
- usage/telemetry
- install/init/upgrade
- plugin and skill lifecycle parity
- remote/device handoff
- TUI control-density parity

### Phase 4: Lock And Rewrite

- remaining command cleanup
- parity audit and regression gate
- freeze behavior
- move to `v1.0.0: Native`

## Audit Rule

Parity claims should be backed by the audit command, not by UI similarity.

Run:

```bash
./venv/bin/python scripts/claude_parity_audit.py
```

## Rewrite Rule

Do not switch languages until these contracts are stable:

- tool contracts
- permission contracts
- task and agent lifecycle contracts
- settings schema
- command definitions
- parity audit criteria
