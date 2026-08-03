"""Phase 8 refresh additions over the existing Phase 7 snapshot schema.

Phase 7 owns ct_extraction_run and ct_published_snapshot.  Revision 002
verifies that bootstrap contract before adding only its own columns and
objects.  Apply it before enabling Phase 8 persistence services.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PREREQUISITE_SQL = """
DO $$
DECLARE
    missing_requirement TEXT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'ct_extraction_run'
          AND c.relkind IN ('r', 'p')
    ) OR NOT EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'ct_published_snapshot'
          AND c.relkind IN ('r', 'p')
    ) THEN
        RAISE EXCEPTION
            'Phase 8 migration requires the Phase 7 snapshot schema tables';
    END IF;

    SELECT format('%s.%s must use PostgreSQL type %s',
                  required.table_name, required.column_name, required.udt_name)
    INTO missing_requirement
    FROM (
        VALUES
            ('ct_extraction_run', 'run_id', 'uuid'),
            ('ct_extraction_run', 'company_id', 'int8'),
            ('ct_extraction_run', 'status', 'text'),
            ('ct_extraction_run', 'started_at', 'timestamptz'),
            ('ct_extraction_run', 'completed_at', 'timestamptz'),
            ('ct_extraction_run', 'finished_at', 'timestamptz'),
            ('ct_extraction_run', 'published_at', 'timestamptz'),
            ('ct_published_snapshot', 'company_id', 'int8'),
            ('ct_published_snapshot', 'run_id', 'uuid'),
            ('ct_published_snapshot', 'published_at', 'timestamptz')
    ) AS required(table_name, column_name, udt_name)
    LEFT JOIN information_schema.columns actual
      ON actual.table_schema = 'public'
     AND actual.table_name = required.table_name
     AND actual.column_name = required.column_name
    WHERE actual.column_name IS NULL
       OR actual.udt_name <> required.udt_name
    ORDER BY required.table_name, required.column_name
    LIMIT 1;

    IF missing_requirement IS NOT NULL THEN
        RAISE EXCEPTION
            'Phase 8 migration requires a valid Phase 7 prerequisite column: %',
            missing_requirement;
    END IF;
END $$;
"""


OWNERSHIP_SQL = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'ct_extraction_run'
          AND column_name = ANY (ARRAY[
              'requested_at', 'stage', 'stage_started_at', 'heartbeat_at',
              'attempt', 'retry_of_run_id', 'base_snapshot_run_id',
              'failure_class', 'progress', 'selected_domains', 'last_error_at'
          ])
    ) THEN
        RAISE EXCEPTION
            'Phase 8 revision 002 column already exists; refusing to claim ownership';
    END IF;

    IF to_regclass('public.ct_control_tower_watermark') IS NOT NULL
       OR to_regclass('public.ct_parent_reconciliation_queue') IS NOT NULL
       OR to_regclass('public.ct_parent_reconciliation_cursor') IS NOT NULL THEN
        RAISE EXCEPTION
            'Phase 8 revision 002 table already exists; refusing to claim ownership';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = ANY (ARRAY[
              'idx_ct_watermark_checked',
              'idx_ct_parent_reconcile_queue_pending',
              'idx_ct_extraction_run_retry'
          ])
    ) OR EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        JOIN pg_class relation_row ON relation_row.oid = constraint_row.conrelid
        JOIN pg_namespace n ON n.oid = relation_row.relnamespace
        WHERE n.nspname = 'public'
          AND constraint_row.conname = ANY (ARRAY[
              'pk_ct_control_tower_watermark',
              'pk_ct_parent_reconciliation_queue',
              'pk_ct_parent_reconciliation_cursor',
              'ck_ct_watermark_company_positive',
              'ck_ct_watermark_model_nonempty',
              'ck_ct_watermark_overlap_nonnegative',
              'ck_ct_watermark_status',
              'ck_ct_watermark_tuple_coherent',
              'ck_ct_queue_company_positive',
              'ck_ct_queue_parent_id_positive',
              'ck_ct_queue_status',
              'ck_ct_queue_generation_nonnegative',
              'ck_ct_queue_attempts_nonnegative',
              'ck_ct_cursor_company_positive',
              'ck_ct_cursor_status',
              'ck_ct_run_failure_class',
              'ck_ct_run_retry_not_self',
              'fk_ct_run_retry_of',
              'fk_ct_run_base_snapshot',
              'fk_ct_watermark_published_run',
              'fk_ct_reconcile_source_run'
          ])
    ) THEN
        RAISE EXCEPTION
            'Phase 8 revision 002 constraint or index already exists; refusing to claim ownership';
    END IF;
END $$;
"""


