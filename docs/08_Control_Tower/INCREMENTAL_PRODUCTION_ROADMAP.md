# Odoo Control Tower — Incremental Production Roadmap

**Status:** Owner-approved high-level roadmap  
**Delivery model:** Capability-based incremental production rollout  
**Product boundary:** Read-only Odoo evidence and human-reviewed operational guidance

## 1. Roadmap Principle

The Control Tower will not wait for the whole application to be complete before deployment.

Each release must deliver one small capability that is:

- useful to a real user;
- supported by trusted evidence;
- understandable without technical interpretation;
- safe within a stated production boundary;
- validated from source or database through API and browser;
- releasable to a small audience;
- expandable without pretending unfinished areas are complete.

The product grows through repeated capability cycles:

```text
user promise
→ thin vertical slice
→ trustworthy validation
→ small-scale production rollout
→ real-user observation
→ stabilization
→ next capability
```

## 2. Product North Star

The Odoo Control Tower should help operational reviewers answer:

1. Where is the business process now?
2. Which records require attention?
3. Why do they require attention?
4. What evidence supports the conclusion?
5. Which exact document should the user open next?

Technical components such as SQL views, persistence tables, APIs, and extraction jobs are supporting foundation. Roadmap milestones are defined by the user capability they enable.

## 3. Production Readiness by Capability

The project does not use one broad production-ready percentage as its primary progress measure.

Each capability is tracked through these gates:

- **A — Defined**
- **B — End-to-end working**
- **C — Small-scale production ready**
- **D — User validated**
- **E — Ready to expand**

A capability can be production-ready within a narrow boundary while other parts of the Control Tower remain unimplemented.

## 4. Current Release Roadmap

### Release 0.1 — Visual Process Navigator

**User promise**

> Users can understand the approved high-level business flow from Estimasi/RKB through Payment and inspect the two fulfilment paths.

**Included**

- process flow:
  - Estimasi/RKB;
  - Quotation;
  - Sales Order;
  - Fulfilment;
  - Delivery;
  - Invoice;
  - Payment;
- fulfilment choices:
  - Manufacturing Order;
  - From Stock / Internal Order;
- material planning branch:
  - RKB Pekerjaan;
  - Cek Stock;
  - ROP;
  - Purchase Order;
  - Receipt & QC;
- four reviewed interaction states;
- keyboard-accessible interaction;
- responsive horizontal navigation.

**Production boundary**

- read-only visual reference;
- no live Odoo counts;
- no finding badges;
- no claim of real-time process status;
- no full document lineage.

**Current status**

- merged to `main` in PR #9;
- small-scale production-ready for use as a visual process navigator;
- next action is deployment confirmation and bounded user observation.

### Release 0.2 — First Actionable Finding: Sales Order Data Completeness

**User promise**

> Users can see confirmed 2026 Sales Orders that are missing Customer Reference or Customer PO Date and open the exact affected Sales Order.

**Approved rule**

- category: `DATA_BELUM_LENGKAP`;
- canonical rule: `DH2-SALES-001`;
- source check: `SO-PO-001`;
- applicable to confirmed Sales Orders with `date_order >= 2026-01-01`;
- `write_date` is not a fallback for business applicability.

**Included**

- deterministic finding identity;
- internal `OPEN` and `RESOLVED` lifecycle;
- first and last detection timestamps;
- authenticated findings API;
- Temuan page with user-readable remediation;
- honest loading, empty, error, retry, and not-found behavior;
- exact Sales Order deep link;
- company isolation.

**Production boundary**

- one approved rule only;
- one category only;
- one company context at a time;
- read-only review aid;
- no Archives UI;
- no manual acknowledgement, assignment, or comments;
- no Process Map badge;
- no user-facing Refresh Data implementation.

**Current status**

- end-to-end implementation exists on `feat/control-tower-temuan-so-data-v01`;
- focused Python, Node, browser, and repository checks have passed;
- real snapshot currently contains zero approved-rule mismatches;
- dynamic PostgreSQL lifecycle validation is the remaining gate before final review, commit, PR, independent review, merge, and deployment.

### Release 0.3 — Sales Order Awareness on the Process Map

**User promise**

> Users can see when the Sales Order process has active trusted findings and open the matching filtered Temuan list from the Process Map.

**Minimum scope**

- Sales Order node only;
- counts sourced only from approved open findings;
- category badge only for implemented categories;
- click node or badge opens a correctly filtered Temuan view;
- no placeholder counts on unsupported nodes.

**Production boundary**

