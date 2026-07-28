# Incremental Production Workflow Standard

**Status:** Owner-approved working standard  
**Applies to:** Dashboard Odoo, Odoo Protocol / Control Tower, and future user-facing projects unless a stricter approved standard applies.

## 1. Core Principle

Projects should move from zero to useful production capability as early as trustworthiness allows.

Do not wait for the whole product to be complete. Build one small capability that is correct, understandable, safe for a bounded audience, and ready to use. Release it at small scale, observe real use, stabilize it, and then expand.

The standard is:

```text
Define user promise
→ bound the production scope
→ build a thin vertical slice
→ validate trustworthiness
→ explain the result in user language
→ deploy at small scale
→ observe real use
→ stabilize
→ expand one capability
```

## 2. What Counts as Progress

### 2.1 Technical progress

Examples:

- schema or migration created;
- query or API implemented;
- synchronization or rule logic added;
- automated tests added;
- performance or reliability improved.

Technical progress is necessary, but it is not a product milestone by itself.

### 2.2 User-visible progress

Examples:

- users can see new trustworthy information;
- users can understand why it matters;
- users can open the exact affected document;
- users can take the next operational action;
- loading, empty, error, and not-found states are clear.

A milestone is considered materially delivered only when the technical work produces a bounded user-visible capability.

## 3. Standard Delivery Stages

### Stage 1 — Define the user promise

Answer:

> What can the user do after this release that they could not do before?

Required output:

- user problem;
- user capability;
- first intended users;
- source of truth;
- scope and explicit non-scope.

Write the milestone in user language, not component language.

Good:

> Users can see Sales Orders with incomplete customer PO data and open the exact Sales Order.

Avoid:

> Add a finding table and API endpoint.

### Stage 2 — Select the minimum usable slice

Choose the smallest complete path that provides value:

```text
source data
→ business rule or transformation
→ backend contract
→ API or delivery mechanism
→ user interface
→ user action
```

Prefer one complete path over several unfinished backend components.

Required behavior includes, where relevant:

- success state;
- empty state;
- loading state;
- error state;
- not-found state;
- exact destination or next action.

### Stage 3 — Declare the production boundary

Define where the capability is safe and truthful to use.

Examples:

- read-only;
- one company;
- one process or rule;
- internal users only;
- administrator-triggered refresh;
- review aid, not automatic business decision;
- no write-back or automated closure.

Use this format:

> This release is production-ready for **X** within **Y boundary**. It does not yet support **Z**.

### Stage 4 — Build the thin vertical slice

Implementation priorities:

1. correct information;
2. understandable information;
3. exact source-document navigation or action;
4. honest empty and failure behavior;
5. only the foundation needed for trustworthiness;
6. optimization and generalization later.

Do not build a broad framework for hypothetical future requirements when a bounded implementation is sufficient.

### Stage 5 — Validate trustworthiness

Validate the complete path, not only whether code runs.

Minimum validation layers:

```text
database or source evidence
→ service/API contract
→ browser or user interaction
```

Check, as applicable:

- approved source fields and business meaning;
- deterministic and idempotent behavior;
- no cross-company leakage;
- correct resolution or recurrence behavior;
- exact document destination;
- truthful empty state;
- visible failure state;
- authentication and authorization;
- migration and rollback path.

Claims must use the narrowest readiness language supported by evidence.

### Stage 6 — Translate technical output into user information

Every user-facing result should answer:

1. What happened?
2. Which document or process is affected?
3. Why is it shown?
4. What should the user do?
5. Where should the user go next?

Avoid exposing technical rule failures without operational explanation.

Technical:

> SO-PO-001 failed.

User-facing:

> Customer PO Date is missing on SO00123. Complete the Customer PO Date on that Sales Order.

### Stage 7 — Small-scale production rollout

Release first to a bounded audience or operational area, for example:

- owner only;
- owner plus one reviewer;
- one department;
- one company;
- one process;
- one rule set.

Small-scale rollout limits blast radius; it does not permit false data or unfinished primary flows.

Required release evidence:

- release version or commit;
- deployed route or artifact;
- intended users;
- production boundary;
- release notes;
- rollback method.

### Stage 8 — Observe real use

Before immediately expanding, observe:

- whether users understand the information;
- whether terminology matches daily work;
- whether users know the next action;
- false positives or missing cases;
- navigation confusion;
- performance and failure patterns;
- requests that show the next highest-value capability.

Real user evidence has higher priority than speculative polish.

### Stage 9 — Stabilize

Fix issues that materially block trust or use:

- incorrect data;
- wrong destination;
- unclear message;
- hidden failure;
- unacceptable performance;
- access or company-scope defect.

Do not delay expansion indefinitely for cosmetic perfection.

### Stage 10 — Expand one capability

Expansion may mean:

- another rule;
- another process node;
- another filter;
- another user group;
- safer refresh;
- an additional action;
- higher frequency or scale.

Then restart at Stage 1 with a new user promise.

## 4. Capability Gates

### Gate A — Defined

Ready to build when:

- user problem and promise are clear;
- source data is identified;
- production boundary is explicit;
- non-scope is written;
- owner review path is known.

### Gate B — End-to-end working

Ready for validation when:

- the full source-to-user path works in development;
- primary success, empty, and failure behavior exist;
- no placeholder or fabricated data is shown.

### Gate C — Small-scale production ready

Ready to deploy to a bounded audience when:

- data and business meaning are validated;
- authentication and company scope are correct;
- database/API/browser validation passes;
- migration and rollback are known;
- limitations are visible and documented.

### Gate D — User validated

Ready to stabilize or expand when real users can:

- understand the information;
- trust the result for the stated purpose;
- identify the next action;
- use the capability without hidden manual interpretation.

### Gate E — Ready to expand

Expansion is allowed when:

- no critical trust or usability defect remains;
- observed behavior supports the next capability;
- current production boundary remains protected.

## 5. Roadmap and Progress Reporting

Do not report only a broad project percentage. Track production readiness per capability.

Example:

| Capability | Gate | Production boundary |
| --- | --- | --- |
| Visual Process Navigator | C | Read-only process reference; no live counts |
| Sales Order Data Completeness Finding | B | One approved rule; validation pending |
| Process Map Finding Badge | A | Sales Order node only |

Backend work may be listed as supporting evidence, but user-visible outcomes lead the roadmap and status report.

## 6. Standard Completion Report

Every substantial iteration must report in this order.

### A. User-visible outcome

1. What users can now do.
2. Where to start.
3. The exact user flow.
4. Success, empty, error, and not-found behavior.
5. Current production boundary.
6. What is explicitly not supported.

### B. Technical evidence

1. Data source and business rule.
2. Files, schema, API, or architecture changed.
3. Tests and reconciliation performed.
4. Authentication and company-scope evidence.
5. Migration and rollback notes.
6. Repository and deployment status.
7. Remaining uncertainty.
8. One next bounded task.

## 7. Governing Rule

A technically significant change is not automatically a product release.

A release milestone should normally produce a capability that users can see, understand, and use within a clearly stated boundary. Necessary backend-only work is recorded as foundation under that user-visible milestone, not presented as the milestone itself.
