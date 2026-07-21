# Control Tower Frontend Experience Vision

**Status:** product/design direction — future frontend phase  
**Scope:** Control Tower Health dashboard  
**Relationship to backend:** implementation begins only after backend is declared `READY_FOR_UI`  
**Authority:** this document records the agreed design ideology. It is not a fixed wireframe and may be improved as long as the principles below are preserved.

## 1. Product Vision

The Control Tower frontend must feel like a **living operational command center**, not a conventional collection of static KPI cards and tables.

The experience should be:

- active;
- modern;
- visually attractive enough to keep on a dedicated display;
- continuously informative without requiring constant interaction;
- understandable by operational users who do not know the underlying SQL, Odoo models, or technical status codes;
- suitable for both passive monitoring and deep investigation.

Visual inspiration may come from interactive command interfaces such as Steam- or PlayStation-style system screens, game command centers, and live system maps. The interface must not imitate those products literally. Their value is the sense of motion, hierarchy, responsiveness, and a world that appears continuously active.

## 2. Core Ideology

The main screen should present business activity as a **live or animated process world**.

Examples of process journeys include:

```text
Quotation
→ Sales Order
→ Source Decision
→ Internal Order / Manufacturing / Stock / Purchase
→ Delivery
→ Invoice
→ Accounts Receivable
→ Payment
```

and:

```text
RKB / ROP / Internal Order
→ RFQ
→ Purchase Order
→ Receipt
→ Vendor Bill
→ Accounts Payable
→ Payment
```

The exact number of screens, sections, modes, or panels is deliberately not fixed. The final design may be split, combined, or improved as needed, provided it remains faithful to the following principle:

> The dashboard must look alive, remain interesting to observe, and make the health and movement of business processes understandable.

## 3. Primary Interaction Model

### Passive display

The dashboard should work on a dedicated display and continuously communicate:

- where business activity is flowing;
- which process areas are busy;
- where flow is slowing or accumulating;
- where confirmed exceptions exist;
- where human verification is needed;
- where evidence or data linkage is incomplete;
- when the underlying data was last refreshed.

A user should obtain useful situational awareness even without touching the screen.

### Hover

Hovering a process node, edge, or operational area should reveal a concise health summary, such as:

- active document count;
- validated count;
- need-action count;
- need-review count;
- data-linkage gaps;
- aging or duration;
- responsible owner;
- last refresh time;
- evidence confidence.

Hover information should remain concise and understandable within a few seconds.

### Click

Clicking a node or flow should open progressively deeper information, for example:

- process health detail;
- related SOP rules;
- exception worklist;
- top recurring issues;
- record-level journey;
- expected versus actual evidence;
- technical evidence when explicitly requested.

The interface should move from overview to evidence without losing the user's sense of position in the business flow.

## 4. Meaningful Animation

Animation is a product feature only when it represents real information. It must not be decorative noise.

Possible visual meanings include:

| Visual behavior | Operational meaning |
| --- | --- |
| Moving pulses or particles | Documents or aggregated activity moving through a process |
| Particle frequency | Transaction volume or throughput |
| Edge thickness | Active volume, queue size, or process load |
| Edge speed | Relative process velocity or duration |
| Slowing movement | Aging or bottleneck |
| Pulsing node | New activity or a state change |
| Warning glow | Confirmed action-required exception |
| Dashed or interrupted path | Missing or uncertain data linkage |
| Dimmed process | Low activity, stale data, or unavailable test coverage |
| Health overlay | Validated, action required, verification required, or data-evidence issue |

Every animation must have a legend, tooltip, or explainable metric behind it.

## 5. Operational Status Language

Technical backend statuses must be translated into user-facing meaning.

| Backend status | User-facing meaning |
| --- | --- |
| `VALIDATED` | Sesuai |
| `MISMATCH` | Perlu Tindakan |
| `PARTIAL_MATCH` | Perlu Verifikasi |
| `DATA_LINKAGE_GAP` | Bukti Data Belum Lengkap |
| `MANUAL_EVIDENCE_REQUIRED` | Perlu Bukti Manual |
| `VALID_EXCEPTION` | Pengecualian Disetujui |
| `NOT_TESTED` | Belum Dapat Diuji |

