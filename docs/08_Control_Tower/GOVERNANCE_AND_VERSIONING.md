# Governance and Versioning — Protocol, Dashboard, Ticket, and AI

**Status:** Active Governance v2 — incremental production rollout adopted

## 1. Core Principle

Odoo Protocol is the approved business contract. Dashboard Odoo is the monitoring and evidence layer. Ticketing stores operational learning. AI may analyze and propose, but human owners approve business changes.

The Control Tower is released incrementally by capability. The project does not wait for the entire roadmap to be complete before production use. A bounded capability may be released when it is trustworthy, understandable, safe for its stated users, and explicit about what it does not support.

The governing workflow is:

`docs/01_Project_Management/INCREMENTAL_PRODUCTION_WORKFLOW.md`

The current Control Tower capability sequence is:

`docs/08_Control_Tower/INCREMENTAL_PRODUCTION_ROADMAP.md`

## 2. Version Objects

The system maintains separate but linked versions:

| Object | Example | Owner |
| --- | --- | --- |
| SOP Version | `SOP-ODOO-1.2` | VP Operations / document controller |
| Rule Registry Version | `RULES-1.2` | Data Health Owner + process owners |
| Dashboard Release | `CT-0.3.0` | Dashboard technical owner |
| Capability Release | `CT-CAP-SO-FINDING-0.1` | Product owner + technical owner |
| Data Contract Version | `DATA-1.1` | Data/technical owner |
| Ticket Resolution | `TKT-2026-0042` | Ticket coordinator / process owner |
| SOP Change Proposal | `SCP-2026-0010` | AI draft; human reviewer/approver |

Versions do not have to share identical numbers, but every production capability release must declare the SOP, Rule Registry, data contract, production boundary, and user scenario it implements.

## 3. Change Types

### A. SOP-only Clarification

No data logic changes. Example: improve wording or screenshot.

### B. Rule-only Technical Correction

Business rule unchanged; query or linkage fixed after false positive.

### C. Joint Business Change

SOP, rule logic, test cases, and dashboard all change together.

### D. Data Contract Change

Source field/model or transformation changes while business meaning remains stable.

### E. Capability Expansion

A new user-visible function, rule, process, action, user group, or scale boundary is added while preserving existing approved behavior.

Capability expansion starts with a new user promise and production boundary. It is not justified only because backend infrastructure already exists.

## 4. Standard Change Flow

```text
Ticket / anomaly / management decision / user observation
→ define the user or business outcome
→ factual investigation
→ root cause and resolution verified by human
→ SOP and rule impact classification
→ define the minimum usable capability and production boundary
→ AI creates SOP Change Proposal when relevant
→ process owner review
→ Data Health Owner checks dashboard impact
→ VP Operations approves business-rule changes
→ update SOP draft and Rule Registry
→ implement the smallest source-to-user vertical slice
→ database/API/browser validation
→ independent review
→ small-scale production rollout
→ observe real use
→ stabilize material trust and usability issues
→ publish linked versions
→ expand one capability or close the change proposal
```

## 5. Incremental Production Release Model

A release milestone is defined by what users can newly see, understand, or do.

Technical work such as tables, SQL, synchronization, APIs, migrations, and tests is recorded as necessary foundation under that user-visible milestone.

Each capability release must declare:

1. user promise;
2. first intended users;
3. exact source of truth;
4. end-to-end user flow;
5. production boundary;
6. explicit non-scope;
7. success, empty, error, and not-found behavior;
8. validation evidence;
9. rollback path;
10. observation and expansion gate.

A capability can be production-ready for a narrow scenario even when the wider product remains incomplete. The release must not imply unsupported breadth.

## 6. Capability Gates

### Gate A — Defined

- user problem and promise are clear;
- source data and business authority are identified;
- scope, non-scope, first users, and review path are explicit.

### Gate B — End-to-end working

- source-to-user path works in development;
- success, empty, and failure behavior exist;
- no placeholder or fabricated production information is shown.

### Gate C — Small-scale production ready

- data and business meaning are validated;
- authentication and company scope are correct;
- database, API, and browser behavior are proven;
- migration and rollback are known;
- limitations are documented and visible where relevant.

### Gate D — User validated

- intended users understand the information;
- the next action is clear;
- the result is trusted for the stated purpose;
- no material user-facing defect blocks use.

### Gate E — Ready to expand

- no critical trust, access, or usability defect remains;
- production observation supports the next capability;
- the existing production boundary remains protected.

