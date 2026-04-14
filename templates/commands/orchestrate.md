---
description: Orchestrate the full Moon Spec lifecycle from request or design through final verification.
handoffs:
  - label: Specify Single Story
    agent: speckit.specify
    prompt: Create a one-story specification from the request.
  - label: Break Down Design
    agent: speckit.breakdown
    prompt: Split the design into coverage-checked one-story specs.
  - label: Plan Story
    agent: speckit.plan
    prompt: Create an implementation plan for the selected spec.
  - label: Generate Tasks
    agent: speckit.tasks
    prompt: Create TDD-first implementation tasks for the selected spec.
  - label: Align Artifacts
    agent: speckit.align
    prompt: Analyze and remediate artifact drift before implementation.
  - label: Implement Story
    agent: speckit.implement
    prompt: Implement the selected story from tasks.md.
  - label: Verify Implementation
    agent: speckit.verify
    prompt: Verify the final implementation against the original request.
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Coordinate the Moon Spec workflow end to end using the installed Spec Kit commands. This command is a meta-command: it classifies the request, chooses the next required stage, invokes or follows the appropriate `/speckit.*` command, enforces artifact gates between stages, and finishes with `/speckit.verify`.

## Command Invocation Rules

- Use the canonical command IDs and user-facing command names:
  - `/speckit.specify`
  - `/speckit.breakdown`
  - `/speckit.plan`
  - `/speckit.tasks`
  - `/speckit.align`
  - `/speckit.implement`
  - `/speckit.verify`
- Do **not** use Codex-only `moonspec-*` skill names in orchestration instructions or reports.
- If the host agent can invoke another installed command directly, invoke the canonical command and wait for its result before advancing.
- If the host agent cannot invoke another command from inside this command, execute the same workflow inline by reading the corresponding installed command for the active integration, such as a sibling `speckit.<name>.*` command file or `speckit-<name>/SKILL.md`, and following it exactly.
- When reporting a command handoff, use the canonical command ID, for example:

  ```text
  EXECUTE_COMMAND: speckit.plan
  EXECUTE_COMMAND_INVOCATION: /speckit.plan <prompt or context>
  ```

- For native skill-backed integrations, the visible invocation may be rendered differently by the agent, but this orchestration still refers to the canonical `/speckit.*` command names.

## Inputs

- Required: a feature request, active feature directory, or broad declarative design.
- Optional: implementation constraints, testing constraints, scope boundaries, source design paths, target story, or verification focus.
- If no request or active feature context is available, ask once for the missing input before starting.

Default intent is `runtime`: production code plus tests must be delivered. Use `docs` intent only when the user explicitly asks for documentation-only work.

## Core Rules

- Moon Spec uses one independently testable story per `spec.md`.
- Broad designs must go through `/speckit.breakdown` before planning.
- Single-story requests go through `/speckit.specify`.
- TDD is the default strategy.
- Unit tests and integration tests are both expected.
- The original request or source design preserved in `spec.md` `**Input**` is the final alignment source.
- `/speckit.align` replaces the old multi-step analyze remediation sequence for automatic artifact edits.
- Do not synthesize user approvals, scripted user responses, or pretend an analyze report exists.
- Resume from existing artifacts when they pass gates; do not regenerate by default.
- Preserve unrelated user changes in the worktree.

## Resume Model

Before running a stage, inspect the active feature state:

- `spec.md`
- `plan.md`
- `research.md`
- `data-model.md`
- `contracts/`
- `quickstart.md`
- `tasks.md`
- relevant production code and tests
- previous verification report when available in the conversation

Resume from the first incomplete stage. If artifacts are inconsistent, use `/speckit.align` when `spec.md`, `plan.md`, and `tasks.md` exist; otherwise stop and report the missing artifact that prevents safe alignment.

Do not overwrite later-stage artifacts unless:

- the user requested regeneration, or
- `/speckit.align` determines conservative artifact edits are required, or
- an upstream artifact changed and downstream artifacts must be regenerated to remain coherent.

## Artifact Gates

Use these gates before advancing:

- Specify gate:
  - `spec.md` exists.
  - It contains exactly one user story.
  - The original request or source design is preserved in `**Input**`.
  - Requirements are testable and contain no unresolved story-critical clarification.
- Breakdown gate:
  - `specs/breakdown.md` exists when a broad design was split.
  - Each generated `spec.md` contains one story.
  - Each generated spec preserves the source design in `**Input**`.
  - Source design coverage IDs such as `DESIGN-REQ-*` are mapped.
- Plan gate:
  - `plan.md` exists.
  - `research.md` and `quickstart.md` exist.
  - `data-model.md` exists when the story involves data.
  - `contracts/` exists when the story exposes an API, CLI, UI contract, event, parser, library surface, or external interface.
  - Unit and integration test strategies are identified.
- Tasks gate:
  - `tasks.md` exists.
  - It covers exactly one story.
  - It includes unit test tasks, integration test tasks, red-first confirmation tasks, implementation tasks, story validation, and final `/speckit.verify`.
  - Source design or original request mappings have task coverage.
