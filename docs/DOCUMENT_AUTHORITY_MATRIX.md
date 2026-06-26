# Documentation Authority Matrix

Classification date: 2026-06-24

Scope: documentation classification only. No existing documentation files were moved, deleted, or modified.

## Category Definitions

- AUTHORITATIVE: Current source of truth or strongest candidate source of truth.
- REFERENCE: Useful supporting documentation, but not the primary decision source.
- HISTORICAL: Completed milestone, older audit, or superseded planning record kept for traceability.
- DEPRECATED: Should not be used for current decisions except as history.
- INVESTIGATION: Discovery/debugging record; conclusions should be merged into source-of-truth docs.
- WORKING_NOTE: Planning or interim notes that may still contain useful next steps.

## Matrix

| Document | Category | Purpose | Keep? | Merge Into | Notes |
|---|---|---|---|---|---|
| `docs/CHATGPT_HANDOFF_REPORT.md` | AUTHORITATIVE | Current project status, latest decisions, validation snapshot, and handoff context. | Yes | Future `PROJECT_STATUS.md` | Treat as the active operational status source until a consolidated project-status doc exists. |
| `docs/01_Project_Management/MIGRATION_GUIDE.md` | REFERENCE | Migration/setup guidance for moving or running the project. | Yes | Future `PROJECT_STATUS.md` or `ARCHITECTURE.md` | Useful implementation reference; not a business-rule source. |
| `docs/01_Project_Management/NEXT_DATA_MODEL_STEPS.md` | WORKING_NOTE | Earlier recommended SQL views, implementation order, and dashboard sequencing. | Yes | Future `PROJECT_STATUS.md` and `DATA_MODEL.md` | Some items are completed or superseded by later Data Truth Layer and dashboard work. |
| `docs/02_Architecture/FINAL_ARCHITECTURE.md` | AUTHORITATIVE | Main system/platform architecture reference. | Yes | Future `ARCHITECTURE.md` | Best candidate base for the architecture source of truth. |
| `docs/02_Architecture/analytics_architecture.md` | REFERENCE | Analytics architecture context and design notes. | Yes | Future `ARCHITECTURE.md` | Merge useful concepts into the architecture source of truth. |
| `docs/02_Architecture/DATA_LAYER.md` | REFERENCE | Data layer concept and structure notes. | Yes | Future `ARCHITECTURE.md` or `DATA_MODEL.md` | Overlaps with Data Truth Layer and data model documentation. |
| `docs/03_Data_Model/data_catalog.md` | AUTHORITATIVE | Data catalog and table/field reference. | Yes | Future `DATA_MODEL.md` | Best candidate base for the data model source of truth. |
| `docs/03_Data_Model/ODOO_FIELD_MAPPING.md` | REFERENCE | Odoo field mapping reference. | Yes | Future `DATA_MODEL.md` | Keep as a mapping appendix or merged table. |
| `docs/03_Data_Model/SCHEMA_EVOLUTION.md` | HISTORICAL | Schema and model evolution notes. | Yes | Future `DATA_MODEL.md` appendix | Useful chronology, not current decision authority. |
| `docs/03_Data_Model/TABLE_AUDIT.md` | HISTORICAL | Initial table audit and relationship discovery. | Yes | Future `DATA_MODEL.md` after verification | Superseded by later Data Truth Layer corrections, especially IO bridge and accounting mapping. |
| `docs/04_Business_Rules/BUSINESS_FLOW.md` | AUTHORITATIVE | Business glossary, confirmed flows, and target operational model. | Yes | Future `BUSINESS_RULES.md` | Candidate business-rule source of truth; should be cleaned and merged with implemented rules. |
| `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md` | AUTHORITATIVE | Implemented Data Truth Layer rules, classifications, and known limitations. | Yes | Future `BUSINESS_RULES.md` and `DATA_MODEL.md` | Strongest source for implemented traceability logic. |
| `docs/04_Business_Rules/FLOW_IMPLEMENTATION_GAP.md` | HISTORICAL | Earlier implementation gap analysis. | Yes | Future `BUSINESS_RULES.md` for unresolved gaps only | Mostly superseded by Data Truth Layer and dashboard implementation docs. |
| `docs/05_Dashboards/DASHBOARD_BUSINESS_REVIEW.md` | REFERENCE | Business usability review and simplification decisions for the IO dashboard. | Yes | Future `DASHBOARDS.md` | Useful decision log for dashboard layout and column placement. |
| `docs/05_Dashboards/DASHBOARD_DATA_CONTRACT.md` | AUTHORITATIVE | V1 Internal Order dashboard field contract. | Yes | Future `DASHBOARDS.md` | Authoritative for IO dashboard data semantics, though UI column placement was later simplified. |
| `docs/05_Dashboards/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md` | REFERENCE | Internal Order dashboard page design. | Yes | Future `DASHBOARDS.md` | Partially superseded by business review and implemented UI simplification. |
| `docs/05_Dashboards/SALES_ORDER_DASHBOARD_CONCEPT.md` | HISTORICAL | Earlier Sales Order dashboard concept. | Yes | Future `DASHBOARDS.md` if useful | Superseded by `SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`. |
| `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md` | AUTHORITATIVE | Phase 2A Sales Order dashboard architecture and implementation basis. | Yes | Future `DASHBOARDS.md` | Current source of truth for Sales Order dashboard requirements and formulas. |
| `docs/05_Dashboards/JOB_ORDER_COST_REKAP_REPORT.md` | AUTHORITATIVE | Job Order Cost Rekap business/report specification. | Yes | Future `DASHBOARDS.md` | Source of truth for report business meaning, Phase 1 decisions, scope, non-goals, and open decisions. |
| `docs/05_Dashboards/JOB_ORDER_COST_REKAP_SQL_DESIGN.md` | AUTHORITATIVE | Phase 1 SQL design for Job Order Cost Rekap implementation. | Yes | Future `DASHBOARDS.md` | Technical design for source mapping, formulas, validation queries, and SQL implementation risks. |
| `docs/06_Investigations/DATA_QUALITY_INVESTIGATION.md` | INVESTIGATION | Data quality findings and rule corrections such as JO normalization and cancelled-record handling. | Yes | Archive after conclusions are merged | Investigation conclusions should be preserved in source-of-truth docs. |
| `docs/06_Investigations/INTERNAL_ORDER_TRACEABILITY_INVESTIGATION.md` | INVESTIGATION | Internal Order bridge and approval request investigation. | Yes | Archive after conclusions are merged | Conclusions are implemented in current IO traceability logic. |
| `docs/06_Investigations/NEW_FIELD_CHECK.md` | INVESTIGATION | Confirmation of newly synced fields and stock picking type interpretation. | Yes | Archive after conclusions are merged | Field discoveries should be summarized in the data model source of truth. |
| `docs/06_Investigations/nullable_fix_report.md` | INVESTIGATION | Report for nullable-field fixes and related implementation notes. | Yes | Archive or data model appendix | Keep for audit trail; not a current business-rule source. |
| `docs/07_Deliverables/MILESTONE_V1_TRACEABILITY_COMPLETE.md` | HISTORICAL | Official V1 traceability completion checkpoint. | Yes | Future `PROJECT_STATUS.md` | Important milestone record, but current status is now newer than V1. |

