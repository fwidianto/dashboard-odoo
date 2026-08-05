-- Bounded Control Tower derived read-model bundle for disposable PostgreSQL tests.
--
-- The production publication path runs the full approved SQL bundle
-- (sql/09..13).  Those files additionally depend on the dashboard sync schema
-- (sale_order etc.) which is not part of the disposable Control Tower test
-- database.  This file provides the minimal, schema-compatible derived objects
-- the tests use to prove that the derived-data stage runs inside the safe
-- publication boundary and that the trusted pointer now serves candidate
-- evidence.  It does not change business-rule meaning.

CREATE OR REPLACE VIEW vw_ct_current_run AS
SELECT
    run.run_id,
    run.started_at,
    run.completed_at,
    run.company_id,
    run.model_counts
FROM ct_extraction_run run
LEFT JOIN ct_published_snapshot pointer
  ON pointer.company_id = run.company_id
WHERE run.status IN ('COMPLETED', 'SUCCEEDED')
  AND (
      pointer.run_id = run.run_id
      OR NOT EXISTS (
          SELECT 1
          FROM ct_published_snapshot existing_pointer
          WHERE existing_pointer.company_id = run.company_id
      )
  )
ORDER BY run.completed_at DESC NULLS LAST, run.started_at DESC
LIMIT 1;

CREATE OR REPLACE VIEW vw_ct_native_record_snapshot_current AS
SELECT snapshot.*
FROM ct_native_record_snapshot snapshot
JOIN vw_ct_current_run current_run
  ON current_run.run_id = snapshot.extraction_run_id;

CREATE OR REPLACE VIEW vw_ct_document_links AS
SELECT link.*
FROM ct_document_link link
JOIN vw_ct_current_run current_run
  ON current_run.run_id = link.extraction_run_id;

-- Bounded derived evidence the tests can read after publication.
CREATE OR REPLACE VIEW vw_ct_test_published_evidence AS
SELECT
    current_run.run_id::text AS published_run_id,
    current_run.completed_at AS published_at,
    (SELECT COUNT(*) FROM vw_ct_native_record_snapshot_current) AS snapshot_count,
    (SELECT COUNT(*) FROM vw_ct_document_links) AS link_count
FROM vw_ct_current_run current_run;
