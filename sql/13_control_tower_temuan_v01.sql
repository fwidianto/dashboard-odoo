-- =============================================================================
-- Control Tower Temuan v0.1 - persisted Data Belum Lengkap findings
-- =============================================================================
-- Source rule: SO-PO-001
-- Canonical finding rule: DH2-SALES-001
-- This is an internal OPEN/RESOLVED lifecycle only. It is not an Archives or
-- manual ticketing implementation.
-- =============================================================================

DO $$
BEGIN
    IF to_regclass('public.ct_finding') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM information_schema.columns
           WHERE table_schema = 'public'
             AND table_name = 'ct_finding'
             AND column_name = 'finding_id'
       )
    THEN
        IF EXISTS (SELECT 1 FROM ct_finding) THEN
            RAISE EXCEPTION 'Cannot replace incompatible populated ct_finding table.';
        END IF;
        ALTER TABLE ct_finding RENAME TO ct_finding_legacy;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS ct_finding (
    finding_id TEXT PRIMARY KEY,
    category TEXT NOT NULL CHECK (category = 'DATA_BELUM_LENGKAP'),
    rule_code TEXT NOT NULL,
    affected_model TEXT NOT NULL,
    affected_document_id BIGINT NOT NULL,
    native_document_reference TEXT,
    company_id BIGINT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_detected_time TIMESTAMPTZ NOT NULL,
    last_detected_time TIMESTAMPTZ NOT NULL,
    current_status TEXT NOT NULL CHECK (current_status IN ('OPEN', 'RESOLVED')),
    destination_url TEXT NOT NULL,
    UNIQUE (rule_code, affected_model, affected_document_id, company_id)
);

CREATE INDEX IF NOT EXISTS idx_ct_finding_company_status
    ON ct_finding (company_id, current_status, category, affected_document_id);

CREATE OR REPLACE VIEW vw_ct_temuan_so_data_incomplete_current AS
WITH current_run AS (
    SELECT run_id, company_id
    FROM vw_ct_current_run
),
rule_rows AS (
    SELECT
        result.*,
        snapshot.company_id,
        snapshot.payload,
        snapshot.state AS native_state,
        snapshot.extraction_run_id
    FROM mv_ct_rule_results result
    JOIN vw_ct_native_record_snapshot_current snapshot
      ON snapshot.model = result.document_model
     AND snapshot.record_id = result.document_id
    JOIN current_run
      ON current_run.company_id = snapshot.company_id
    WHERE result.rule_id = 'SO-PO-001'
      AND result.document_model = 'sale.order'
      AND result.validation_status = 'MISMATCH'
),
missing_fields AS (
    SELECT
        rows.*,
        NULLIF(BTRIM(COALESCE(rows.actual_condition ->> 'client_order_ref', '')), '') IS NULL
            AS missing_customer_reference,
        NULLIF(BTRIM(COALESCE(rows.actual_condition ->> 'customer_po_date', '')), '') IS NULL
            AS missing_customer_po_date
    FROM rule_rows rows
)
SELECT
    MD5(CONCAT_WS('|', 'DH2-SALES-001', 'sale.order', document_id::text, company_id::text)) AS finding_id,
    'DATA_BELUM_LENGKAP'::text AS category,
    'DH2-SALES-001'::text AS rule_code,
    'sale.order'::text AS affected_model,
    document_id AS affected_document_id,
    document_number AS native_document_reference,
    company_id,
    'Data Sales Order belum lengkap'::text AS title,
    CASE
        WHEN missing_customer_reference AND missing_customer_po_date
            THEN 'Lengkapi Customer Reference dan Customer PO Date pada SO ' || COALESCE(document_number, document_id::text) || '.'
        WHEN missing_customer_reference
            THEN 'Lengkapi Customer Reference pada SO ' || COALESCE(document_number, document_id::text) || '.'
        ELSE 'Lengkapi Customer PO Date pada SO ' || COALESCE(document_number, document_id::text) || '.'
    END AS summary,
    JSONB_BUILD_OBJECT(
        'canonical_rule_code', 'DH2-SALES-001',
        'source_check', 'SO-PO-001',
        'source_model', 'sale.order',
        'source_fields', JSONB_BUILD_ARRAY(
            'state', 'date_order', 'client_order_ref',
            'x_studio_tanggal_po_cust', 'company_id'
        ),
        'state', native_state,
        'date_order', payload ->> 'date_order',
        'client_order_ref', actual_condition ->> 'client_order_ref',
        'customer_po_date', actual_condition ->> 'customer_po_date',
        'missing_fields',
            CASE WHEN missing_customer_reference
                THEN JSONB_BUILD_ARRAY('Customer Reference')
                ELSE '[]'::jsonb END
            || CASE WHEN missing_customer_po_date
                THEN JSONB_BUILD_ARRAY('Customer PO Date')
                ELSE '[]'::jsonb END,
        'effective_from', '2026-01-01',
        'extraction_run_id', extraction_run_id::text
    ) AS evidence_payload,
    detected_at AS detected_time,
    '/dashboard/sales-orders?sales_order_id=' || document_id::text AS destination_url
FROM missing_fields;

INSERT INTO ct_finding (
    finding_id,
    category,
    rule_code,
    affected_model,
    affected_document_id,
    native_document_reference,
    company_id,
    title,
    summary,
    evidence_payload,
    first_detected_time,
    last_detected_time,
    current_status,
    destination_url
)
SELECT
    finding_id,
    category,
    rule_code,
    affected_model,
    affected_document_id,
    native_document_reference,
    company_id,
    title,
    summary,
    evidence_payload,
    detected_time,
    detected_time,
    'OPEN',
    destination_url
FROM vw_ct_temuan_so_data_incomplete_current
ON CONFLICT (rule_code, affected_model, affected_document_id, company_id)
DO UPDATE SET
    native_document_reference = EXCLUDED.native_document_reference,
    title = EXCLUDED.title,
    summary = EXCLUDED.summary,
    evidence_payload = EXCLUDED.evidence_payload,
    last_detected_time = EXCLUDED.last_detected_time,
    current_status = 'OPEN',
    destination_url = EXCLUDED.destination_url;

UPDATE ct_finding finding
SET current_status = 'RESOLVED'
WHERE finding.rule_code = 'DH2-SALES-001'
  AND finding.affected_model = 'sale.order'
  AND finding.current_status = 'OPEN'
  AND finding.company_id = (SELECT company_id FROM vw_ct_current_run)
  AND NOT EXISTS (
      SELECT 1
      FROM vw_ct_temuan_so_data_incomplete_current current_finding
      WHERE current_finding.finding_id = finding.finding_id
  );

COMMENT ON TABLE ct_finding IS
    'Persisted Control Tower findings for the bounded Temuan v0.1 slice. Internal OPEN/RESOLVED lifecycle only.';
COMMENT ON VIEW vw_ct_temuan_so_data_incomplete_current IS
    'Current-company projection of SO-PO-001 mismatches into canonical DH2-SALES-001 Data Belum Lengkap findings.';