## Duplicate Documents

1. `docs/05_Dashboards/SALES_ORDER_DASHBOARD_CONCEPT.md` and `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md` overlap on Sales Order dashboard purpose, KPIs, filters, and drill-down design. The architecture document is newer and more authoritative.
2. `docs/05_Dashboards/DASHBOARD_DATA_CONTRACT.md`, `docs/05_Dashboards/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md`, and `docs/05_Dashboards/DASHBOARD_BUSINESS_REVIEW.md` overlap on Internal Order dashboard columns, KPIs, and layout decisions.
3. `docs/04_Business_Rules/BUSINESS_FLOW.md`, `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md`, and `docs/CHATGPT_HANDOFF_REPORT.md` overlap on the SO / JO / IO / RKB / ROP glossary and traceability rules.
4. `docs/03_Data_Model/TABLE_AUDIT.md`, `docs/03_Data_Model/data_catalog.md`, and `docs/03_Data_Model/ODOO_FIELD_MAPPING.md` overlap on table and field descriptions.
5. `docs/02_Architecture/FINAL_ARCHITECTURE.md`, `docs/02_Architecture/analytics_architecture.md`, and `docs/02_Architecture/DATA_LAYER.md` overlap on architecture and data layer responsibilities.

## Documents Superseded By Newer Documents

| Superseded Document | Newer / Stronger Document | Reason |
|---|---|---|
| `docs/05_Dashboards/SALES_ORDER_DASHBOARD_CONCEPT.md` | `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md` | Phase 2A architecture includes approved formulas, routes, dashboard requirements, and implementation summary. |
| `docs/04_Business_Rules/FLOW_IMPLEMENTATION_GAP.md` | `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md` | Later Data Truth Layer work resolved or reframed many earlier gaps. |
| `docs/03_Data_Model/TABLE_AUDIT.md` | `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md` and investigation docs | Early audit contains assumptions later corrected, especially accounting-to-SO and IO bridge behavior. |
| `docs/01_Project_Management/NEXT_DATA_MODEL_STEPS.md` | SQL/dashboard implementation docs and `docs/CHATGPT_HANDOFF_REPORT.md` | Several next steps have already been implemented. |
| `docs/05_Dashboards/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md` | `docs/05_Dashboards/DASHBOARD_BUSINESS_REVIEW.md` | Business review simplified the default table and moved some fields into diagnostics. |
| `docs/07_Deliverables/MILESTONE_V1_TRACEABILITY_COMPLETE.md` | `docs/CHATGPT_HANDOFF_REPORT.md` | Milestone remains valid history, but the handoff report reflects newer Phase 2A status. |