## 7. Approval Matrix

| Change | Process Owner | Data Health Owner | VP Operations | Technical Owner |
| --- | --- | --- | --- | --- |
| Wording only | Review | Informed | Approve according to document rule | Not required |
| Dashboard false positive | Confirm business intent | Approve rule correction | Informed unless business meaning changes | Implement |
| New anomaly rule | Confirm | Review/coordinate | Approve Critical/High or policy change | Implement |
| New user-visible capability | Confirm operational value | Verify data/evidence readiness | Approve policy or authority change | Implement and declare boundary |
| New process or approval | Review | Assess data impact | Approve | Implement after approval |
| SOP publication | Review | Verify rule linkage | Final approval | Confirm release compatibility |

## 8. Capability Release Gate

A bounded capability cannot be marked `Small-scale production ready` until:

1. the user promise and first users are identified;
2. the production boundary and non-scope are explicit;
3. source models, fields, company filters, SOP references, and Rule IDs are documented;
4. normal, invalid, cancelled, partial, missing-data, and accepted-exception cases relevant to the capability pass;
5. sample results reconcile to Odoo or the approved development snapshot;
6. authentication and company isolation are validated;
7. the user can understand the message and reach the correct source document or next action;
8. loading, empty, error, and not-found behavior are honest;
9. changelog or release notes describe user impact and limitations;
10. deployment and rollback paths exist;
11. an observation plan is defined.

This gate is capability-specific. Unsupported modules, rules, or process nodes do not block release when they are outside the declared boundary and are not presented as implemented.

## 9. Joint Publication Gate

A joint SOP/rule/dashboard release cannot be marked `Published` until:

1. SOP section and version are identified;
2. Rule ID and version are identified;
3. process owner has reviewed the business meaning;
4. VP Operations has approved business-rule changes;
5. source models/fields and company filters are documented;
6. valid, invalid, cancelled, partial, and accepted-exception tests pass;
7. sample results are reconciled to Odoo;
8. changelog describes impact;
9. rollback path exists for technical changes;
10. dashboard displays the implemented versions when required.

## 10. AI Guardrails

AI may:

- summarize closed tickets;
- cluster recurring anomaly patterns;
- compare ticket resolution to current SOP;
- generate a proposed before/after SOP change;
- identify impacted Rule IDs and test cases;
- draft user promises, production boundaries, release notes, and review checklists;
- propose the next bounded capability based on observed user evidence.

AI may not:

- establish physical truth;
- close tickets;
- change process ownership or approval authority;
- approve an accepted exception;
- alter production rules without human approval;
- publish an SOP version automatically;
- broaden a production boundary without owner approval;
- describe backend completion as user-ready when the source-to-user path is incomplete.

## 11. Drift Detection

The Control Tower should detect four kinds of drift:

1. **SOP Drift**: approved process changed but SOP did not.
2. **Rule Drift**: SOP changed but dashboard still uses old logic.
3. **Data Drift**: field/model meaning changed or sync is stale.
4. **Operational Drift**: users repeatedly follow a different flow.

Each dashboard release header must show, when relevant to the released capability:

```text
Implemented SOP Version
Implemented Rule Version
Data Contract Version
Capability Release and Boundary
Data Last Refreshed
Rule Last Tested
```

## 12. Ticket-to-Knowledge Classification

After resolution, every ticket is classified as one of:

- `USER_TRAINING`;
- `DATA_CORRECTION`;
- `PROCESS_CLARIFICATION`;
- `SOP_CHANGE_REQUIRED`;
- `DASHBOARD_RULE_FIX`;
- `SYSTEM_CONFIGURATION_FIX`;
- `DEVELOPMENT_REQUIRED`;
- `ACCEPTED_EXCEPTION`;
- `NO_CHANGE`.

Only `SOP_CHANGE_REQUIRED` and approved `PROCESS_CLARIFICATION` automatically enter the SOP Change Proposal queue. “Automatically” means automatic draft creation, not automatic approval or publication.

User observation may create a new capability proposal, but it does not automatically authorize a business-rule or production-boundary change.

## 13. Ownership Requirement

The organization must formally appoint:

- product/capability owner;
- Data Health Owner / coordinator;
- backup coordinator;
- process owner per node;
- technical dashboard owner;
- SOP approver;
- document publisher/controller.

Until formal appointment, role labels are used and no personal name is hard-coded in rules or SOP documents.