def upgrade() -> None:
    """Add Phase 8 objects only after the complete Phase 7 contract check."""
    op.execute(PREREQUISITE_SQL)
    op.execute(OWNERSHIP_SQL)

    for statement in (
        "ALTER TABLE public.ct_extraction_run ADD COLUMN requested_at TIMESTAMPTZ",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN stage TEXT",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN stage_started_at TIMESTAMPTZ",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN heartbeat_at TIMESTAMPTZ",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN attempt INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN retry_of_run_id UUID",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN base_snapshot_run_id UUID",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN failure_class TEXT",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN progress JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN selected_domains JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE public.ct_extraction_run ADD COLUMN last_error_at TIMESTAMPTZ",
        "CREATE TABLE public.ct_control_tower_watermark ("
        "company_id BIGINT NOT NULL, model TEXT NOT NULL, "
        "last_successful_write_date TIMESTAMPTZ, last_successful_id BIGINT, "
        "overlap_seconds INTEGER NOT NULL DEFAULT 0, published_run_id UUID, "
        "checked_at TIMESTAMPTZ, status TEXT NOT NULL DEFAULT 'BOOTSTRAP_REQUIRED', "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "CONSTRAINT pk_ct_control_tower_watermark PRIMARY KEY (company_id, model), "
        "CONSTRAINT ck_ct_watermark_company_positive CHECK (company_id > 0), "
        "CONSTRAINT ck_ct_watermark_model_nonempty CHECK (length(btrim(model)) > 0), "
        "CONSTRAINT ck_ct_watermark_overlap_nonnegative CHECK (overlap_seconds >= 0), "
        "CONSTRAINT ck_ct_watermark_status CHECK (status IN ('BOOTSTRAP_REQUIRED', 'READY')), "
        "CONSTRAINT ck_ct_watermark_tuple_coherent CHECK ("
        "(status = 'BOOTSTRAP_REQUIRED' AND last_successful_write_date IS NULL "
        " AND last_successful_id IS NULL AND published_run_id IS NULL) OR "
        "(status = 'READY' AND last_successful_write_date IS NOT NULL "
        " AND last_successful_id IS NOT NULL AND published_run_id IS NOT NULL)), "
        "CONSTRAINT ck_ct_watermark_id_positive CHECK ("
        "last_successful_id IS NULL OR last_successful_id > 0))",
        "CREATE INDEX idx_ct_watermark_checked "
        "ON public.ct_control_tower_watermark (company_id, checked_at, model)",
        "CREATE TABLE public.ct_parent_reconciliation_queue ("
        "company_id BIGINT NOT NULL, parent_model TEXT NOT NULL, "
        "parent_id BIGINT NOT NULL, child_model TEXT NOT NULL, reason TEXT NOT NULL, "
        "status TEXT NOT NULL DEFAULT 'PENDING', source_run_id UUID, "
        "generation BIGINT NOT NULL DEFAULT 1, claimed_generation BIGINT, "
        "claimed_by TEXT, attempts INTEGER NOT NULL DEFAULT 0, "
        "last_checked_at TIMESTAMPTZ, last_touched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "CONSTRAINT pk_ct_parent_reconciliation_queue PRIMARY KEY "
        "(company_id, parent_model, parent_id, child_model), "
        "CONSTRAINT ck_ct_queue_company_positive CHECK (company_id > 0), "
        "CONSTRAINT ck_ct_queue_parent_id_positive CHECK (parent_id > 0), "
        "CONSTRAINT ck_ct_queue_status CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED')), "
        "CONSTRAINT ck_ct_queue_generation_nonnegative CHECK (generation > 0), "
        "CONSTRAINT ck_ct_queue_attempts_nonnegative CHECK (attempts >= 0))",
        "CREATE INDEX idx_ct_parent_reconcile_queue_pending "
        "ON public.ct_parent_reconciliation_queue (company_id, status, last_touched_at)",
        "CREATE TABLE public.ct_parent_reconciliation_cursor ("
        "company_id BIGINT NOT NULL, parent_model TEXT NOT NULL, child_model TEXT NOT NULL, "
        "last_parent_id BIGINT, batch_size INTEGER NOT NULL DEFAULT 500, "
        "version BIGINT NOT NULL DEFAULT 0, last_sweep_started_at TIMESTAMPTZ, "
        "last_sweep_completed_at TIMESTAMPTZ, status TEXT NOT NULL DEFAULT 'READY', "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "CONSTRAINT pk_ct_parent_reconciliation_cursor PRIMARY KEY "
        "(company_id, parent_model, child_model), "
        "CONSTRAINT ck_ct_cursor_company_positive CHECK (company_id > 0), "
        "CONSTRAINT ck_ct_cursor_status CHECK (status IN ('READY', 'RUNNING')))",
        "CREATE INDEX idx_ct_extraction_run_retry "
        "ON public.ct_extraction_run (retry_of_run_id)",
    ):
        op.execute(statement)

    for statement in (
        "ALTER TABLE public.ct_extraction_run ADD CONSTRAINT ck_ct_run_failure_class "
        "CHECK (status NOT IN ('REQUESTED', 'PREPARING', 'DETECTING_CHANGES', "
        "'FETCHING', 'RECONCILING', 'VALIDATING', 'REFRESHING_DERIVED_DATA', "
        "'PUBLISHING', 'SUCCEEDED', 'SUCCEEDED_NO_CHANGES', "
        "'FAILED_TRANSIENT', 'FAILED_PERMANENT', 'INTERRUPTED', 'ABORTED') OR "
        "((status = 'FAILED_TRANSIENT' AND failure_class = 'TRANSIENT') OR "
        "(status = 'FAILED_PERMANENT' AND failure_class = 'PERMANENT') OR "
        "(status = 'INTERRUPTED' AND failure_class = 'INTERRUPTED') OR "
        "(status = 'ABORTED' AND failure_class = 'ABORTED') OR "
        "(status IN ('REQUESTED', 'PREPARING', 'DETECTING_CHANGES', 'FETCHING', "
        "'RECONCILING', 'VALIDATING', 'REFRESHING_DERIVED_DATA', 'PUBLISHING', "
        "'SUCCEEDED', 'SUCCEEDED_NO_CHANGES') AND failure_class IS NULL)))",
        "ALTER TABLE public.ct_extraction_run ADD CONSTRAINT ck_ct_run_retry_not_self "
        "CHECK (retry_of_run_id IS NULL OR retry_of_run_id <> run_id)",
        "ALTER TABLE public.ct_extraction_run ADD CONSTRAINT fk_ct_run_retry_of "
        "FOREIGN KEY (retry_of_run_id) REFERENCES public.ct_extraction_run(run_id) "
        "ON DELETE RESTRICT",
        "ALTER TABLE public.ct_extraction_run ADD CONSTRAINT fk_ct_run_base_snapshot "
        "FOREIGN KEY (base_snapshot_run_id) REFERENCES public.ct_extraction_run(run_id) "
        "ON DELETE RESTRICT",
        "ALTER TABLE public.ct_control_tower_watermark ADD CONSTRAINT fk_ct_watermark_published_run "
        "FOREIGN KEY (published_run_id) REFERENCES public.ct_extraction_run(run_id) "
        "ON DELETE RESTRICT",
        "ALTER TABLE public.ct_parent_reconciliation_queue ADD CONSTRAINT fk_ct_reconcile_source_run "
        "FOREIGN KEY (source_run_id) REFERENCES public.ct_extraction_run(run_id) "
        "ON DELETE RESTRICT",
    ):
        op.execute(statement)


