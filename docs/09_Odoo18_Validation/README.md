# Odoo 18 Validation Authority

Last updated: 2026-07-20

This folder contains the validated technical and SOP-alignment baseline for the Odoo 18 dashboard project.

## Current Authority

1. `SOP_SYSTEM_ALIGNMENT_MATRIX_FINAL.md` — authoritative business/system alignment baseline for SOP Draft v2 and dashboard data-contract planning.
2. `CONFIRMED_SOP_DECISIONS_2026-07-20.md` — concise confirmed-decision register and approved exception vocabulary.

The alignment baseline supersedes earlier working assumptions wherever they conflict.

## Implementation Boundary

The confirmed decisions may be used to:

- update SOP Draft v2;
- define the future extraction/data contract;
- prepare exception and Control Tower rules;
- prioritize dashboard backlog.

They do not yet authorize immediate production configuration, SQL, API, or UI changes. Implementation begins after SOP Draft v2 and the remaining Accounting/IO allocation decisions are approved.

## Required Future Data-Contract Changes

- preserve native Odoo IDs alongside display values;
- extract the SO–IO many-to-many relation directly;
- use stable company ID;
- use approval header status for validity;
- distinguish mixed fulfilment per line;
- add stock picking/move/backorder evidence;
- add invoice, residual, and reconciliation evidence before payment implementation;
- expose cancellation/reset outstanding exceptions;
- treat automation-derived helper fields as secondary evidence.
