-- Control Tower PO cancellation scope hardening.
--
-- Business authority: only purchase.order.date_order >= 2026-01-01 belongs
-- to the active operational PO cancellation KPI. Historical and missing-date
-- records remain reviewable in dedicated views; source snapshots are untouched.

CREATE TABLE IF NOT EXISTS ct_purchase_order_date_enrichment_execution (
    execution_id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    company_id BIGINT NOT NULL,
    expected_count BIGINT NOT NULL,
    returned_count BIGINT,
    null_date_order_count BIGINT,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failure_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_ct_po_date_enrichment_execution_run
    ON ct_purchase_order_date_enrichment_execution (run_id, status, completed_at DESC);

CREATE TABLE IF NOT EXISTS ct_purchase_order_date_enrichment (
    run_id UUID NOT NULL,
    purchase_order_id BIGINT NOT NULL,
    company_id BIGINT NOT NULL,
    source_state TEXT NOT NULL,
    date_order TIMESTAMP WITHOUT TIME ZONE,
    source_write_date TIMESTAMP WITHOUT TIME ZONE,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enrichment_status TEXT NOT NULL CHECK (enrichment_status = 'COMPLETED'),
    enrichment_execution_id UUID NOT NULL
        REFERENCES ct_purchase_order_date_enrichment_execution (execution_id),
    PRIMARY KEY (run_id, purchase_order_id)
);

CREATE INDEX IF NOT EXISTS idx_ct_po_date_enrichment_scope
    ON ct_purchase_order_date_enrichment (run_id, date_order, purchase_order_id);

CREATE OR REPLACE VIEW vw_ct_purchase_order_date_enrichment_current AS
SELECT enrichment.*
FROM ct_purchase_order_date_enrichment enrichment
JOIN vw_ct_current_run current_run
  ON current_run.run_id = enrichment.run_id
JOIN ct_purchase_order_date_enrichment_execution execution
  ON execution.execution_id = enrichment.enrichment_execution_id
 AND execution.status = 'COMPLETED'
WHERE enrichment.company_id = 3
  AND enrichment.enrichment_status = 'COMPLETED';

CREATE OR REPLACE VIEW vw_ct_po_cancellation_scope AS
WITH cancelled_po AS (
    SELECT
        current_run.run_id,
        po.record_id AS purchase_order_id,
        po.document_number AS purchase_order_number,
        LOWER(COALESCE(po.state, '')) AS purchase_order_state,
        enrichment.date_order
    FROM vw_ct_native_record_snapshot_current po
    CROSS JOIN vw_ct_current_run current_run
    LEFT JOIN vw_ct_purchase_order_date_enrichment_current enrichment
      ON enrichment.run_id = current_run.run_id
     AND enrichment.purchase_order_id = po.record_id
    WHERE current_run.company_id = 3
      AND po.model = 'purchase.order'
      AND LOWER(COALESCE(po.state, '')) IN ('cancel', 'cancelled')
),
receipt_link AS (
    SELECT DISTINCT
        link.parent_id AS purchase_order_id,
        link.child_id AS receipt_id,
        receipt.document_number AS receipt_number,
        LOWER(COALESCE(receipt.state, '')) AS receipt_state
    FROM vw_ct_document_links link
    JOIN cancelled_po po
      ON po.purchase_order_id = link.parent_id
    JOIN vw_ct_native_record_snapshot_current receipt
      ON receipt.model = 'stock.picking'
     AND receipt.record_id = link.child_id
    WHERE link.link_type = 'PO_TO_RECEIPT'
      AND link.parent_model = 'purchase.order'
      AND link.child_model = 'stock.picking'
      AND link.confidence = 'HIGH'
),
receipt_summary AS (
    SELECT
        purchase_order_id,
        COUNT(DISTINCT receipt_id) FILTER (
            WHERE receipt_state IN ('draft', 'waiting', 'confirmed', 'assigned', 'partially_available')
        ) AS operational_open_receipt_count,
        COUNT(DISTINCT receipt_id) FILTER (
            WHERE receipt_state NOT IN (
                'draft', 'waiting', 'confirmed', 'assigned', 'partially_available',
                'done', 'cancel', 'cancelled'
            )
        ) AS unsupported_receipt_state_count,
        COALESCE(
            JSONB_AGG(DISTINCT JSONB_BUILD_OBJECT(
                'id', receipt_id,
                'number', receipt_number,
                'state', receipt_state
            )) FILTER (
                WHERE receipt_state IN ('draft', 'waiting', 'confirmed', 'assigned', 'partially_available')
            ),
            '[]'::jsonb
        ) AS open_receipts
    FROM receipt_link
    GROUP BY purchase_order_id
),
open_backorder AS (
    SELECT DISTINCT
        receipt_link.purchase_order_id,
        receipt_link.receipt_id AS child_receipt_id
    FROM receipt_link
    JOIN vw_ct_document_links backorder
      ON backorder.link_type = 'PICKING_TO_BACKORDER'
     AND backorder.parent_model = 'stock.picking'
     AND backorder.child_model = 'stock.picking'
     AND backorder.child_id = receipt_link.receipt_id
     AND backorder.confidence = 'HIGH'
    JOIN vw_ct_native_record_snapshot_current parent_receipt
      ON parent_receipt.model = 'stock.picking'
     AND parent_receipt.record_id = backorder.parent_id
    WHERE receipt_link.receipt_state IN (
        'draft', 'waiting', 'confirmed', 'assigned', 'partially_available'
    )
      AND LOWER(COALESCE(parent_receipt.state, '')) IN ('done', 'cancel', 'cancelled')
),
backorder_summary AS (
    SELECT
        purchase_order_id,
        COUNT(DISTINCT child_receipt_id) AS open_backorder_count
    FROM open_backorder
    GROUP BY purchase_order_id
),
scoped AS (
    SELECT
        po.run_id,
        po.purchase_order_id,
        po.purchase_order_number,
        po.purchase_order_state,
        po.date_order,
        CASE
            WHEN po.date_order >= DATE '2026-01-01' THEN 'ACTIVE_2026_PLUS'
            WHEN po.date_order < DATE '2026-01-01' THEN 'HISTORICAL_PRE_2026'
            ELSE 'DATE_SCOPE_UNKNOWN'
        END AS date_scope,
        COALESCE(receipt.operational_open_receipt_count, 0) AS operational_open_receipt_count,
        COALESCE(receipt.unsupported_receipt_state_count, 0) AS unsupported_receipt_state_count,
        COALESCE(receipt.open_receipts, '[]'::jsonb) AS open_receipts,
        COALESCE(backorder.open_backorder_count, 0) AS open_backorder_count
    FROM cancelled_po po
    LEFT JOIN receipt_summary receipt
      ON receipt.purchase_order_id = po.purchase_order_id
    LEFT JOIN backorder_summary backorder
      ON backorder.purchase_order_id = po.purchase_order_id
)
SELECT
    scoped.*,
    CASE
        WHEN date_scope = 'ACTIVE_2026_PLUS' AND operational_open_receipt_count > 0
            THEN 'ACTIVE_ISSUE'
        WHEN date_scope = 'HISTORICAL_PRE_2026' AND operational_open_receipt_count > 0
            THEN 'HISTORICAL_EXPOSURE'
        WHEN date_scope = 'DATE_SCOPE_UNKNOWN' AND operational_open_receipt_count > 0
            THEN 'DATE_REVIEW_REQUIRED'
        ELSE 'NO_OPEN_RECEIPT'
    END AS operational_exposure,
    CASE
        WHEN date_scope = 'ACTIVE_2026_PLUS' AND operational_open_receipt_count > 0
            THEN 'Masalah Aktif 2026+'
        WHEN date_scope = 'HISTORICAL_PRE_2026' AND operational_open_receipt_count > 0
            THEN 'Catatan Historis'
        WHEN date_scope = 'DATE_SCOPE_UNKNOWN'
            THEN 'Tanggal PO Belum Tersedia'
        ELSE 'Tidak ada penerimaan barang terbuka'
    END AS business_label,
    CASE
        WHEN date_scope = 'ACTIVE_2026_PLUS' AND open_backorder_count > 0
            THEN 'Penerimaan Backorder Masih Terbuka.'
        WHEN date_scope = 'ACTIVE_2026_PLUS' AND operational_open_receipt_count > 0
            THEN 'PO Sudah Dibatalkan, tetapi Penerimaan Barang Masih Terbuka.'
        WHEN date_scope = 'HISTORICAL_PRE_2026' AND open_backorder_count > 0
            THEN 'Catatan Historis: Penerimaan Backorder Masih Terbuka dan ditampilkan untuk audit.'
        WHEN date_scope = 'HISTORICAL_PRE_2026' AND operational_open_receipt_count > 0
            THEN 'Kasus berasal dari PO sebelum 2026 dan ditampilkan untuk kebutuhan audit.'
        WHEN date_scope = 'DATE_SCOPE_UNKNOWN'
            THEN 'Tanggal PO belum tersedia sehingga belum dapat ditentukan sebagai masalah aktif atau historis.'
        ELSE 'Tidak ada Receipt operasional terbuka pada PO cancelled ini.'
    END AS business_message,
    'HIGH'::text AS relation_confidence
FROM scoped;

CREATE OR REPLACE VIEW vw_ct_po_cancellation_active AS
SELECT *
FROM vw_ct_po_cancellation_scope
WHERE date_scope = 'ACTIVE_2026_PLUS';

CREATE OR REPLACE VIEW vw_ct_po_cancellation_historical AS
SELECT *
FROM vw_ct_po_cancellation_scope
WHERE date_scope = 'HISTORICAL_PRE_2026';

CREATE OR REPLACE VIEW vw_ct_po_cancellation_date_review AS
SELECT *
FROM vw_ct_po_cancellation_scope
WHERE date_scope = 'DATE_SCOPE_UNKNOWN';

-- Rebuild only the three runtime materializations whose PO-CANCEL-001
-- semantics change. The source snapshot and document-link graph remain intact.
DROP MATERIALIZED VIEW IF EXISTS mv_ct_exception_worklist;
DROP MATERIALIZED VIEW IF EXISTS mv_ct_sop_validation_summary;
DROP MATERIALIZED VIEW IF EXISTS mv_ct_rule_results;

CREATE MATERIALIZED VIEW mv_ct_rule_results AS
WITH base AS (
    SELECT * FROM vw_ct_rule_results
),
adjusted AS (
    SELECT
        base.*,
        CASE
            WHEN base.rule_id = 'SO-CANCEL-001' THEN COALESCE((
                SELECT COUNT(*)
                FROM JSONB_ARRAY_ELEMENTS(
                    COALESCE(base.actual_condition -> 'open_documents', '[]'::jsonb)
                ) document
                WHERE document ->> 'model' IN (
                    'mrp.production',
                    'stock.picking',
                    'purchase.order',
                    'account.move'
                )
            ), 0)
            ELSE NULL
        END AS operational_open_count,
        CASE
            WHEN base.rule_id = 'SO-CANCEL-001' THEN COALESCE((
                SELECT JSONB_AGG(document)
                FROM JSONB_ARRAY_ELEMENTS(
                    COALESCE(base.actual_condition -> 'open_documents', '[]'::jsonb)
                ) document
                WHERE document ->> 'model' IN (
                    'mrp.production',
                    'stock.picking',
                    'purchase.order',
                    'account.move'
                )
            ), '[]'::jsonb)
            ELSE NULL
        END AS operational_open_documents
    FROM base
),
scoped AS (
    SELECT
        adjusted.*,
        COALESCE(scope.date_scope, 'DATE_SCOPE_UNKNOWN') AS po_date_scope,
        COALESCE(scope.operational_exposure, 'DATE_REVIEW_REQUIRED') AS po_operational_exposure,
        COALESCE(scope.operational_open_receipt_count, 0) AS po_open_receipt_count,
        COALESCE(scope.unsupported_receipt_state_count, 0) AS po_unsupported_receipt_state_count,
        COALESCE(scope.open_backorder_count, 0) AS po_open_backorder_count,
        COALESCE(scope.open_receipts, '[]'::jsonb) AS po_open_receipts,
        COALESCE(scope.business_label, 'Tanggal PO Belum Tersedia') AS po_business_label,
        COALESCE(
            scope.business_message,
            'Tanggal PO belum tersedia sehingga belum dapat ditentukan sebagai masalah aktif atau historis.'
        ) AS po_business_message
    FROM adjusted
    LEFT JOIN vw_ct_po_cancellation_scope scope
      ON adjusted.rule_id = 'PO-CANCEL-001'
     AND scope.purchase_order_id = adjusted.document_id
)
SELECT
    rule_id,
    sop_section,
    document_model,
    document_id,
    document_number,
    CASE
        WHEN rule_id = 'PO-CANCEL-001' THEN JSONB_BUILD_OBJECT(
            'active_scope_starts_on', '2026-01-01',
            'active_open_receipt_count', 0,
            'historical_exposures_retained', TRUE,
            'date_scope_unknown_requires_review', TRUE
        )
        ELSE expected_condition
    END AS expected_condition,
    CASE
        WHEN rule_id = 'SO-CANCEL-001' THEN JSONB_BUILD_OBJECT(
            'open_downstream_count', operational_open_count,
            'historical_downstream_count', COALESCE(
                NULLIF(actual_condition ->> 'historical_downstream_count', '')::bigint,
                0
            ),
            'open_documents', operational_open_documents,
            'scope', 'OPERATIONAL_DOCUMENTS_ONLY'
        )
        WHEN rule_id = 'PO-CANCEL-001' THEN JSONB_BUILD_OBJECT(
            'date_scope', po_date_scope,
            'date_order_scope_boundary', '2026-01-01',
            'operational_exposure', po_operational_exposure,
            'open_receipt_count', po_open_receipt_count,
            'unsupported_receipt_state_count', po_unsupported_receipt_state_count,
            'open_backorder_count', po_open_backorder_count,
            'open_receipts', po_open_receipts,
            'business_label', po_business_label,
            'business_message', po_business_message
        )
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN
            actual_condition || JSONB_BUILD_OBJECT(
                'review_reason', 'Active MO may be legitimate for a mixed-source SO; line-level evidence is required'
            )
        ELSE actual_condition
    END AS actual_condition,
    CASE
        WHEN rule_id = 'SO-CANCEL-001' AND operational_open_count = 0 THEN 'VALIDATED'
        WHEN rule_id = 'SO-CANCEL-001' THEN 'MISMATCH'
        WHEN rule_id = 'PO-CANCEL-001'
         AND po_date_scope = 'ACTIVE_2026_PLUS'
         AND po_operational_exposure = 'ACTIVE_ISSUE' THEN 'MISMATCH'
        WHEN rule_id = 'PO-CANCEL-001'
         AND (po_operational_exposure = 'HISTORICAL_EXPOSURE' OR po_date_scope = 'DATE_SCOPE_UNKNOWN')
            THEN 'VALID_EXCEPTION'
        WHEN rule_id = 'PO-CANCEL-001' THEN 'VALIDATED'
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN 'PARTIAL_MATCH'
        ELSE validation_status
    END AS validation_status,
    CASE
        WHEN rule_id = 'SO-CANCEL-001' AND operational_open_count = 0 THEN 'LOW'
        WHEN rule_id = 'SO-CANCEL-001' THEN 'HIGH'
        WHEN rule_id = 'PO-CANCEL-001'
         AND po_operational_exposure IN ('ACTIVE_ISSUE', 'HISTORICAL_EXPOSURE', 'DATE_REVIEW_REQUIRED')
            THEN 'HIGH'
        WHEN rule_id = 'PO-CANCEL-001' AND po_date_scope = 'DATE_SCOPE_UNKNOWN' THEN 'MEDIUM'
        WHEN rule_id = 'PO-CANCEL-001' THEN 'LOW'
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN 'MEDIUM'
        ELSE severity
    END AS severity,
    CASE
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN 'MEDIUM'
        ELSE confidence
    END AS confidence,
    owner,
    CASE
        WHEN rule_id = 'SO-CANCEL-001' THEN evidence || JSONB_BUILD_OBJECT(
            'basis', 'operational descendant graph only',
            'operational_models', JSONB_BUILD_ARRAY(
                'mrp.production', 'stock.picking', 'purchase.order', 'account.move'
            )
        )
        WHEN rule_id = 'PO-CANCEL-001' THEN COALESCE(evidence, '{}'::jsonb) || JSONB_BUILD_OBJECT(
            'basis', 'purchase.order.line -> stock.move.purchase_line_id -> stock.picking native relation',
            'date_scope_field', 'purchase.order.date_order',
            'date_scope_boundary', '2026-01-01',
            'write_date_used_for_scope', FALSE,
            'backorder_evaluated', TRUE,
            'historical_records_retained', TRUE
        )
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN
            evidence || JSONB_BUILD_OBJECT(
                'requires_line_level_review', TRUE,
                'classification', 'REVIEW_SIGNAL_NOT_CONFIRMED_MISMATCH'
            )
        ELSE evidence
    END AS evidence,
    detected_at
FROM scoped
WITH DATA;

CREATE INDEX idx_mv_ct_rule_status
    ON mv_ct_rule_results (rule_id, validation_status);
CREATE INDEX idx_mv_ct_rule_document
    ON mv_ct_rule_results (document_model, document_id);

CREATE MATERIALIZED VIEW mv_ct_sop_validation_summary AS
WITH active_results AS (
    SELECT *
    FROM mv_ct_rule_results result
    WHERE result.rule_id <> 'PO-CANCEL-001'
       OR result.actual_condition ->> 'date_scope' = 'ACTIVE_2026_PLUS'
),
aggregate AS (
    SELECT
        result.rule_id,
        COUNT(*) AS tested_records,
        COUNT(*) FILTER (WHERE validation_status = 'VALIDATED') AS validated_records,
        COUNT(*) FILTER (WHERE validation_status = 'PARTIAL_MATCH') AS partial_match_records,
        COUNT(*) FILTER (WHERE validation_status = 'MISMATCH') AS mismatch_records,
        COUNT(*) FILTER (WHERE validation_status = 'MANUAL_EVIDENCE_REQUIRED') AS manual_records,
        COUNT(*) FILTER (WHERE validation_status = 'DATA_LINKAGE_GAP') AS linkage_gap_records,
        COUNT(*) FILTER (WHERE validation_status = 'VALID_EXCEPTION') AS valid_exception_records,
        COUNT(*) FILTER (WHERE validation_status = 'NOT_TESTED') AS not_tested_records
    FROM active_results result
    GROUP BY result.rule_id
)
SELECT
    catalog.rule_id,
    CASE
        WHEN catalog.rule_id = 'PO-CANCEL-001'
            THEN 'Masalah Aktif 2026+: PO dibatalkan dengan penerimaan barang terbuka'
        ELSE catalog.rule_name
    END AS rule_name,
    catalog.sop_section,
    catalog.owner,
    catalog.default_severity,
    catalog.implementation_class,
    COALESCE(aggregate.tested_records, 0) AS tested_records,
    COALESCE(aggregate.validated_records, 0) AS validated_records,
    COALESCE(aggregate.partial_match_records, 0) AS partial_match_records,
    COALESCE(aggregate.mismatch_records, 0) AS mismatch_records,
    COALESCE(aggregate.manual_records, 0) AS manual_records,
    COALESCE(aggregate.linkage_gap_records, 0) AS linkage_gap_records,
    COALESCE(aggregate.valid_exception_records, 0) AS valid_exception_records,
    COALESCE(aggregate.not_tested_records, 0) AS not_tested_records,
    CASE
        WHEN aggregate.rule_id IS NULL AND catalog.implementation_class = 'MANUAL_EVIDENCE_ONLY'
            THEN 'MANUAL_EVIDENCE_REQUIRED'
        WHEN aggregate.rule_id IS NULL THEN 'NOT_TESTED'
        WHEN COALESCE(aggregate.mismatch_records, 0) > 0 THEN 'MISMATCH'
        WHEN COALESCE(aggregate.linkage_gap_records, 0) > 0 THEN 'DATA_LINKAGE_GAP'
        WHEN COALESCE(aggregate.partial_match_records, 0) > 0 THEN 'PARTIAL_MATCH'
        ELSE 'VALIDATED'
    END AS overall_status,
    CASE
        WHEN COALESCE(aggregate.tested_records, 0) = 0 THEN NULL
        ELSE ROUND(
            100.0 * COALESCE(aggregate.validated_records, 0)
            / NULLIF(aggregate.tested_records, 0),
            2
        )
    END AS validation_rate_percent
FROM vw_ct_rule_catalog catalog
LEFT JOIN aggregate
  ON aggregate.rule_id = catalog.rule_id
WITH DATA;

CREATE UNIQUE INDEX idx_mv_ct_summary_rule
    ON mv_ct_sop_validation_summary (rule_id);

CREATE MATERIALIZED VIEW mv_ct_exception_worklist AS
SELECT
    MD5(result.rule_id || '|' || result.document_model || '|' || result.document_id::text) AS issue_id,
    result.rule_id,
    CASE
        WHEN result.rule_id = 'PO-CANCEL-001'
            THEN 'Masalah Aktif 2026+: PO dibatalkan dengan penerimaan barang terbuka'
        ELSE catalog.rule_name
    END AS rule_name,
    result.sop_section,
    result.document_model,
    result.document_id,
    result.document_number,
    result.validation_status,
    result.severity,
    result.confidence,
    result.owner,
    result.expected_condition,
    result.actual_condition,
    result.evidence,
    result.detected_at,
    CASE result.severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END AS severity_priority
FROM mv_ct_rule_results result
LEFT JOIN vw_ct_rule_catalog catalog
  ON catalog.rule_id = result.rule_id
WHERE result.validation_status IN (
    'PARTIAL_MATCH',
    'MISMATCH',
    'MANUAL_EVIDENCE_REQUIRED',
    'DATA_LINKAGE_GAP',
    'NOT_TESTED'
)
  AND NOT (
    result.rule_id = 'PO-CANCEL-001'
    AND COALESCE(result.actual_condition ->> 'date_scope', 'DATE_SCOPE_UNKNOWN')
        <> 'ACTIVE_2026_PLUS'
  )
WITH DATA;

CREATE INDEX idx_mv_ct_exception_issue
    ON mv_ct_exception_worklist (issue_id);
CREATE INDEX idx_mv_ct_exception_filter
    ON mv_ct_exception_worklist (
        severity_priority,
        rule_id,
        validation_status,
        document_number,
        document_id
    );

COMMENT ON VIEW vw_ct_po_cancellation_scope IS
    'PO cancellation scope from targeted purchase.order.date_order enrichment; write_date is never used to classify active scope.';
COMMENT ON VIEW vw_ct_po_cancellation_historical IS
    'All cancelled Purchase Orders before 2026 retained for audit, including historical open Receipt exposures.';
COMMENT ON MATERIALIZED VIEW mv_ct_rule_results IS
    'Runtime-adjusted SOP results; PO-CANCEL-001 mismatch is limited to active 2026+ date_order scope.';
COMMENT ON MATERIALIZED VIEW mv_ct_exception_worklist IS
    'Active operational investigation queue; historical and unknown-date PO cancellation records are excluded from the active workload.';