- only Release 0.2 findings are represented;
- other process nodes remain visual only;
- full journey and lineage remain in Tracking, not the Process Map.

**Entry gate**

- Release 0.2 merged and deployed;
- finding count reconciles with the Temuan list;
- first users confirm the finding wording and destination are understandable.

### Release 0.4 — User-Visible Data Freshness and Refresh Status

**User promise**

> Users can tell when the displayed data was last refreshed, whether the latest refresh succeeded, and whether information may be stale.

**Minimum scope**

- last successful refresh timestamp;
- refresh in-progress state;
- refresh failed state;
- clear user-facing failure message;
- no presentation of stale data as current;
- administrator-safe execution path.

**Production boundary**

- does not yet promise full self-service incremental orchestration;
- no concurrent refresh architecture claim until locking and recovery are proven;
- user-visible Refresh Data behavior must not be added before transactional safety is validated.

### Release 0.5 — Additional Sales Order Findings

**User promise**

> Users receive additional trustworthy, actionable Sales Order review signals with clear evidence and exact document navigation.

**Minimum scope per added rule**

- approved business meaning;
- direct or explicitly approved evidence fields;
- deterministic positive and negative fixtures;
- user-readable title and remediation;
- exact destination;
- company-safe persistence;
- owner review before production.

Add one or two rules at a time. Do not activate the entire registry in one release.

### Release 0.6 — First Purchase Order Finding

**User promise**

> Users can see one important Purchase Order issue or data gap and open the exact Purchase Order that requires review.

Build as a fresh thin vertical slice:

```text
one approved PO rule
→ persistent finding
→ Temuan
→ exact Purchase Order
```

Do not assume the Sales Order implementation automatically proves Purchase Order semantics.

### Later Capability Releases

Order is value-driven and may change after user observation.

Candidate capabilities:

1. Manufacturing Order findings;
2. From Stock / Internal Order findings;
3. material planning and procurement findings;
4. Delivery findings;
5. Invoice findings;
6. Payment traceability findings after Accounting approval;
7. Archives and visible finding history;
8. Tracking and end-to-end document journey;
9. Gross Profit and margin views after approved financial contracts;
10. broader users, companies, automation, and operational scale.

Each remains a separate capability release with its own production boundary.

## 5. Release Selection Rule

Choose the next release based on the strongest combination of:

- user value;
- trusted available evidence;
- low risk of misleading interpretation;
- ability to complete an end-to-end path;
- feedback from the most recent production capability.

Do not select the next release only because backend infrastructure is convenient to build.

## 6. Standard Capability Definition

Every Control Tower release must state:

1. **User promise** — what the user can newly do.
2. **First users** — who receives the release first.
3. **Source of truth** — exact approved data or rule basis.
4. **Production boundary** — where the capability is safe and truthful.
5. **End-to-end flow** — source through user action.
6. **Success and failure behavior** — including empty and not-found.
7. **Validation evidence** — database, API, browser, and reconciliation.
8. **Rollback path** — how to disable or revert safely.
9. **Observation plan** — what will be learned from real users.
10. **Expansion gate** — what must be stable before adding breadth.

## 7. User-Visible Progress Rule

Backend progress is not hidden, but it is reported as supporting foundation beneath a user-visible outcome.

Preferred roadmap language:

> Users can open the exact Sales Order that is missing customer PO information.

Supporting technical tasks:

- persist deterministic findings;
- expose authenticated API;
- add company-scoped projection;
- implement deep-link behavior.

Avoid presenting the supporting tasks as the primary milestone.

## 8. Release Observation Standard

After each small-scale deployment, review:

- comprehension of labels and messages;
- trust in data and evidence;
- false positives and missing cases;
- whether the next action is obvious;
- navigation behavior;
- freshness expectations;
- performance and failures;
- the next highest-value user capability.

Stabilize material trust and usability defects before expanding. Cosmetic perfection is not required to begin the next bounded release.

## 9. Current Program Position

```text
Release 0.1 — Visual Process Navigator
Gate C: small-scale production ready

Release 0.2 — Sales Order Data Completeness Finding
Gate B: end-to-end working
Next gate: dynamic PostgreSQL lifecycle validation

Release 0.3 — Sales Order Finding Badge on Process Map
Gate A: defined at high level; implementation not started
```

The immediate program objective is not to complete the entire Control Tower.

It is to deploy Release 0.1 within its truthful boundary, complete and deploy Release 0.2, observe real use, and then activate Release 0.3 using the trusted findings foundation.