def downgrade() -> None:
    """Remove only revision-002 objects and preserve all Phase 7 evidence."""
    for statement in (
        "ALTER TABLE public.ct_parent_reconciliation_queue DROP CONSTRAINT fk_ct_reconcile_source_run",
        "ALTER TABLE public.ct_control_tower_watermark DROP CONSTRAINT fk_ct_watermark_published_run",
        "ALTER TABLE public.ct_extraction_run DROP CONSTRAINT fk_ct_run_base_snapshot",
        "ALTER TABLE public.ct_extraction_run DROP CONSTRAINT fk_ct_run_retry_of",
        "ALTER TABLE public.ct_extraction_run DROP CONSTRAINT ck_ct_run_retry_not_self",
        "ALTER TABLE public.ct_extraction_run DROP CONSTRAINT ck_ct_run_failure_class",
        "DROP INDEX public.idx_ct_extraction_run_retry",
        "DROP INDEX public.idx_ct_parent_reconcile_queue_pending",
        "DROP INDEX public.idx_ct_watermark_checked",
        "DROP TABLE public.ct_parent_reconciliation_cursor",
        "DROP TABLE public.ct_parent_reconciliation_queue",
        "DROP TABLE public.ct_control_tower_watermark",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN last_error_at",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN selected_domains",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN progress",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN failure_class",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN base_snapshot_run_id",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN retry_of_run_id",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN attempt",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN heartbeat_at",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN stage_started_at",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN stage",
        "ALTER TABLE public.ct_extraction_run DROP COLUMN requested_at",
    ):
        op.execute(statement)
