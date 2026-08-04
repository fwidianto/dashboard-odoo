"""Runtime readiness check for Phase 8 persistence services."""

from __future__ import annotations

from sqlalchemy import text


class Phase8SchemaNotReady(RuntimeError):
    """Raised when revision 002 is not available to a Phase 8 service."""


_READY_MESSAGE = (
    "Phase 8 persistence requires Alembic revision 002 and its schema objects; "
    "apply revision 002 before using Phase 8 services."
)


def ensure_phase8_schema_ready(postgres_client) -> None:
    """Check revision 002 once at a Phase 8 service boundary.

    This function intentionally does not run migrations.  Importing this module
    is side-effect free; the query happens only when a persistence service is
    initialized.
    """
    try:
        with postgres_client.engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            ).scalar()
            if str(revision) not in {"002", "003", "004"}:
                raise Phase8SchemaNotReady(_READY_MESSAGE)
            ready = conn.execute(
                text(
                    """
                    SELECT
                        to_regclass('public.ct_control_tower_watermark') IS NOT NULL AS watermark,
                        to_regclass('public.ct_parent_reconciliation_queue') IS NOT NULL AS queue,
                        to_regclass('public.ct_parent_reconciliation_cursor') IS NOT NULL AS cursor,
                        EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'ct_extraction_run'
                              AND column_name = 'base_snapshot_run_id'
                        ) AS base_snapshot,
                        EXISTS (
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'ct_extraction_run'
                              AND column_name = 'failure_class'
                        ) AS failure_class
                    """
                )
            ).mappings().one()
            if not all(bool(ready.get(key)) for key in ("watermark", "queue", "cursor", "base_snapshot", "failure_class")):
                raise Phase8SchemaNotReady(_READY_MESSAGE)
    except Phase8SchemaNotReady:
        raise
    except Exception as exc:
        raise Phase8SchemaNotReady(_READY_MESSAGE) from exc


def ensure_phase8_detection_schema_ready(postgres_client) -> None:
    """Require revision 003 and both durable change-detection tables."""
    ensure_phase8_schema_ready(postgres_client)
    try:
        with postgres_client.engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            ).scalar()
            if str(revision) not in {"003", "004"}:
                raise Phase8SchemaNotReady(
                    "Change detection requires Alembic revision 003 and its manifest tables."
                )
            ready = conn.execute(text("""
                SELECT to_regclass('public.ct_change_detection_run') IS NOT NULL AS header,
                       to_regclass('public.ct_change_manifest') IS NOT NULL AS manifest
            """)).mappings().one()
            if not ready["header"] or not ready["manifest"]:
                raise Phase8SchemaNotReady("Change detection manifest schema is not ready.")
    except Phase8SchemaNotReady:
        raise
    except Exception as exc:
        raise Phase8SchemaNotReady("Change detection manifest schema is not ready.") from exc

def ensure_phase8_fetch_schema_ready(postgres_client) -> None:
    """Require revision 004 and the durable fetch/apply evidence tables."""
    ensure_phase8_detection_schema_ready(postgres_client)
    try:
        with postgres_client.engine.connect() as conn:
            revision = conn.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1")
            ).scalar()
            if str(revision) != "004":
                raise Phase8SchemaNotReady(
                    "Fetch/apply requires Alembic revision 004 and its evidence tables."
                )
            ready = conn.execute(text("""
                SELECT to_regclass('public.ct_fetch_apply_run') IS NOT NULL AS header,
                       to_regclass('public.ct_fetch_apply_evidence') IS NOT NULL AS evidence,
                       to_regclass('public.ct_fetch_apply_batch') IS NOT NULL AS batch
            """)).mappings().one()
            if not ready["header"] or not ready["evidence"] or not ready["batch"]:
                raise Phase8SchemaNotReady("Fetch/apply evidence schema is not ready.")
    except Phase8SchemaNotReady:
        raise
    except Exception as exc:
        raise Phase8SchemaNotReady("Fetch/apply evidence schema is not ready.") from exc
