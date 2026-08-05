# Current Codex Task

- **Task ID:** CT-8E1-R1
- **Task file:** `codex-prompts/tasks/CT-8E1-R1-correct-normal-refresh-edge-cases.md`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Required implementation base:** `3c4b019044da3f44fcca241444024e699d618a9c`
- **Capability:** Phase 3 — Real Incremental Refresh Data
- **Classification:** BLOCKER / MUST DO NOW
- **Decision:** ONE CORRECTION
- **Role:** correction
- **Prompt branch:** `codex-prompts`

## Owner-visible outcome

The normal incremental Refresh Data path must be ready for the owner's controlled staging test: mandatory watermark-second replay can still finish truthfully as `Tidak ada perubahan`, every supported reconciliation set completes before publication, only one active run can be created across processes, and watermark bootstrap is all-or-nothing.

## Standing rules

- OpenCode/Codex must fetch the prompt branch and read the exact correction task from the prompt commit supplied by ChatGPT.
- Do not merge or check out the prompt branch into the implementation branch.
- Confirm the implementation branch is exactly at the required base before editing.
- Correct only the four independently reviewed normal-path defects.
- Normal Refresh Data remains incremental; full extraction remains maintenance/bootstrap/recovery only.
- Odoo remains read-only and company scope remains company 3.
- Do not publish partial data or advance watermarks on failure.
- Do not redesign the frontend, add module selectors, refactor broadly, clean the repository, or begin later roadmap work.
- Push exactly one correction commit, then stop. Do not begin another correction or the owner staging test automatically.

This task is governed by `codex-prompts/PROMPT_AUTHORING_GUARDRAILS.md`, current PersonalOS `PROJECT_STATUS.md`, `PILOT_FIRST_DELIVERY_GUARDRAILS.md`, the frozen Control Tower ROADMAP Phase 3, target-branch `AGENTS.md`, CT-8E1, and the correction task above.

## Closed task history

- **CT-8D1-R1** — completed at `9dd9904500720be09d6074a21f85e7c2554e5917` (`fix(control-tower): replace evidence state on refresh`).
- **CT-8D1-R2** — completed at `75891225f179d405eb4c86440199a0e518893968` (`fix(control-tower): add stale refresh recovery action`).
- **CT-8E1** — implementation checkpoint at `3c4b019044da3f44fcca241444024e699d618a9c` (`feat(control-tower): complete incremental refresh path`), independently reviewed and requiring this one bounded correction before staging.
