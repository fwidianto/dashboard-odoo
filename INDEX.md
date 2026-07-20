# Documentation Index

This index lists the documentation cleanup locations created for the Odoo Analytics project.

## Root Documentation

| Document | Location | Notes |
| --- | --- | --- |
| Project README | `README.md` | Root project overview and documentation structure. |
| Changelog | `CHANGELOG.md` | Project documentation cleanup entry. |
| Documentation Index | `INDEX.md` | This file. |
| ChatGPT Handoff Report | `docs/CHATGPT_HANDOFF_REPORT.md` | Kept at this path by project convention for ChatGPT review handoffs. |

## 01 Project Management

| Document | New Location |
| --- | --- |
| Migration Guide | `docs/01_Project_Management/MIGRATION_GUIDE.md` |
| Next Data Model Steps | `docs/01_Project_Management/NEXT_DATA_MODEL_STEPS.md` |

## 02 Architecture

| Document | New Location |
| --- | --- |
| Analytics Architecture | `docs/02_Architecture/analytics_architecture.md` |
| Data Layer | `docs/02_Architecture/DATA_LAYER.md` |
| Final Architecture | `docs/02_Architecture/FINAL_ARCHITECTURE.md` |

## 03 Data Model

| Document | New Location |
| --- | --- |
| Data Catalog | `docs/03_Data_Model/data_catalog.md` |
| Odoo Field Mapping | `docs/03_Data_Model/ODOO_FIELD_MAPPING.md` |
| Schema Evolution | `docs/03_Data_Model/SCHEMA_EVOLUTION.md` |
| Table Audit | `docs/03_Data_Model/TABLE_AUDIT.md` |

## 04 Business Rules

| Document | New Location |
| --- | --- |
| Business Flow | `docs/04_Business_Rules/BUSINESS_FLOW.md` |
| Data Truth Layer Review | `docs/04_Business_Rules/DATA_TRUTH_LAYER_REVIEW.md` |
| Flow Implementation Gap | `docs/04_Business_Rules/FLOW_IMPLEMENTATION_GAP.md` |

## 05 Dashboards

| Document | New Location |
| --- | --- |
| Dashboard Business Review | `docs/05_Dashboards/DASHBOARD_BUSINESS_REVIEW.md` |
| Dashboard Data Contract | `docs/05_Dashboards/DASHBOARD_DATA_CONTRACT.md` |
| Internal Order Dashboard Page Design | `docs/05_Dashboards/DASHBOARD_PAGE_1_INTERNAL_ORDER_TRACEABILITY.md` |
| Sales Order Dashboard Concept | `docs/05_Dashboards/SALES_ORDER_DASHBOARD_CONCEPT.md` |
| Sales Order Traceability Architecture | `docs/05_Dashboards/SALES_ORDER_TRACEABILITY_ARCHITECTURE.md` |
| Odoo Protocol Control Tower Concept | `docs/05_Dashboards/ODOO_PROTOCOL_CONTROL_TOWER_CONCEPT.md` |

## 06 Investigations

| Document | New Location |
| --- | --- |
| Data Quality Investigation | `docs/06_Investigations/DATA_QUALITY_INVESTIGATION.md` |
| Internal Order Traceability Investigation | `docs/06_Investigations/INTERNAL_ORDER_TRACEABILITY_INVESTIGATION.md` |
| New Field Check | `docs/06_Investigations/NEW_FIELD_CHECK.md` |
| Nullable Fix Report | `docs/06_Investigations/nullable_fix_report.md` |

## 07 Deliverables

| Document | New Location |
| --- | --- |
| V1 Traceability Milestone | `docs/07_Deliverables/MILESTONE_V1_TRACEABILITY_COMPLETE.md` |

## 08 Control Tower

| Document | Location | Purpose |
| --- | --- | --- |
| Process Node Register | `docs/08_Control_Tower/PROCESS_NODE_REGISTER.md` | Defines the official end-to-end process stages, owners, entry/exit conditions, and flow branches. |
| Canonical Status Model | `docs/08_Control_Tower/PROCESS_STATUS_MODEL.md` | Defines consistent cross-module status semantics and precedence. |
| Rule Registry v1 | `docs/08_Control_Tower/RULE_REGISTRY_V1.md` | Links SOP rules to data checks, severity, owner, action, and implementation readiness. |
| Data Readiness Matrix | `docs/08_Control_Tower/DATA_READINESS_MATRIX.md` | Assesses current data and dashboard readiness for every process stage. |
| MVP Control Tower Specification | `docs/08_Control_Tower/MVP_CONTROL_TOWER_SPEC.md` | Defines page behavior, API contracts, data views, scope, and acceptance criteria. |
| Governance and Versioning | `docs/08_Control_Tower/GOVERNANCE_AND_VERSIONING.md` | Controls synchronized SOP, dashboard, rule, ticket, and AI-assisted change releases. |
| Phase 0 Decision Register | `docs/08_Control_Tower/PHASE_0_DECISION_REGISTER.md` | Tracks provisional decisions and questions requiring human confirmation. |
| Machine-readable Contract | `config/control_tower.yaml` | Initial configuration for nodes, statuses, roots, versions, and API contracts. |

## 99 Unsorted

No documents were placed in `docs/99_Unsorted/` during this cleanup.
