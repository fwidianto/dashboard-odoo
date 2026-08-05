# Current Codex Task

- **Task ID:** CT-8E1
- **Task file:** `codex-prompts/tasks/CT-8E1-complete-incremental-refresh.md`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Required implementation base:** `fe8cb2029210420203dfc43920eb7eb979d3398d`
- **Capability:** Phase 3 — Real Incremental Refresh Data
- **Classification:** BLOCKER / MUST DO NOW
- **Role:** implementation
- **Prompt branch:** `codex-prompts`

## Owner-visible outcome

The normal Control Tower `Refresh Data` action must use the existing incremental foundation end to end rather than the 2–3 hour full extraction path. Trusted data remains visible until successful publication, changed and no-change outcomes are truthful, and the result is ready for the owner’s controlled staging test.

## Standing rules

- OpenCode/Codex must fetch the prompt branch and read the exact task file from the prompt commit supplied by ChatGPT.
- Do not merge or check out the prompt branch into the implementation branch.
- Confirm the implementation branch is exactly at the required base before editing.
- Normal Refresh Data must be incremental; full extraction is maintenance/bootstrap/recovery only.
- Odoo remains read-only and company scope remains company 3.
- Do not publish partial data or advance watermarks on failure.
- Do not continue frontend recovery, redesign the Control Tower, or begin later roadmap work.
- Stop after one implementation commit and push. Do not begin a correction or next task automatically.

This task is governed by `codex-prompts/PROMPT_AUTHORING_GUARDRAILS.md`, the current PersonalOS `PROJECT_STATUS.md`, the frozen Control Tower `ROADMAP.md` Phase 3, repository `AGENTS.md`, and the task file above.

## Closed task history

- **CT-8D1-R1** — completed at `9dd9904500720be09d6074a21f85e7c2554e5917` (`fix(control-tower): replace evidence state on refresh`).
- **CT-8D1-R2** — completed at `75891225f179d405eb4c86440199a0e518893968` (`fix(control-tower): add stale refresh recovery action`).