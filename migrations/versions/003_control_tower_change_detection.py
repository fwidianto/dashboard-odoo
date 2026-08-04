"""Phase 8B-2B1 durable incremental change manifest.

Revision ID: 003
Revises: 002
"""

from typing import Sequence, Union
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE public.ct_change_detection_run (
            run_id UUID PRIMARY KEY REFERENCES public.ct_extraction_run(run_id) ON DELETE RESTRICT,
            company_id BIGINT NOT NULL CHECK (company_id > 0),
            base_snapshot_run_id UUID NOT NULL REFERENCES public.ct_extraction_run(run_id) ON DELETE RESTRICT,
            selected_domains JSONB NOT NULL,
            models JSONB NOT NULL,
            registry_fingerprint TEXT NOT NULL CHECK (length(btrim(registry_fingerprint)) = 64),
            watermark_inputs JSONB NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETE')),
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ,
            duration_seconds DOUBLE PRECISION CHECK (duration_seconds IS NULL OR duration_seconds >= 0),
            contract_fingerprint TEXT NOT NULL CHECK (length(btrim(contract_fingerprint)) = 64),
            completion_contract_version TEXT,
            completion_fingerprint TEXT,
            manifest_row_count BIGINT CHECK (manifest_row_count IS NULL OR manifest_row_count >= 0),
            model_row_counts JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_ct_change_detection_run_company UNIQUE (run_id, company_id),
            CHECK ((status = 'RUNNING' AND finished_at IS NULL AND duration_seconds IS NULL)
                OR (status = 'COMPLETE' AND finished_at IS NOT NULL AND duration_seconds IS NOT NULL
                    AND completion_contract_version = 'ct-change-manifest-v1'
                    AND length(btrim(completion_fingerprint)) = 64
                    AND manifest_row_count IS NOT NULL
                    AND model_row_counts IS NOT NULL))
        )
    """)
    op.execute("CREATE INDEX idx_ct_change_detection_company_status ON public.ct_change_detection_run (company_id, status)")
    op.execute("""
        CREATE TABLE public.ct_change_manifest (
            run_id UUID NOT NULL,
            company_id BIGINT NOT NULL CHECK (company_id > 0),
            business_domains JSONB NOT NULL,
            model TEXT NOT NULL CHECK (length(btrim(model)) > 0),
            record_id BIGINT NOT NULL CHECK (record_id > 0),
            source_write_date TIMESTAMPTZ NOT NULL,
            parent_model TEXT,
            parent_record_id BIGINT CHECK (parent_record_id IS NULL OR parent_record_id > 0),
            parent_hints JSONB NOT NULL DEFAULT '[]'::jsonb,
            from_overlap BOOLEAN NOT NULL,
            detection_sequence BIGINT NOT NULL CHECK (detection_sequence > 0),
            detected_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'DETECTED'
                CHECK (status IN ('DETECTED', 'FETCHED', 'APPLIED')),
            PRIMARY KEY (run_id, model, record_id),
            UNIQUE (run_id, model, detection_sequence),
            CONSTRAINT fk_ct_change_manifest_run_company
                FOREIGN KEY (run_id, company_id)
                REFERENCES public.ct_change_detection_run(run_id, company_id)
                ON DELETE RESTRICT
        )
    """)
    op.execute("CREATE INDEX idx_ct_change_manifest_model_tuple ON public.ct_change_manifest (company_id, model, source_write_date, record_id)")
    op.execute("CREATE INDEX idx_ct_change_manifest_status ON public.ct_change_manifest (run_id, status)")


def downgrade() -> None:
    op.execute("DROP INDEX public.idx_ct_change_manifest_status")
    op.execute("DROP INDEX public.idx_ct_change_manifest_model_tuple")
    op.execute("DROP TABLE public.ct_change_manifest")
    op.execute("DROP INDEX public.idx_ct_change_detection_company_status")
    op.execute("DROP TABLE public.ct_change_detection_run")