- Align gate:
  - `/speckit.align` has run after `tasks.md` generation unless the user explicitly skipped alignment.
  - Any artifact changes from alignment have been validated or propagated.
- Implement gate:
  - Required implementation work is done.
  - Completed tasks are marked `[X]`.
  - Unit and integration tests have been run or blocked with exact reasons.
- Verify gate:
  - `/speckit.verify` produced a concrete report for the active `spec.md`.
  - Verdict is not `NO_DETERMINATION`.
  - Completion is claimed only when verdict is `FULLY_IMPLEMENTED`.

If a gate fails, stop or run the appropriate upstream command. Do not continue on a claimed success without artifacts or evidence.

## Workflow

### 1. Classify Input

Classify the request:

- Single-story feature request: use `/speckit.specify`.
- Broad technical or declarative design: use `/speckit.breakdown`.
- Existing feature directory: resume from current artifacts.
- Documentation-only request: use `docs` intent only when explicitly requested.

For `Implement Docs/<path>.md` style requests, treat the document as a runtime source design unless the user explicitly says documentation-only.

### 2. Create Or Select Specs

For a single story:

1. Run `/speckit.specify` if `spec.md` does not already exist.
2. Verify the specify gate.

For a broad design:

1. Run `/speckit.breakdown`.
2. Verify the breakdown gate.
3. Select the recommended first spec unless the user asked to implement all generated specs.
4. For "all specs", process each generated spec in dependency order, one spec at a time.

### 3. Plan

For the selected spec:

1. Run `/speckit.plan` if the plan gate is incomplete.
2. Verify generated artifacts.
3. Stop if planning requires unresolved user input.

### 4. Generate Tasks

1. Run `/speckit.tasks` if the tasks gate is incomplete or upstream artifacts changed.
2. Verify `tasks.md` format, single-story focus, TDD order, unit/integration coverage, source traceability, and final `/speckit.verify`.

### 5. Align Artifacts

1. Run `/speckit.align` after task generation.
2. Let `/speckit.align` make conservative artifact edits without asking for follow-up responses.
3. If `/speckit.align` changes `spec.md`, `plan.md`, design artifacts, or `tasks.md`, re-check downstream gates.
4. Regenerate only the downstream artifact that is now stale; do not restart the full pipeline automatically.

This replaces the old manual analyze remediation flow. Do not provide scripted "yes", "continue", or other user responses to get through analyze limitations.

### 6. Implement

1. Run `/speckit.implement` when implementation work remains.
2. Require TDD execution: unit tests and integration tests are written and confirmed failing before production code.
3. Require completed work to be marked `[X]` in `tasks.md`.
4. Preserve story scope; do not add hidden scope to make verification easier.

### 7. Verify

1. Run `/speckit.verify` as the final gate unless an up-to-date verification report already covers the current code and artifacts.
2. If verdict is `FULLY_IMPLEMENTED`, report success.
3. If verdict is `ADDITIONAL_WORK_NEEDED`, use the verification report as the remaining-work list:
   - run `/speckit.implement` for bounded code or test gaps,
   - rerun targeted unit/integration validation,
   - rerun `/speckit.verify`.
4. Run at most two verification-remediation cycles unless the user explicitly asks to keep going.
5. If verdict is `NO_DETERMINATION`, stop and report the exact missing evidence, commands, or context.

## Multi-Spec Designs

When `/speckit.breakdown` creates multiple specs:

- Process specs in dependency order from `specs/breakdown.md`.
- Keep each spec isolated through plan, tasks, align, implement, and verify.
- Do not merge multiple stories into one `tasks.md`.
- After each spec, report its verification verdict before moving to the next.
- Stop if a dependency spec fails verification and blocks later specs.

## Commit And PR Behavior

Do not create commits or pull requests unless the user explicitly asks or the current orchestration environment requires that output.

If commit or PR creation is requested but cannot complete because of missing authentication, remote configuration, branch state, or permissions, report the exact blocker and the minimum manual command needed.

## Final Report

Return a concise report:

```markdown
## MoonSpec Orchestration

Feature:
- [spec path or generated spec list]

Stages:
- Specify/Breakdown: PASS/FAIL/SKIPPED
- Plan: PASS/FAIL/SKIPPED
- Tasks: PASS/FAIL/SKIPPED
- Align: PASS/FAIL/SKIPPED
- Implement: PASS/FAIL/SKIPPED
- Verify: FULLY_IMPLEMENTED/ADDITIONAL_WORK_NEEDED/NO_DETERMINATION/SKIPPED

Changed files:
- [paths]

Tests:
- [command]: [PASS/FAIL/NOT RUN]

Remaining risks:
- [risk or "None"]

Next action:
- [only if work remains]
```

Mention source design coverage and `DOC-REQ-*`/`DESIGN-REQ-*` status when present.

## Key Rules

- Use `/speckit.*` commands for downstream work.
- Use `/speckit.align`, not the old analyze prompt workaround.
- Do not invent user approvals or fake intermediate outputs.
- Enforce one story per spec.
- Keep TDD, unit tests, integration tests, and `/speckit.verify` in the pipeline.
- Treat verification as the final authority for completion.
