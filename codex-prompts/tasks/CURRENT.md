# Current Codex Task

- **Task ID:** CT-8D1-R1
- **Task file:** `codex-prompts/tasks/CT-8D1-R1-reset-evidence-reload.md`
- **Target implementation branch:** `feat/control-tower-refresh-center`
- **Required implementation base:** `f0f0eff84d9a5122ff6d84bb92f58244ea4d4a18`
- **Capability:** Truthful visible Refresh Data evidence reload
- **Prompt branch:** `codex-prompts`
- **Correction allowance:** One bounded correction for CT-8D1

Codex must fetch the prompt branch and read the task file from the exact prompt commit supplied by ChatGPT. Do not merge or check out the prompt branch into the implementation branch.

This task is governed by `codex-prompts/PROMPT_AUTHORING_GUARDRAILS.md`. Fix only the normal-use evidence accumulation/retention defect, validate it deterministically, push one commit, and stop. Do not start another backend or hardening cycle.