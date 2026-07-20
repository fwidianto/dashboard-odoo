# Decision-to-Data-Contract Map v2

**Purpose:** translate each remaining stakeholder decision into explicit dashboard/data-contract consequences without implementing unresolved business assumptions.

| Decision ID | Area | Data-contract consequence after approval | Current safe behavior | Tests required |
| --- | --- | --- | --- | --- |
| `DEC-GOV-001` | Data Health Owner | populate `review_owner_role`, escalation owner, and default worklist assignment | owner remains configurable/null | owner assignment and fallback |
| `DEC-GOV-002` | Review cadence | add review cadence and due/overdue logic per severity | show age only; no overdue conclusion | date boundary/timezone/cadence |
| `DEC-GOV-003` | Structured Log Note | expose required-note completeness and note evidence references | link/count messages only | action with/without evidence |
| `DEC-GOV-004` | Reason codes | add canonical reason code and root-cause grouping | free-text/unknown reason | known/unknown/deprecated code |
| `DEC-GOV-005` | Reset/Unlock approval | add request/approval/completion/verification states | exposure detection only | approved/rejected/missing note |
| `DEC-ACC-001` | Fully Paid | define canonical `FULLY_PAID` rule from residual and reconciliation | traceability fields only | cash, non-cash, zero residual, conflict |
| `DEC-ACC-002` | Unreconciled payment | add `PAYMENT_REGISTERED_UNRECONCILED` | source conflict/needs review | posted payment without reconciliation |
| `DEC-ACC-003` | Partial payment | add `PARTIALLY_PAID` and outstanding balance/age | show residual and partial reconcile evidence | single/multiple partials |
| `DEC-ACC-004` | Adjustment settlement | separate cash settlement and non-cash adjustment | show journal/reconcile type without final label | credit note, write-off, journal settlement |
| `DEC-ACC-005` | DP allocation | add explicit DP-to-final/SO allocation records | show linked invoices only | one/many DP and final invoices |
| `DEC-ACC-006` | Overpayment | add customer-credit/overpayment status and amount | source conflict/needs review | residual credit and unapplied payment |
| `DEC-ACC-007` | Payment date | select primary management date and retain alternate dates | expose all dates with no preferred date | posting vs reconciliation date |
| `DEC-IO-001` | IO denominator | define `io_requested_qty` authority field | diagnostic candidate fields only | line/header/missing qty |
| `DEC-IO-002` | Product matching | define product-match key/mapping version | exact product only or `DATA_EXCEPTION` | exact/family/mismatch |
| `DEC-IO-003` | UoM conversion | define conversion source, rounding, and normalized quantity | no unapproved conversion | exact/convertible/unconvertible |
| `DEC-IO-004` | Multi-IO allocation | add allocation bridge with quantity per SO line and IO | retain `DATA_EXCEPTION` | one-to-one, one-to-many, over-allocation |
| `DEC-IO-005` | Parent-Child MO | add persistent genealogy relation and relation confidence | diagnostic grouping only | child before parent, missing link, multi-level |
| `DEC-IO-006` | Over-production tolerance | add tolerance and severity policy | positive variance is review signal only | inside/outside tolerance |
| `DEC-PRC-001` | Reset PO exposure | define approved-exposure status and closure requirement | detect open downstream | receipt/bill/backorder combinations |
| `DEC-PRC-002` | Cancel PO procedure | define canonical blocked/failed/resolved states | final-state verification and exposure | error unchanged/state changed |
| `DEC-PRC-003` | Backorder owner | assign next-action owner by procurement vs picking decision | multi-owner/needs review | keep/cancel/complete backorder |
| `DEC-PRC-004` | Receipt replacement | add replacement/closure relationship and outcome | show PO open after Receipt cancel | replacement/no replacement/PO cancel |
| `DEC-PRC-005` | Service evidence | add accepted evidence types and completeness | manual evidence pending | BAP/BAST/requester confirmation |
| `DEC-SAL-001` | SO cancellation | define allowed historical downstream and required open-document disposition | exposure classifications only | done/open/posted/partial combinations |
| `DEC-SAL-002` | Delivery replacement | add replacement delivery linkage and approval evidence | show cancelled delivery and parent SO separately | recreate/close/backorder |
| `DEC-SAL-003` | Distribusi JO evidence | future optional manual/Odoo evidence model | manual milestone; not inferred | manual/missing/future mapped |
| `DEC-SAL-004` | Customer evidence | add required evidence completeness rule | Customer Reference + PO Date for 2026+ | attachment optional/mandatory outcomes |

## Contract Versioning Rule

When a decision is approved:

1. update Decision Register status;
2. increment affected rule/data-contract version;
3. update SOP and exception definition;
4. add regression fixtures;
5. reconcile sample records;
6. only then enable the business-facing label or KPI.
