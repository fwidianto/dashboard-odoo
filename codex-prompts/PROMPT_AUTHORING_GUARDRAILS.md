# Prompt Authoring Guardrails — Odoo Control Tower

**Effective:** 2026-08-04  
**Authority:** Owner-approved pilot-first delivery policy in `fwidianto/personal-OS/03_Projects/Odoo_Analytics/PILOT_FIRST_DELIVERY_GUARDRAILS.md`

This file governs every future Codex task prompt and every ChatGPT GitHub review for the Control Tower.

## Roadmap anchor

The owner reactivated the frozen Control Tower roadmap on 2026-08-05. The current active capability is **Phase 3 — Real Refresh Data workflow** as recorded in the canonical PersonalOS status update.

Every future prompt and review must anchor to these rules:

- normal Refresh Data must use the incremental pipeline;
- full extraction is maintenance/bootstrap/recovery only;
- a visible button is not accepted unless its real execution path is operationally feasible;
- mocked tests cannot prove operational runtime;
- staging measurement is required before claiming the refresh capability is ready;
- Phase 3 is the current active capability after the canonical PersonalOS status update;
- no frontend redesign or later roadmap work may interrupt it unless a real blocker is demonstrated.

Historical descriptions of frontend recovery or a full-extraction normal path remain historical, paused, or completed evidence only.

## Mandatory live preflight

Before publishing any new Codex task, ChatGPT must freshly load the current authority files through the GitHub connector. Previously fetched content, conversation memory, and summaries are not sufficient substitutes.

The automatic trigger includes:

- `Prompt Codex`;
- `Review and continue`;
- `continue and prompt Codex`;
- `prepare the next task`;
- equivalent requests asking ChatGPT to choose or publish the next implementation run.

Load at minimum:

1. `fwidianto/personal-OS/03_Projects/Odoo_Analytics/PROJECT_STATUS.md`;
2. `fwidianto/personal-OS/03_Projects/Odoo_Analytics/PILOT_FIRST_DELIVERY_GUARDRAILS.md`;
3. `fwidianto/dashboard-odoo/AGENTS.md` from the target implementation branch;
4. this file from `codex-prompts`;
5. `codex-prompts/tasks/CURRENT.md` when a current task exists;
6. the active task file and the smallest relevant roadmap/design authority.

If any required authority cannot be loaded, stop before writing to the prompt branch. Do not reconstruct the rules from memory.

`Review GitHub` authorizes review and classification only. It does not authorize a correction prompt or next task.

## Mandatory prompt gate

After the live preflight and before publishing a task, answer:

1. What can the user visibly see, understand, or do after this task?
2. Is this the shortest path to the next usable capability?
3. What concrete normal-use failure does any backend-only work prevent?
4. Does the work protect Odoo read-only behavior, company isolation, trusted snapshot safety, ordinary refresh/retry correctness, or the agreed user result?
5. Was the issue inside the frozen acceptance criteria?
6. What visible product work would be delayed by doing this now?
7. What is explicitly deferred?
8. What is the stopping condition?
9. Is the decision `ACCEPT`, `ONE CORRECTION`, or `DEFER`?

Show this compact **Orchestrator Gate** to the owner before any prompt-branch write.

Do not publish the task when the only justification is theoretical completeness, arbitrary direct-database tamper resistance, exhaustive forensic consistency, generic cleanup, or speculative production scale.

## Blocking standard

A finding may block only when a credible normal application path can cause:

- Odoo writes or a security breach;
- cross-company contamination;
- corruption/loss of trusted data, publication state, or watermarks;
- unsafe or unusable ordinary refresh/retry behavior;
- a materially wrong or misleading supported user result;
- unrecoverable schema/data loss;
- inability to complete the current visible capability.

Every blocking review must explain the user-visible consequence, normal trigger path, likelihood, impact, and why deferral is unsafe.

Manual PostgreSQL tampering, cryptographic binding of every internal field, broad observability, speculative scale, and cleanup are normally `IMPORTANT LATER` or `LOW PRIORITY`.

## Acceptance freeze

Freeze acceptance criteria before the run. Do not add new acceptance requirements after implementation unless they pass the blocking standard above.

Review against the agreed capability, not theoretical perfection.

## Correction limit

Default per capability:

```text
one implementation run
→ one consolidated review
→ at most one correction run
```

Any further correction requires explicit owner approval, a concrete normal-use failure, and a stated product tradeoff.

CT-8C2-R4 was already running when this policy took effect. After it finishes, do not publish CT-8C2-R5 unless the R4 commit introduces a normal-use blocker.

## Visible-progress rule

Do not schedule more than two consecutive backend-only substantive runs. The next run must create a user-operable or visually reviewable result unless a real blocker prevents it.

After CT-8C2-R4, the next required milestone is the smallest end-to-end Refresh Data vertical slice:

```text
trusted data visible
→ Refresh Data action
→ understandable progress
→ plain-language success/failure
→ trusted data remains on failure
→ updated data/timestamp on success
→ one real Sales Order case verified
```

## Required review output

Lead every review with:

1. user-visible outcome;
2. normal-use failure prevented;
3. likelihood and impact;
4. classification: `BLOCKER`, `MUST DO NOW`, `IMPORTANT LATER`, or `LOW PRIORITY`;
5. pilot decision: accept, correct once, or defer;
6. next visible step.

Technical evidence follows. Do not make the owner interpret low-level terminology to understand the decision.

## Run budget

Treat run estimates as product constraints. When the buffer is consumed, defer lower-value hardening first. Do not preserve an estimate by silently compressing UI, UX, reporting, owner validation, or deployment work.
