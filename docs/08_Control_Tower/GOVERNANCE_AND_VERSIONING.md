# Governance and Versioning — Protocol, Dashboard, Ticket, and AI

Status: Phase 0 Draft v1

## 1. Core Principle

Odoo Protocol is the approved business contract. Dashboard Odoo is the monitoring and evidence layer. Ticketing stores operational learning. AI may analyze and propose, but human owners approve business changes.

## 2. Version Objects

The system maintains separate but linked versions:

| Object | Example | Owner |
| --- | --- | --- |
| SOP Version | `SOP-ODOO-1.2` | VP Operations / document controller |
| Rule Registry Version | `RULES-1.2` | Data Health Owner + process owners |
| Dashboard Release | `CT-0.3.0` | Dashboard technical owner |
| Data Contract Version | `DATA-1.1` | Data/technical owner |
| Ticket Resolution | `TKT-2026-0042` | Ticket coordinator / process owner |
| SOP Change Proposal | `SCP-2026-0010` | AI draft; human reviewer/approver |

Versions do not have to share identical numbers, but every production dashboard release must declare the SOP and Rule Registry versions it implements.

## 3. Change Types

### A. SOP-only Clarification

No data logic changes. Example: improve wording or screenshot.

### B. Rule-only Technical Correction

Business rule unchanged; query or linkage fixed after false positive.

### C. Joint Business Change

SOP, rule logic, test cases, and dashboard all change together.

### D. Data Contract Change

Source field/model or transformation changes while business meaning remains stable.

## 4. Standard Change Flow

```text
Ticket / anomaly / management decision
→ factual investigation
→ root cause and resolution verified by human
→ SOP impact classification
→ AI creates SOP Change Proposal when relevant
→ process owner review
→ Data Health Owner checks dashboard impact
→ VP Operations approves business change
→ update SOP draft and Rule Registry
→ update SQL/API/UI when required
→ regression test
→ publish linked versions
→ close change proposal
```

## 5. Approval Matrix

| Change | Process Owner | Data Health Owner | VP Operations | Technical Owner |
| --- | --- | --- | --- | --- |
| Wording only | Review | Informed | Approve according to document rule | Not required |
| Dashboard false positive | Confirm business intent | Approve rule correction | Informed unless business meaning changes | Implement |
| New anomaly rule | Confirm | Review/coordinate | Approve Critical/High or policy change | Implement |
| New process or approval | Review | Assess data impact | Approve | Implement after approval |
| SOP publication | Review | Verify rule linkage | Final approval | Confirm release compatibility |

## 6. Release Gate

A joint release cannot be marked `Published` until:

1. SOP section and version are identified;
2. Rule ID and version are identified;
3. process owner has reviewed the business meaning;
4. VP Operations has approved business-rule changes;
5. source models/fields and company filters are documented;
6. valid, invalid, cancelled, partial, and accepted-exception tests pass;
7. sample results are reconciled to Odoo;
8. changelog describes impact;
9. rollback path exists for technical changes;
10. dashboard displays the implemented versions.

## 7. AI Guardrails

AI may:

- summarize closed tickets;
- cluster recurring anomaly patterns;
- compare ticket resolution to current SOP;
- generate a proposed before/after SOP change;
- identify impacted Rule IDs and test cases;
- draft changelog and review checklist.

AI may not:

- establish physical truth;
- close tickets;
- change process ownership or approval authority;
- approve an accepted exception;
- alter production rules without human approval;
- publish an SOP version automatically.

## 8. Drift Detection

The Control Tower should detect four kinds of drift:

1. **SOP Drift**: approved process changed but SOP did not.
2. **Rule Drift**: SOP changed but dashboard still uses old logic.
3. **Data Drift**: field/model meaning changed or sync is stale.
4. **Operational Drift**: users repeatedly follow a different flow.

Each dashboard release header must show:

```text
Implemented SOP Version
Implemented Rule Version
Data Contract Version
Data Last Refreshed
Rule Last Tested
```

## 9. Ticket-to-Knowledge Classification

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

## 10. Ownership Requirement

The organization must formally appoint:

- Data Health Owner / coordinator;
- backup coordinator;
- process owner per node;
- technical dashboard owner;
- SOP approver;
- document publisher/controller.

Until formal appointment, role labels are used and no personal name is hard-coded in rules or SOP documents.
