# Documentation Authority Matrix

**Classification date:** 2026-07-20  
**Purpose:** define which documents control current business, technical, and implementation decisions.

## Categories

- `AUTHORITATIVE` — current source of truth.
- `IMPLEMENTATION_AUTHORITY` — approved technical specification for an implemented or explicitly approved scope.
- `REFERENCE` — useful supporting context.
- `INVESTIGATION` — evidence/discovery; conclusions should feed authoritative documents.
- `HISTORICAL` — completed milestone or superseded record.
- `WORKING_NOTE` — draft or planning material.
- `DEPRECATED` — must not be used for current decisions except historical review.

## Current Authority Order

### Business and SOP authority

1. `docs/09_Odoo18_Validation/SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md`
2. `docs/09_Odoo18_Validation/CONFIRMED_SOP_DECISIONS_2026-07-20.md`
3. `docs/04_Business_Rules/BUSINESS_FLOW.md`
4. `docs/09_Odoo18_Validation/DATA_HEALTH_RULE_CATALOG_V2.md`

Earlier business-flow, glossary, or dashboard assumptions are superseded where they conflict with these documents.

### Runtime and technical validation authority

1. `docs/09_Odoo18_Validation/FULL_RUNTIME_CANCELLATION_AND_OUTSTANDING_MATRIX.md`
2. `docs/09_Odoo18_Validation/FINAL_SOP_SYSTEM_CLOSURE_AUDIT.md`
3. Odoo 18 automation/server-action audit documents in `docs/09_Odoo18_Validation/`
4. validated scripts under `scripts/odoo_runtime_validation/`

### Implementation planning authority

1. `docs/09_Odoo18_Validation/DASHBOARD_IMPLEMENTATION_BACKLOG_V2.md`
2. `docs/08_Control_Tower/` specifications where they do not conflict with the final alignment
3. `config/control_tower.yaml` after revalidation against final rules

The backlog is preparation only. It does not authorize production changes before stakeholder gates are closed.

## Document Classification

| Document | Category | Current use |
| --- | --- | --- |
| `docs/09_Odoo18_Validation/SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md` | AUTHORITATIVE | Final business/system alignment and implementation boundary. |
| `docs/09_Odoo18_Validation/CONFIRMED_SOP_DECISIONS_2026-07-20.md` | AUTHORITATIVE | Concise confirmed decision register. |
| `docs/04_Business_Rules/BUSINESS_FLOW.md` | AUTHORITATIVE | Current business glossary, flow, and data-contract principles. |
| `docs/09_Odoo18_Validation/DATA_HEALTH_RULE_CATALOG_V2.md` | AUTHORITATIVE | Rule contract and readiness classification. |
| `docs/09_Odoo18_Validation/DASHBOARD_IMPLEMENTATION_BACKLOG_V2.md` | WORKING_NOTE | Ordered post-approval implementation plan. |
| `docs/09_Odoo18_Validation/FULL_RUNTIME_CANCELLATION_AND_OUTSTANDING_MATRIX.md` | INVESTIGATION | Controlled runtime evidence. |
| `docs/09_Odoo18_Validation/FINAL_SOP_SYSTEM_CLOSURE_AUDIT.md` | INVESTIGATION | Final read-only counts and classifications. |
| `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md` | IMPLEMENTATION_AUTHORITY | Current implemented V1 logic; must be revised where final alignment differs. |
| `docs/03_Data_Model/data_catalog.md` | AUTHORITATIVE | Data catalog and table/field reference, subject to later Odoo 18 audit corrections. |
| `docs/03_Data_Model/ODOO_FIELD_MAPPING.md` | REFERENCE | Field mapping appendix. |
| `docs/02_Architecture/FINAL_ARCHITECTURE.md` | AUTHORITATIVE | Stable platform architecture until consolidated. |
| `docs/02_Architecture/analytics_architecture.md` | REFERENCE | Supporting analytics architecture. |
| `docs/02_Architecture/DATA_LAYER.md` | REFERENCE | Supporting data-layer concepts. |
| `docs/05_Dashboards/DASHBOARD_DATA_CONTRACT.md` | IMPLEMENTATION_AUTHORITY | Existing V1 IO dashboard contract; pending v2 replacement. |
| `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md` | IMPLEMENTATION_AUTHORITY | Existing SO dashboard design; pending v2 relation/source correction. |
| `docs/05_Dashboards/DASHBOARD_BUSINESS_REVIEW.md` | REFERENCE | UI/business usability decisions. |
| `docs/05_Dashboards/JOB_ORDER_COST_REKAP_REPORT.md` | IMPLEMENTATION_AUTHORITY | Report business scope. |
| `docs/05_Dashboards/JOB_ORDER_COST_REKAP_SQL_DESIGN.md` | IMPLEMENTATION_AUTHORITY | Report SQL design. |
| `docs/08_Control_Tower/*` | WORKING_NOTE / REFERENCE | Control Tower preparation; must align to final rule vocabulary and gates. |
| `docs/CHATGPT_HANDOFF_REPORT.md` | REFERENCE | Historical handoff/context; no longer primary business authority. |
| `docs/04_Business_Rules/FLOW_IMPLEMENTATION_GAP.md` | HISTORICAL | Earlier gap analysis superseded by final validation. |
| `docs/03_Data_Model/TABLE_AUDIT.md` | HISTORICAL | Early table audit; use later validated evidence. |
| `docs/06_Investigations/*` | INVESTIGATION | Preserve evidence; merge conclusions before archiving. |
| `docs/07_Deliverables/MILESTONE_V1_TRACEABILITY_COMPLETE.md` | HISTORICAL | V1 milestone only. |
| `docs/01_Project_Management/NEXT_DATA_MODEL_STEPS.md` | HISTORICAL / WORKING_NOTE | Earlier plan, partially completed and superseded by v2 backlog. |

## Known Supersessions

| Older statement/document | Current authority |
| --- | --- |
| Distribusi JO occurs only after SO Confirm | Final alignment: outside Odoo and may occur while SO is Draft. |
| IO-based SO creates no new MO | Final alignment: MO may be created then auto-cancelled as `MO_SUPPRESSED_BY_IO`. |
| SO source can be classified at header using IO precedence | Final alignment: classify per line; header may be `MIXED_SOURCE`. |
| Reset to Draft cleans/cancels downstream | Runtime evidence: downstream may remain active and linked. |
| Sales copied paid field represents payment truth | Final alignment: residual and reconciliation are accounting truth. |
| Display name/text reference is sufficient for joins | Final alignment: native IDs and relation tables take precedence. |

## Implementation Gate

No SQL, API, UI, or production configuration change should be treated as approved until:

1. SOP Draft v2 is reviewed and approved;
2. Accounting taxonomy is approved;
3. IO product/UoM and multi-IO allocation rules are approved;
4. Data Health owner and cadence are assigned;
5. acceptance criteria and reconciliation tests are defined.

After the gate, implementation follows `DASHBOARD_IMPLEMENTATION_BACKLOG_V2.md`, beginning with native relationship extraction rather than frontend redesign.

## Future Consolidation

A simplified structure remains useful after v2 implementation:

```text
docs/
├── ARCHITECTURE.md
├── BUSINESS_RULES.md
├── DATA_MODEL.md
├── DASHBOARDS.md
├── PROJECT_STATUS.md
└── archive/
```

Consolidation must preserve validation evidence and revision history rather than deleting it.
