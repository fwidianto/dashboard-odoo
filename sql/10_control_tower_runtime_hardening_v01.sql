-- =============================================================================
-- Control Tower Health v0.1.1 - Runtime hardening after first live extraction
-- =============================================================================
-- Perubahan:
--   1. normalisasi x_studio_category tanpa mengubah snapshot mentah;
--   2. materialisasi document paths dan hasil rule untuk respons API cepat;
--   3. batasi SO cancellation ke dokumen downstream operasional;
--   4. perlakukan active MO pada SO berbasis IO sebagai review signal, bukan
--      confirmed process mismatch.
--
-- Tetap read-only terhadap Odoo. Seluruh object berada di PostgreSQL dashboard.
-- =============================================================================

-- Normalisasi selection/many2one category pada lapisan view. Payload mentah tetap
-- dipertahankan di ct_native_record_snapshot dan disalin ke key diagnostik.
CREATE OR REPLACE VIEW vw_ct_native_record_snapshot_current AS
SELECT
    snapshot.extraction_run_id,
    snapshot.model,
    snapshot.record_id,
    snapshot.document_number,
    snapshot.state,
    snapshot.company_id,
    snapshot.company_name,
    snapshot.write_date,
    CASE
        WHEN snapshot.model = 'approval.product.line' THEN
            snapshot.payload || JSONB_BUILD_OBJECT(
                '_ct_raw_x_studio_category', snapshot.payload -> 'x_studio_category',
                'x_studio_category', COALESCE(
                    NULLIF(snapshot.payload #>> '{x_studio_category,name}', ''),
                    NULLIF(snapshot.payload #>> '{x_studio_category,display_name}', ''),
                    NULLIF(snapshot.payload ->> 'x_studio_category', ''),
                    ''
                )
            )
        ELSE snapshot.payload
    END AS payload,
    snapshot.extracted_at
FROM ct_native_record_snapshot snapshot
JOIN vw_ct_current_run current_run
  ON current_run.run_id = snapshot.extraction_run_id;

CREATE OR REPLACE VIEW vw_ct_io_category_diagnostics AS
SELECT
    payload -> '_ct_raw_x_studio_category' AS raw_category,
    payload ->> 'x_studio_category' AS normalized_category,
    COUNT(*) AS record_count
FROM vw_ct_native_record_snapshot_current
WHERE model = 'approval.product.line'
GROUP BY
    payload -> '_ct_raw_x_studio_category',
    payload ->> 'x_studio_category'
ORDER BY record_count DESC;

-- Materialized objects are rebuilt after every completed extraction/read-model
-- application. API reads these objects; expensive recursive work happens once.
DROP MATERIALIZED VIEW IF EXISTS mv_ct_exception_worklist CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_ct_sop_validation_summary CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_ct_rule_results CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_ct_document_paths CASCADE;

CREATE MATERIALIZED VIEW mv_ct_document_paths AS
SELECT *
FROM vw_ct_document_paths
WITH DATA;

CREATE INDEX idx_mv_ct_paths_root
    ON mv_ct_document_paths (root_model, root_id, depth);
CREATE INDEX idx_mv_ct_paths_parent
    ON mv_ct_document_paths (parent_model, parent_id);
CREATE INDEX idx_mv_ct_paths_child
    ON mv_ct_document_paths (child_model, child_id);

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
)
SELECT
    rule_id,
    sop_section,
    document_model,
    document_id,
    document_number,
    expected_condition,
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
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN
            actual_condition || JSONB_BUILD_OBJECT(
                'review_reason', 'Active MO may be legitimate for a mixed-source SO; line-level evidence is required'
            )
        ELSE actual_condition
    END AS actual_condition,
    CASE
        WHEN rule_id = 'SO-CANCEL-001' AND operational_open_count = 0 THEN 'VALIDATED'
        WHEN rule_id = 'SO-CANCEL-001' THEN 'MISMATCH'
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN 'PARTIAL_MATCH'
        ELSE validation_status
    END AS validation_status,
    CASE
        WHEN rule_id = 'SO-CANCEL-001' AND operational_open_count = 0 THEN 'LOW'
        WHEN rule_id = 'SO-CANCEL-001' THEN 'HIGH'
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
        WHEN rule_id = 'SO-IO-MO-001' AND validation_status = 'MISMATCH' THEN
            evidence || JSONB_BUILD_OBJECT(
                'requires_line_level_review', TRUE,
                'classification', 'REVIEW_SIGNAL_NOT_CONFIRMED_MISMATCH'
            )
        ELSE evidence
    END AS evidence,
    detected_at
FROM adjusted
WITH DATA;

CREATE INDEX idx_mv_ct_rule_status
    ON mv_ct_rule_results (rule_id, validation_status);
CREATE INDEX idx_mv_ct_rule_document
    ON mv_ct_rule_results (document_model, document_id);

CREATE MATERIALIZED VIEW mv_ct_sop_validation_summary AS
WITH aggregate AS (
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
    FROM mv_ct_rule_results result
    GROUP BY result.rule_id
)
SELECT
    catalog.rule_id,
    catalog.rule_name,
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
    catalog.rule_name,
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
WITH DATA;

-- Satu IO dapat menghasilkan lebih dari satu result per product/UoM, sehingga
-- issue_id sengaja tidak dibuat unique pada v0.1.1.
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

COMMENT ON MATERIALIZED VIEW mv_ct_document_paths IS
    'Precomputed document paths for fast journey queries. Rebuilt after each extraction.';
COMMENT ON MATERIALIZED VIEW mv_ct_rule_results IS
    'Runtime-adjusted SOP validation results after first live reconciliation.';
COMMENT ON MATERIALIZED VIEW mv_ct_exception_worklist IS
    'Fast read-only investigation queue for Control Tower API.';