## Business-Rule Source-Of-Truth Candidates

These documents should feed a single future `BUSINESS_RULES.md`:

1. `docs/04_Business_Rules/BUSINESS_FLOW.md`
2. `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md`
3. Latest confirmed glossary and decisions from `docs/CHATGPT_HANDOFF_REPORT.md`
4. Sales Order source classification and status decisions from `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`

Recommended business-rule authority:

- `BUSINESS_FLOW.md` should define the business language and process meaning.
- `DATA_TRUTH_LAYER_REVIEW.md` should define how those rules are implemented in SQL/views.
- The future consolidated source should remove duplicate wording and keep one clean glossary.

## Architecture Source-Of-Truth Candidates

These documents should feed a single future `ARCHITECTURE.md`:

1. `docs/02_Architecture/FINAL_ARCHITECTURE.md`
2. `docs/02_Architecture/analytics_architecture.md`
3. `docs/02_Architecture/DATA_LAYER.md`
4. Current dashboard/API architecture details from `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`

Recommended architecture authority:

- Use `FINAL_ARCHITECTURE.md` as the base.
- Merge analytics/data layer details from the other architecture documents.
- Add current dashboard route/API notes only where they describe stable architecture.

## Investigation Documents That Can Be Archived

These can move to an archive later after their conclusions are merged into source-of-truth docs:

1. `docs/06_Investigations/DATA_QUALITY_INVESTIGATION.md`
2. `docs/06_Investigations/INTERNAL_ORDER_TRACEABILITY_INVESTIGATION.md`
3. `docs/06_Investigations/NEW_FIELD_CHECK.md`
4. `docs/06_Investigations/nullable_fix_report.md`

Additional historical archive candidates after verification:

1. `docs/03_Data_Model/TABLE_AUDIT.md`
2. `docs/04_Business_Rules/FLOW_IMPLEMENTATION_GAP.md`
3. `docs/01_Project_Management/NEXT_DATA_MODEL_STEPS.md`

## Proposed Simplified Future Documentation Structure

This is a proposal only. No consolidation was performed.

```text
docs/
├── ARCHITECTURE.md
├── BUSINESS_RULES.md
├── DATA_MODEL.md
├── DASHBOARDS.md
├── PROJECT_STATUS.md
└── archive/
    ├── historical/
    ├── investigations/
    └── working-notes/
```

### 1. Architecture Source Of Truth

Future file: `docs/ARCHITECTURE.md`

Merge from:

- `docs/02_Architecture/FINAL_ARCHITECTURE.md`
- `docs/02_Architecture/analytics_architecture.md`
- `docs/02_Architecture/DATA_LAYER.md`
- Stable route/API architecture from `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`

### 2. Business Rules Source Of Truth

Future file: `docs/BUSINESS_RULES.md`

Merge from:

- `docs/04_Business_Rules/BUSINESS_FLOW.md`
- `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md`
- Latest confirmed glossary from `docs/CHATGPT_HANDOFF_REPORT.md`
- Current Sales Order classification rules from `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`

### 3. Data Model Source Of Truth

Future file: `docs/DATA_MODEL.md`

Merge from:

- `docs/03_Data_Model/data_catalog.md`
- `docs/03_Data_Model/ODOO_FIELD_MAPPING.md`
- Verified content from `docs/03_Data_Model/TABLE_AUDIT.md`
- Relevant schema history from `docs/03_Data_Model/SCHEMA_EVOLUTION.md`
- Confirmed investigation outcomes from `docs/06_Investigations/NEW_FIELD_CHECK.md`

### 4. Dashboard Source Of Truth

Future file: `docs/DASHBOARDS.md`

Merge from:

- `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md`
- `docs/05_Dashboards/DASHBOARD_DATA_CONTRACT.md`
- `docs/05_Dashboards/DASHBOARD_BUSINESS_REVIEW.md`
- `docs/05_Dashboards/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md`

### 5. Project Status Source Of Truth

Future file: `docs/PROJECT_STATUS.md`

Merge from:

- `docs/CHATGPT_HANDOFF_REPORT.md`
- `docs/07_Deliverables/MILESTONE_V1_TRACEABILITY_COMPLETE.md`
- Unresolved items from `docs/01_Project_Management/NEXT_DATA_MODEL_STEPS.md`

