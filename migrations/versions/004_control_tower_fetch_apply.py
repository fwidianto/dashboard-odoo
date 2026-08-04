"""Phase 8C-2 durable fetch/apply evidence.

Revision ID: 004
Revises: 003
"""

from typing import Sequence, Union

from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.ct_fetch_apply_run (
            run_id UUID PRIMARY KEY REFERENCES public.ct_extraction_run(run_id) ON DELETE RESTRICT,
            company_id BIGINT NOT NULL CHECK (company_id > 0),
            base_snapshot_run_id UUID NOT NULL REFERENCES public.ct_extraction_run(run_id) ON DELETE RESTRICT,
            selected_domains JSONB NOT NULL,
            models JSONB NOT NULL,
            manifest_completion_fingerprint TEXT NOT NULL CHECK (length(btrim(manifest_completion_fingerprint)) = 64),
            manifest_row_count BIGINT NOT NULL CHECK (manifest_row_count >= 0),
            batch_size INTEGER NOT NULL CHECK (batch_size > 0),
            contract_version TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETE')),
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            duration_seconds DOUBLE PRECISION CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
            completion_fingerprint TEXT,
            model_fetch_counts JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ct_fetch_apply_run_company UNIQUE (run_id, company_id),
            CHECK ((status = 'RUNNING' AND finished_at IS NULL AND duration_seconds IS NULL)
                OR (status = 'COMPLETE' AND finished_at IS NOT NULL AND duration_seconds IS NOT NULL
                    AND length(btrim(completion_fingerprint)) = 64
                    AND model_fetch_counts IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX idx_ct_fetch_apply_company_status ON public.ct_fetch_apply_run (company_id, status)")
    op.execute("""
        CREATE TABLE public.ct_fetch_apply_evidence (
            run_id UUID NOT NULL,
            company_id BIGINT NOT NULL CHECK (company_id > 0),
            model TEXT NOT NULL CHECK (length(btrim(model)) > 0),
            record_id BIGINT NOT NULL CHECK (record_id > 0),
            detection_sequence BIGINT NOT NULL CHECK (detection_sequence > 0),
            batch_number BIGINT NOT NULL CHECK (batch_number > 0),
            detection_source_write_date TIMESTAMPTZ NOT NULL,
            fetched_write_date TIMESTAMPTZ,
            fetch_status TEXT NOT NULL CHECK (fetch_status IN ('FETCHED', 'MISSING_AT_FETCH')),
            apply_status TEXT NOT NULL CHECK (
                apply_status IN ('PENDING', 'INSERTED', 'UPDATED', 'UNCHANGED', 'MISSING_AT_FETCH')
            ),
            source_drift BOOLEAN NOT NULL DEFAULT FALSE,
            payload_fingerprint TEXT CHECK (payload_fingerprint IS NULL OR length(btrim(payload_fingerprint)) = 64),
            fetched_at TIMESTAMPTZ,
            applied_at TIMESTAMPTZ,
            error_evidence JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (run_id, model, record_id),
            UNIQUE (run_id, model, detection_sequence),
            CONSTRAINT fk_ct_fetch_evidence_run_company
                FOREIGN KEY (run_id, company_id)
                REFERENCES public.ct_fetch_apply_run(run_id, company_id)
                ON DELETE RESTRICT,
            CHECK (
                (fetch_status = 'FETCHED' AND fetched_write_date IS NOT NULL
                 AND payload_fingerprint IS NOT NULL AND fetched_at IS NOT NULL
                 AND apply_status IN ('INSERTED', 'UPDATED', 'UNCHANGED'))
                OR (fetch_status = 'MISSING_AT_FETCH' AND fetched_write_date IS NULL
                    AND payload_fingerprint IS NULL AND fetched_at IS NOT NULL
                    AND apply_status = 'MISSING_AT_FETCH')
            )
        )
    """)
    op.execute("""
        CREATE TABLE public.ct_fetch_apply_batch (
            run_id UUID NOT NULL,
            model TEXT NOT NULL CHECK (length(btrim(model)) > 0),
            batch_number BIGINT NOT NULL CHECK (batch_number > 0),
            records_requested BIGINT NOT NULL CHECK (records_requested > 0),
            records_fetched BIGINT NOT NULL CHECK (records_fetched >= 0),
            records_missing BIGINT NOT NULL CHECK (records_missing >= 0),
            inserted BIGINT NOT NULL CHECK (inserted >= 0),
            updated BIGINT NOT NULL CHECK (updated >= 0),
            unchanged BIGINT NOT NULL CHECK (unchanged >= 0),
            source_drift BIGINT NOT NULL CHECK (source_drift >= 0),
            completed_at TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (run_id, model, batch_number),
            CONSTRAINT fk_ct_fetch_batch_run
                FOREIGN KEY (run_id) REFERENCES public.ct_fetch_apply_run(run_id)
                ON DELETE RESTRICT,
            CHECK (records_fetched + records_missing = records_requested),
            CHECK (inserted + updated + unchanged = records_fetched)
        )
    """)
    op.execute("ALTER TABLE public.ct_change_manifest DROP CONSTRAINT ct_change_manifest_status_check")
    op.execute("""
        ALTER TABLE public.ct_change_manifest ADD CONSTRAINT ct_change_manifest_status_check
        CHECK (status IN ('DETECTED', 'FETCHED', 'APPLIED', 'MISSING_AT_FETCH'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE public.ct_change_manifest DROP CONSTRAINT ct_change_manifest_status_check")
    op.execute("""
        ALTER TABLE public.ct_change_manifest ADD CONSTRAINT ct_change_manifest_status_check
        CHECK (status IN ('DETECTED', 'FETCHED', 'APPLIED'))
    """)
    op.execute("DROP TABLE public.ct_fetch_apply_batch")
    op.execute("DROP TABLE public.ct_fetch_apply_evidence")
    op.execute("DROP INDEX public.idx_ct_fetch_apply_company_status")
    op.execute("DROP TABLE public.ct_fetch_apply_run")