Confirmed operational exceptions must remain visually distinct from data-quality or evidence gaps. The frontend must not make an incomplete data relationship look like confirmed user error.

## 6. Progressive Information Depth

The design should support multiple levels of detail rather than attempting to display all records at once.

### System level

Shows the complete business flow, aggregated health, throughput, bottlenecks, and data freshness.

### Process level

Shows one functional flow in greater detail, such as sales-to-cash, procure-to-pay, manufacturing, or internal-order utilization.

### Record level

Shows the journey of a specific document using native relationships and record evidence.

Examples:

```text
SO/2026/0187
├── IO/2026/0042
│   └── MO/2026/0331
├── WH/OUT/2026/0834
└── INV/2026/0227
    └── AR Outstanding
```

The system must never attempt to render the full million-record snapshot as individual visual objects. Aggregation and level-of-detail are mandatory.

## 7. Explanation Before Technical Detail

For an exception, the primary presentation should be:

1. **Expected** — what the process or SOP requires;
2. **Actual** — what the system currently observes;
3. **Why it matters** — the operational consequence;
4. **Suggested review** — what the responsible user should check;
5. **Evidence confidence** — how strong the underlying relationship is.

Raw models, native IDs, source fields, JSON evidence, and relationship types should be available under a secondary technical-evidence layer. They must not be the default language shown to operational users.

## 8. Honest Live-State Communication

Visual motion must not misrepresent data freshness.

The interface must clearly label its operating mode, for example:

- `SNAPSHOT MODE — Data as of 10:42`;
- `NEAR LIVE — Updated 18 seconds ago`;
- `LIVE EVENT MODE` only when real event delivery exists.

Animated snapshot data may look active, but it must never be presented as real-time when the backend is not updating in real time.

## 9. Potential Experience Modes

The final product may use one or more modes. The names and count are not fixed.

Possible modes include:

- **Live Flow:** emphasizes activity, throughput, queues, and movement;
- **Health:** emphasizes exceptions, evidence confidence, aging, and ownership;
- **Investigation:** isolates a selected document and its journey;
- **Display:** optimized for continuous passive monitoring on a dedicated screen;
- **Executive:** simplified operational health and high-priority risks;
- **Operational:** actionable worklist and process detail;
- **Data Quality:** linkage confidence, freshness, and diagnostic evidence.

The product team may combine or revise these modes as long as the living command-center ideology remains intact.

## 10. Non-Negotiable Design Principles

1. The frontend must feel active and continuously informative.
2. Motion must represent data, health, volume, aging, or uncertainty.
3. The interface must be valuable as a dedicated always-on display.
4. Hover provides immediate health context.
5. Click provides progressively deeper process and record evidence.
6. Operational meaning must be understandable without technical Odoo knowledge.
7. Confirmed process problems, review signals, and data-linkage gaps must remain visually distinct.
8. The interface must never claim real-time freshness without real-time delivery.
9. Large data volumes must be aggregated through level-of-detail.
10. Visual creativity is encouraged; a conventional dashboard layout is not required.
11. Readability, performance, accessibility, and evidence traceability must not be sacrificed for spectacle.
12. The final design may improvise on page count and layout but must preserve this ideology.

## 11. Initial Product Success Test

The first frontend version succeeds when a user can:

```text
see where the process is active or unhealthy
→ hover to understand the health summary
→ click to see the relevant issues
→ open one record journey
→ understand Expected versus Actual
→ identify the responsible owner and next review action
```

The visual experience should attract attention like a modern interactive system while explaining evidence with the discipline of an audit tool.

## 12. Phase Boundary

This document does not authorize immediate frontend implementation.

The current active path remains:

```text
Backend readiness validation
→ readiness report review
→ representative Odoo sample validation
→ business-rule review
→ READY_FOR_UI decision
→ frontend concept and implementation
```

Once `READY_FOR_UI` is confirmed, this document becomes the primary design brief for frontend concept development and implementation prompts.