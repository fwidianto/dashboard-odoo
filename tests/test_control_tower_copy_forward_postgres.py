"""Disposable PostgreSQL tests for Phase 8B-2A candidate copy-forward."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import logging
from threading import Event
import time

import pytest
from sqlalchemy import create_engine, text

from src.control_tower.copy_forward import (
    SNAPSHOT_TABLE_COLUMNS,
    SNAPSHOT_TABLE_NAMES,
    CandidateSnapshotCopyForwardService,
    CopyForwardPartialError,
    CopyForwardStaleError,
    CopyForwardValidationError,
)
from src.control_tower.progress import parse_progress_json
from src.control_tower.refresh_state import RefreshRunStateService
from tests.test_control_tower_refresh_contracts_postgres import (
    PHASE7_BASE_RUN_ID,
    POSTGRES_URL,
    _base_run,
    _bootstrap_phase7,
    _publish_pointer,
    _upgrade,
)


pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Set CT_TEST_POSTGRES_URL to a disposable PostgreSQL URL.",
)


def _client(engine):
    return type("Client", (), {"engine": engine})()


def _candidate(engine, *, company_id: int = 3) -> str:
    service = RefreshRunStateService(_client(engine))
    run = service.create_run(
        company_id=company_id,
        selected_domains=["commercial"],
        now=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
    )
    service.transition(
        run["run_id"],
        "PREPARING",
        now=datetime(2026, 1, 1, 11, 1, tzinfo=timezone.utc),
    )
    return run["run_id"]


def _copy_service(engine, *, copy_hook=None) -> CandidateSnapshotCopyForwardService:
    return CandidateSnapshotCopyForwardService(
        _client(engine),
        copy_hook=copy_hook,
    )


def _counts(engine, run_id: str) -> dict[str, int]:
    with engine.connect() as conn:
        return {
            table_name: conn.execute(
                text(
                    f"""
                    SELECT COUNT(*)
                    FROM public.{table_name}
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": run_id},
            ).scalar_one()
            for table_name in SNAPSHOT_TABLE_NAMES
        }


def _rows(engine, table_name: str, run_id: str):
    columns = dict(SNAPSHOT_TABLE_COLUMNS)[table_name]
    order = ", ".join(str(index) for index in range(1, len(columns) + 1))
    with engine.connect() as conn:
        return conn.execute(
            text(
                f"""
                SELECT {", ".join(columns)}
                FROM public.{table_name}
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                ORDER BY {order}
                """
            ),
            {"run_id": run_id},
        ).mappings().all()


def _full_rows(engine, table_name: str, run_id: str):
    columns = dict(SNAPSHOT_TABLE_COLUMNS)[table_name]
    order = ", ".join(str(index) for index in range(1, len(columns) + 2))
    with engine.connect() as conn:
        return conn.execute(
            text(
                f"""
                SELECT extraction_run_id::text AS extraction_run_id,
                       {", ".join(columns)}
                FROM public.{table_name}
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                ORDER BY {order}
                """
            ),
            {"run_id": run_id},
        ).mappings().all()


def _run_ids(engine, table_name: str, run_id: str) -> list[str]:
    with engine.connect() as conn:
        return [
            row[0]
            for row in conn.execute(
                text(
                    f"""
                    SELECT DISTINCT extraction_run_id::text
                    FROM public.{table_name}
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": run_id},
            ).all()
        ]


def _set_progress_state(
    engine,
    candidate_id: str,
    source_id: str,
    *,
    progress: dict,
    stage_timings: dict,
    stage: str = "DETECTING_CHANGES",
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE public.ct_extraction_run
                SET status = :stage,
                    stage = :stage,
                    base_snapshot_run_id = CAST(:source_id AS UUID),
                    progress = CAST(:progress AS JSONB),
                    stage_timings = CAST(:stage_timings AS JSONB)
                WHERE run_id = CAST(:candidate_id AS UUID)
                """
            ),
            {
                "candidate_id": candidate_id,
                "source_id": source_id,
                "stage": stage,
                "progress": json.dumps(progress),
                "stage_timings": json.dumps(stage_timings),
            },
        )


def _complete_progress(candidate_id: str, source_id: str) -> tuple[dict, dict]:
    started = "2026-01-01T11:00:00+00:00"
    native_completed = "2026-01-01T11:00:01+00:00"
    links_completed = "2026-01-01T11:00:02+00:00"
    finished = "2026-01-01T11:00:03+00:00"
    completed_at = {
        "ct_document_link": links_completed,
        "ct_native_record_snapshot": native_completed,
    }
    progress = {
        "copy_forward_status": "COMPLETE",
        "copy_forward_source_run_id": source_id,
        "copy_forward_candidate_run_id": candidate_id,
        "copy_forward_tables_planned": sorted(SNAPSHOT_TABLE_NAMES),
        "copy_forward_tables_completed": sorted(SNAPSHOT_TABLE_NAMES),
        "copy_forward_rows": {
            "ct_document_link": 1,
            "ct_native_record_snapshot": 1,
        },
        "copy_forward_total_rows": 2,
        "copy_forward_current_table": SNAPSHOT_TABLE_NAMES[-1],
        "copy_forward_started_at": started,
        "copy_forward_finished_at": finished,
        "copy_forward_table_completed_at": completed_at,
        "copy_forward_elapsed_seconds": 3.0,
    }
    stage_timings = {
        "copy_forward_seconds": 3.0,
        "copy_forward_rows": progress["copy_forward_rows"],
        "copy_forward_source_run_id": source_id,
        "copy_forward_started_at": started,
        "copy_forward_finished_at": finished,
        "copy_forward_table_completed_at": completed_at,
    }
    return progress, stage_timings


@pytest.fixture
def postgres_engine():
    engine = create_engine(POSTGRES_URL, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            existing = conn.execute(
                text(
                    """
                    SELECT relname
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relname IN (
                          'ct_extraction_run', 'ct_published_snapshot',
                          'ct_native_record_snapshot', 'ct_document_link',
                          'ct_control_tower_watermark',
                          'ct_parent_reconciliation_queue',
                          'ct_parent_reconciliation_cursor',
                          'alembic_version'
                      )
                    """
                )
            ).scalars().all()
        if existing:
            pytest.skip(
                "CT_TEST_POSTGRES_URL must point to an empty disposable database."
            )
        _bootstrap_phase7(engine)
        _upgrade(engine)
    except Exception:
        engine.dispose()
        raise
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            for table in (
                "ct_purchase_order_date_enrichment",
                "ct_purchase_order_date_enrichment_execution",
                "ct_finding",
                "ct_control_tower_watermark",
                "ct_parent_reconciliation_queue",
                "ct_parent_reconciliation_cursor",
                "ct_published_snapshot",
                "ct_native_record_snapshot",
                "ct_document_link",
                "ct_extraction_run",
                "alembic_version",
            ):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
        engine.dispose()


def test_successful_copy_forward_is_complete_truthful_and_unpublished(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_native_record_snapshot (
                    extraction_run_id, model, record_id, document_number, state,
                    company_id, company_name, write_date, payload, extracted_at
                )
                VALUES (
                    CAST(:run_id AS UUID), 'sale.order', 700010, NULL, NULL,
                    NULL, NULL, :write_date, CAST(:payload AS JSONB), :extracted_at
                )
                """
            ),
            {
                "run_id": PHASE7_BASE_RUN_ID,
                "write_date": datetime(2026, 1, 2, 3, 4, 5, 678901),
                "payload": json.dumps(
                    {"id": 700010, "nested": {"items": [1, None, "x"]}}
                ),
                "extracted_at": datetime(
                    2026, 1, 2, 3, 4, 5, 678901, tzinfo=timezone.utc
                ),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO public.ct_document_link (
                    extraction_run_id, link_type, parent_model, parent_id,
                    parent_number, child_model, child_id, child_number,
                    source_field, confidence, evidence, extracted_at
                )
                VALUES (
                    CAST(:run_id AS UUID), 'SO_TO_LINE', 'sale.order', 700010,
                    NULL, 'sale.order.line', 700011, NULL, 'order_id', 'MEDIUM',
                    CAST(:evidence AS JSONB), :extracted_at
                )
                """
            ),
            {
                "run_id": PHASE7_BASE_RUN_ID,
                "evidence": json.dumps(
                    {"source": "nullable-test", "values": [None, {"ok": True}]}
                ),
                "extracted_at": datetime(
                    2026, 1, 2, 3, 4, 5, 678901, tzinfo=timezone.utc
                ),
            },
        )
    with engine.connect() as conn:
        source_before = {
            table_name: conn.execute(
                text(
                    f"""
                    SELECT COUNT(*) FROM public.{table_name}
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": PHASE7_BASE_RUN_ID},
            ).scalar_one()
            for table_name in SNAPSHOT_TABLE_NAMES
        }
        pointer_before = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot WHERE company_id = 3"
            )
        ).scalar_one()
    source_rows_before = {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    }

    result = _copy_service(engine).copy_forward(candidate_id, company_id=3)

    assert result == {
        "run_id": candidate_id,
        "status": "DETECTING_CHANGES",
        "source_run_id": PHASE7_BASE_RUN_ID,
        "base_snapshot_run_id": PHASE7_BASE_RUN_ID,
        "tables": source_before,
        "total_rows": sum(source_before.values()),
        "idempotent": False,
    }
    assert _counts(engine, candidate_id) == source_before
    with engine.connect() as conn:
        source_after = {
            table_name: conn.execute(
                text(
                    f"""
                    SELECT COUNT(*) FROM public.{table_name}
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": PHASE7_BASE_RUN_ID},
            ).scalar_one()
            for table_name in SNAPSHOT_TABLE_NAMES
        }
        pointer_after = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot WHERE company_id = 3"
            )
        ).scalar_one()
        candidate = conn.execute(
            text(
                """
                SELECT status, stage, base_snapshot_run_id::text, published_at, progress
                FROM public.ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id},
        ).mappings().one()
        watermark_count = conn.execute(
            text("SELECT COUNT(*) FROM public.ct_control_tower_watermark")
        ).scalar_one()
    source_snapshot = _rows(
        engine, "ct_native_record_snapshot", PHASE7_BASE_RUN_ID
    )
    source_rows_after = {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    }
    candidate_snapshot = _rows(
        engine, "ct_native_record_snapshot", candidate_id
    )
    source_links = _rows(engine, "ct_document_link", PHASE7_BASE_RUN_ID)
    candidate_links = _rows(engine, "ct_document_link", candidate_id)
    progress = parse_progress_json(candidate["progress"])
    assert source_after == source_before
    assert source_rows_after == source_rows_before
    assert pointer_before == pointer_after == PHASE7_BASE_RUN_ID
    assert candidate["status"] == "DETECTING_CHANGES"
    assert candidate["stage"] == "DETECTING_CHANGES"
    assert candidate["base_snapshot_run_id"] == PHASE7_BASE_RUN_ID
    assert candidate["published_at"] is None
    assert watermark_count == 0
    assert source_snapshot == candidate_snapshot
    assert source_links == candidate_links
    assert _run_ids(engine, "ct_native_record_snapshot", PHASE7_BASE_RUN_ID) == [
        PHASE7_BASE_RUN_ID
    ]
    assert _run_ids(engine, "ct_native_record_snapshot", candidate_id) == [candidate_id]
    assert _run_ids(engine, "ct_document_link", PHASE7_BASE_RUN_ID) == [
        PHASE7_BASE_RUN_ID
    ]
    assert _run_ids(engine, "ct_document_link", candidate_id) == [candidate_id]
    assert progress["copy_forward_status"] == "COMPLETE"
    assert progress["copy_forward_source_run_id"] == PHASE7_BASE_RUN_ID
    assert progress["copy_forward_candidate_run_id"] == candidate_id
    assert progress["copy_forward_tables_planned"] == sorted(SNAPSHOT_TABLE_NAMES)
    assert progress["copy_forward_tables_completed"] == sorted(SNAPSHOT_TABLE_NAMES)
    assert progress["copy_forward_rows"] == source_before
    assert progress["copy_forward_total_rows"] == sum(source_before.values())
    assert set(progress["copy_forward_table_completed_at"]) == set(SNAPSHOT_TABLE_NAMES)
    assert progress["copy_forward_finished_at"] != progress["copy_forward_started_at"]
    started = datetime.fromisoformat(progress["copy_forward_started_at"])
    finished = datetime.fromisoformat(progress["copy_forward_finished_at"])
    assert progress["copy_forward_elapsed_seconds"] == round(
        (finished - started).total_seconds(), 6
    )


def test_no_published_snapshot_and_invalid_source_fail_closed(postgres_engine):
    engine = postgres_engine
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM public.ct_published_snapshot"))
    candidate_without_source = _candidate(engine)
    with pytest.raises(CopyForwardValidationError, match="No trusted"):
        _copy_service(engine).copy_forward(candidate_without_source, company_id=3)

    invalid_source = "00000000-0000-4000-8000-000000000201"
    _base_run(engine, invalid_source, status="FAILED_PERMANENT")
    _publish_pointer(engine, invalid_source)
    invalid_candidate = _candidate(engine)
    with pytest.raises(CopyForwardValidationError, match="completed"):
        _copy_service(engine).copy_forward(invalid_candidate, company_id=3)
    assert _counts(engine, invalid_candidate) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }


def test_exact_native_value_mismatch_equal_keys_is_rejected(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)

    def change_payload(table_name, conn):
        if table_name == "ct_native_record_snapshot":
            conn.execute(
                text(
                    """
                    UPDATE public.ct_native_record_snapshot
                    SET payload = CAST(:payload AS JSONB)
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                      AND record_id = 700001
                    """
                ),
                {"run_id": candidate_id, "payload": '{"changed": true}'},
            )

    with pytest.raises(CopyForwardPartialError, match="Exact copy-forward equality"):
        _copy_service(engine, copy_hook=change_payload).copy_forward(
            candidate_id, company_id=3
        )
    assert _counts(engine, candidate_id) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }


def test_adversarial_equal_counts_wrong_business_key_is_rejected(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)

    def change_key(table_name, conn):
        if table_name == "ct_native_record_snapshot":
            conn.execute(
                text(
                    """
                    UPDATE public.ct_native_record_snapshot
                    SET record_id = 799999
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                      AND record_id = 700001
                    """
                ),
                {"run_id": candidate_id},
            )

    with pytest.raises(CopyForwardPartialError, match="Exact copy-forward equality"):
        _copy_service(engine, copy_hook=change_key).copy_forward(
            candidate_id, company_id=3
        )
    assert _counts(engine, candidate_id) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }


def test_exact_document_link_value_mismatch_is_rejected(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)

    def change_link(table_name, conn):
        if table_name == "ct_document_link":
            conn.execute(
                text(
                    """
                    UPDATE public.ct_document_link
                    SET evidence = CAST(:evidence AS JSONB)
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                      AND parent_id = 700001
                    """
                ),
                {"run_id": candidate_id, "evidence": '{"changed": true}'},
            )

    with pytest.raises(CopyForwardPartialError, match="Exact copy-forward equality"):
        _copy_service(engine, copy_hook=change_link).copy_forward(
            candidate_id, company_id=3
        )


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_missing_or_unexpected_candidate_rows_are_rejected(postgres_engine, mutation):
    engine = postgres_engine
    candidate_id = _candidate(engine)

    def mutate_rows(table_name, conn):
        if table_name != "ct_native_record_snapshot":
            return
        if mutation == "missing":
            conn.execute(
                text(
                    """
                    DELETE FROM public.ct_native_record_snapshot
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": candidate_id},
            )
            return
        conn.execute(
            text(
                """
                INSERT INTO public.ct_native_record_snapshot (
                    extraction_run_id, model, record_id, document_number, state,
                    company_id, company_name, write_date, payload, extracted_at
                )
                VALUES (
                    CAST(:run_id AS UUID), 'sale.order', 799999, 'SO-EXTRA',
                    'sale', 3, 'PT Nobi Putra Angkasa', :write_date,
                    CAST(:payload AS JSONB), :extracted_at
                )
                """
            ),
            {
                "run_id": candidate_id,
                "write_date": datetime(2026, 1, 1, 9, 55),
                "payload": '{"id": 799999, "name": "SO-EXTRA"}',
                "extracted_at": datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
            },
        )

    with pytest.raises(CopyForwardPartialError, match="Exact copy-forward equality"):
        _copy_service(engine, copy_hook=mutate_rows).copy_forward(
            candidate_id, company_id=3
        )
    assert _counts(engine, candidate_id) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }


def test_duplicate_multiplicity_mismatch_with_equal_counts_is_rejected(postgres_engine):
    engine = postgres_engine
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE public.ct_native_record_snapshot "
                "DROP CONSTRAINT IF EXISTS ct_native_record_snapshot_pkey"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO public.ct_native_record_snapshot (
                    extraction_run_id, model, record_id, document_number, state,
                    company_id, company_name, write_date, payload, extracted_at
                )
                SELECT extraction_run_id, model, record_id, document_number, state,
                       company_id, company_name, write_date, payload, extracted_at
                FROM public.ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": PHASE7_BASE_RUN_ID},
        )
    candidate_id = _candidate(engine)

    def change_one_duplicate(table_name, conn):
        if table_name == "ct_native_record_snapshot":
            conn.execute(
                text(
                    """
                    UPDATE public.ct_native_record_snapshot
                    SET record_id = 799999
                    WHERE ctid = (
                        SELECT ctid
                        FROM public.ct_native_record_snapshot
                        WHERE extraction_run_id = CAST(:run_id AS UUID)
                        LIMIT 1
                    )
                    """
                ),
                {"run_id": candidate_id},
            )

    with pytest.raises(CopyForwardPartialError, match="Exact copy-forward equality"):
        _copy_service(engine, copy_hook=change_one_duplicate).copy_forward(
            candidate_id, company_id=3
        )


def test_company_mismatch_and_stale_base_are_rejected(postgres_engine):
    engine = postgres_engine
    mismatched_candidate = _candidate(engine, company_id=4)
    with pytest.raises(CopyForwardValidationError, match="different company"):
        _copy_service(engine).copy_forward(mismatched_candidate, company_id=3)
    assert _counts(engine, mismatched_candidate) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }

    stale_candidate = _candidate(engine)
    newer_source = "00000000-0000-4000-8000-000000000202"
    _base_run(engine, newer_source)
    _publish_pointer(engine, newer_source)
    with pytest.raises(CopyForwardStaleError, match="stale"):
        _copy_service(engine).copy_forward(stale_candidate, company_id=3)
    with engine.connect() as conn:
        pointer = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot WHERE company_id = 3"
            )
        ).scalar_one()
        candidate_status = conn.execute(
            text(
                "SELECT status FROM public.ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)"
            ),
            {"run_id": stale_candidate},
        ).scalar_one()
    assert pointer == newer_source
    assert candidate_status == "FAILED_PERMANENT"


def test_forged_complete_progress_without_rows_is_rejected(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    progress, stage_timings = _complete_progress(candidate_id, PHASE7_BASE_RUN_ID)
    _set_progress_state(
        engine,
        candidate_id,
        PHASE7_BASE_RUN_ID,
        progress=progress,
        stage_timings=stage_timings,
    )

    with pytest.raises(CopyForwardPartialError, match="Exact copy-forward equality"):
        _copy_service(engine).copy_forward(candidate_id, company_id=3)
    assert _counts(engine, candidate_id) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }


@pytest.mark.parametrize("stage", [None, "NOT_A_STAGE"])
def test_missing_or_malformed_stage_is_rejected(postgres_engine, stage):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE public.ct_extraction_run
                SET stage = :stage
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id, "stage": stage},
        )

    with pytest.raises(CopyForwardValidationError, match="stage"):
        _copy_service(engine).copy_forward(candidate_id, company_id=3)


def test_arbitrary_candidate_identifier_is_rejected_at_service_boundary(postgres_engine):
    with pytest.raises(CopyForwardValidationError, match="UUID"):
        _copy_service(postgres_engine).copy_forward("candidate", company_id=3)


def test_missing_candidate_run_is_rejected(postgres_engine):
    missing_id = "00000000-0000-4000-8000-000000000205"
    with pytest.raises(CopyForwardValidationError, match="not found"):
        _copy_service(postgres_engine).copy_forward(missing_id, company_id=3)


def test_unpublished_source_without_published_at_is_rejected(postgres_engine):
    engine = postgres_engine
    source_id = "00000000-0000-4000-8000-000000000203"
    _base_run(engine, source_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE public.ct_extraction_run
                SET published_at = NULL
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": source_id},
        )
    _publish_pointer(engine, source_id)
    candidate_id = _candidate(engine)

    with pytest.raises(CopyForwardValidationError, match="publication"):
        _copy_service(engine).copy_forward(candidate_id, company_id=3)


def test_candidate_self_source_is_rejected(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE public.ct_published_snapshot
                SET run_id = CAST(:run_id AS UUID)
                WHERE company_id = 3
                """
            ),
            {"run_id": candidate_id},
        )

    with pytest.raises(CopyForwardValidationError, match="itself"):
        _copy_service(engine).copy_forward(candidate_id, company_id=3)


def test_null_base_snapshot_is_assigned_once_and_then_reused(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE public.ct_extraction_run
                SET base_snapshot_run_id = NULL
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id},
        )

    first = _copy_service(engine).copy_forward(candidate_id, company_id=3)
    with engine.connect() as conn:
        base = conn.execute(
            text(
                "SELECT base_snapshot_run_id::text FROM public.ct_extraction_run "
                "WHERE run_id = CAST(:run_id AS UUID)"
            ),
            {"run_id": candidate_id},
        ).scalar_one()
    second = _copy_service(engine).copy_forward(candidate_id, company_id=3)
    assert base == PHASE7_BASE_RUN_ID
    assert first["idempotent"] is False
    assert second["idempotent"] is True


def test_completed_candidate_cannot_adopt_a_newer_pointer(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    _copy_service(engine).copy_forward(candidate_id, company_id=3)
    newer_source = "00000000-0000-4000-8000-000000000206"
    _base_run(engine, newer_source)
    _publish_pointer(engine, newer_source)

    with pytest.raises(CopyForwardStaleError, match="stale"):
        _copy_service(engine).copy_forward(candidate_id, company_id=3)


def test_persisted_progress_identity_mismatch_fails_closed(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    progress, stage_timings = _complete_progress(candidate_id, "00000000-0000-4000-8000-000000000204")
    _set_progress_state(
        engine,
        candidate_id,
        PHASE7_BASE_RUN_ID,
        progress=progress,
        stage_timings=stage_timings,
    )

    with pytest.raises(CopyForwardPartialError, match="incomplete"):
        _copy_service(engine).copy_forward(candidate_id, company_id=3)


def test_second_call_is_idempotent_and_partial_candidate_fails_closed(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    service = _copy_service(engine)
    source_rows_before = {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    }
    with engine.connect() as conn:
        pointer_before = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot "
                "WHERE company_id = 3"
            )
        ).scalar_one()
    first = service.copy_forward(candidate_id, company_id=3)
    with engine.connect() as conn:
        first_metadata = conn.execute(
            text(
                """
                SELECT progress, stage_timings
                FROM public.ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id},
        ).mappings().one()
    second = service.copy_forward(candidate_id, company_id=3)
    with engine.connect() as conn:
        second_metadata = conn.execute(
            text(
                """
                SELECT progress, stage_timings
                FROM public.ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id},
        ).mappings().one()
        pointer_after = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot "
                "WHERE company_id = 3"
            )
        ).scalar_one()
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert second["tables"] == first["tables"]
    assert _counts(engine, candidate_id) == first["tables"]
    assert second_metadata["progress"] == first_metadata["progress"]
    assert second_metadata["stage_timings"] == first_metadata["stage_timings"]
    assert pointer_after == pointer_before == PHASE7_BASE_RUN_ID
    assert {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    } == source_rows_before

    partial_candidate = _candidate(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_native_record_snapshot (
                    extraction_run_id, model, record_id, document_number, state,
                    company_id, company_name, write_date, payload, extracted_at
                )
                SELECT CAST(:candidate AS UUID), model, record_id, document_number, state,
                       company_id, company_name, write_date, payload, extracted_at
                FROM public.ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:source AS UUID)
                """
            ),
            {"candidate": partial_candidate, "source": PHASE7_BASE_RUN_ID},
        )
    with pytest.raises(CopyForwardPartialError, match="partial"):
        service.copy_forward(partial_candidate, company_id=3)
    assert _counts(engine, partial_candidate) == {
        "ct_native_record_snapshot": 1,
        "ct_document_link": 0,
    }


def test_injected_failure_rolls_back_all_copy_rows_and_records_transient_failure(
    postgres_engine,
):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    source_rows_before = {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    }

    def fail_after_first_table(table_name, _conn):
        if table_name == "ct_native_record_snapshot":
            raise RuntimeError("controlled copy-forward failure")

    with pytest.raises(RuntimeError, match="controlled"):
        _copy_service(engine, copy_hook=fail_after_first_table).copy_forward(
            candidate_id,
            company_id=3,
        )

    assert _counts(engine, candidate_id) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }
    with engine.connect() as conn:
        candidate = conn.execute(
            text(
                """
                SELECT status, failure_class, published_at, progress, stage_timings
                FROM public.ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id},
        ).mappings().one()
        pointer = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot WHERE company_id = 3"
            )
        ).scalar_one()
        watermark_count = conn.execute(
            text("SELECT COUNT(*) FROM public.ct_control_tower_watermark")
        ).scalar_one()
    assert candidate["status"] == "FAILED_TRANSIENT"
    assert candidate["failure_class"] == "TRANSIENT"
    assert candidate["published_at"] is None
    assert parse_progress_json(candidate["progress"]) == {}
    assert candidate["stage_timings"] == {}
    assert pointer == PHASE7_BASE_RUN_ID
    assert watermark_count == 0
    assert {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    } == source_rows_before


def test_failure_recording_error_is_visible_without_masking_original(
    postgres_engine, caplog
):
    engine = postgres_engine
    candidate_id = _candidate(engine)

    def fail_during_copy(table_name, _conn):
        if table_name == "ct_native_record_snapshot":
            raise RuntimeError("original copy-forward failure")

    service = _copy_service(engine, copy_hook=fail_during_copy)

    def fail_recording(*_args, **_kwargs):
        raise RuntimeError("failure-recording-error")

    service._record_failure = fail_recording
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="original copy-forward failure"):
            service.copy_forward(candidate_id, company_id=3)

    assert "failure-recording-error" in caplog.text
    assert _counts(engine, candidate_id) == {
        table_name: 0 for table_name in SNAPSHOT_TABLE_NAMES
    }


def test_failed_copy_failure_recorder_cannot_overwrite_successful_retry(
    postgres_engine, caplog
):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    source_rows_before = {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    }
    with engine.connect() as conn:
        pointer_before = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot "
                "WHERE company_id = 3"
            )
        ).scalar_one()

    first_failure_ready = Event()
    release_failure_recorder = Event()
    failure_lock_attempted = Event()
    failure_recorded = Event()
    second_started = Event()
    release_second = Event()

    def fail_first_copy(table_name, _conn):
        if table_name == SNAPSHOT_TABLE_NAMES[0]:
            raise RuntimeError("first copy failure")

    first_service = _copy_service(engine, copy_hook=fail_first_copy)
    original_record_failure = first_service._record_failure

    def delayed_record_failure(*args, **kwargs):
        first_failure_ready.set()
        assert release_failure_recorder.wait(10)
        failure_lock_attempted.set()
        result = original_record_failure(*args, **kwargs)
        failure_recorded.set()
        return result

    first_service._record_failure = delayed_record_failure

    def hold_successful_retry(table_name, _conn):
        if table_name == SNAPSHOT_TABLE_NAMES[0]:
            second_started.set()
            assert release_second.wait(10)

    second_service = _copy_service(engine, copy_hook=hold_successful_retry)
    with caplog.at_level(logging.WARNING):
        with ThreadPoolExecutor(max_workers=2) as pool:
            first_future = pool.submit(
                first_service.copy_forward,
                candidate_id,
                company_id=3,
            )
            assert first_failure_ready.wait(10)
            second_future = pool.submit(
                second_service.copy_forward,
                candidate_id,
                company_id=3,
            )
            assert second_started.wait(10)
            release_failure_recorder.set()
            assert failure_lock_attempted.wait(10)
            assert not failure_recorded.is_set()
            release_second.set()
            second_result = second_future.result(timeout=15)
            with pytest.raises(RuntimeError, match="first copy failure"):
                first_future.result(timeout=15)

    assert failure_recorded.is_set()
    assert second_result["idempotent"] is False
    with engine.connect() as conn:
        candidate = conn.execute(
            text(
                """
                SELECT status, stage, failure_class, base_snapshot_run_id::text,
                       progress
                FROM public.ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id},
        ).mappings().one()
        pointer_after = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot "
                "WHERE company_id = 3"
            )
        ).scalar_one()
    assert candidate["status"] == "DETECTING_CHANGES"
    assert candidate["stage"] == "DETECTING_CHANGES"
    assert candidate["failure_class"] is None
    assert candidate["base_snapshot_run_id"] == PHASE7_BASE_RUN_ID
    assert parse_progress_json(candidate["progress"])["copy_forward_status"] == "COMPLETE"
    assert pointer_after == pointer_before == PHASE7_BASE_RUN_ID
    assert {
        table_name: _full_rows(engine, table_name, PHASE7_BASE_RUN_ID)
        for table_name in SNAPSHOT_TABLE_NAMES
    } == source_rows_before
    for table_name in SNAPSHOT_TABLE_NAMES:
        assert _rows(engine, table_name, candidate_id) == _rows(
            engine, table_name, PHASE7_BASE_RUN_ID
        )
    assert "advanced or changed before failure recording" in caplog.text


@pytest.mark.parametrize(
    ("status", "failure_class", "error_message"),
    [
        ("SUCCEEDED", None, None),
        ("FAILED_PERMANENT", "PERMANENT", "authoritative failure"),
    ],
)
def test_failure_recorder_preserves_later_authoritative_terminal_state(
    postgres_engine, status, failure_class, error_message
):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    recorder_ready = Event()
    release_recorder = Event()

    def fail_copy(table_name, _conn):
        if table_name == SNAPSHOT_TABLE_NAMES[0]:
            raise RuntimeError("original terminal-race failure")

    service = _copy_service(engine, copy_hook=fail_copy)
    original_record_failure = service._record_failure

    def delayed_record_failure(*args, **kwargs):
        recorder_ready.set()
        assert release_recorder.wait(10)
        return original_record_failure(*args, **kwargs)

    service._record_failure = delayed_record_failure
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.copy_forward, candidate_id, company_id=3)
        assert recorder_ready.wait(10)
        terminal_time = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE public.ct_extraction_run
                    SET status = :status,
                        stage = :status,
                        failure_class = :failure_class,
                        error_message = :error_message,
                        published_at = CASE WHEN :status = 'SUCCEEDED'
                                            THEN :terminal_time ELSE published_at END,
                        completed_at = :terminal_time,
                        finished_at = :terminal_time,
                        duration_seconds = 1.0
                    WHERE run_id = CAST(:run_id AS UUID)
                    """
                ),
                {
                    "run_id": candidate_id,
                    "status": status,
                    "failure_class": failure_class,
                    "error_message": error_message,
                    "terminal_time": terminal_time,
                },
            )
        release_recorder.set()
        with pytest.raises(RuntimeError, match="original terminal-race failure"):
            future.result(timeout=15)

    with engine.connect() as conn:
        candidate = conn.execute(
            text(
                """
                SELECT status, failure_class, error_message
                FROM public.ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_id},
        ).mappings().one()
    assert dict(candidate) == {
        "status": status,
        "failure_class": failure_class,
        "error_message": error_message,
    }


def test_derived_audit_and_finding_tables_are_not_copied(postgres_engine):
    engine = postgres_engine
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE public.ct_purchase_order_date_enrichment_execution (
                    execution_id UUID PRIMARY KEY,
                    run_id UUID NOT NULL,
                    company_id BIGINT NOT NULL,
                    expected_count BIGINT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE public.ct_purchase_order_date_enrichment (
                    run_id UUID NOT NULL,
                    purchase_order_id BIGINT NOT NULL,
                    company_id BIGINT NOT NULL,
                    source_state TEXT NOT NULL,
                    enrichment_execution_id UUID NOT NULL,
                    PRIMARY KEY (run_id, purchase_order_id)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE public.ct_finding (
                    finding_id TEXT PRIMARY KEY,
                    company_id BIGINT NOT NULL,
                    current_status TEXT NOT NULL
                )
                """
            )
        )
        execution_id = "00000000-0000-4000-8000-000000000301"
        conn.execute(
            text(
                """
                INSERT INTO public.ct_purchase_order_date_enrichment_execution
                    (execution_id, run_id, company_id, expected_count, status)
                VALUES (CAST(:execution AS UUID), CAST(:run_id AS UUID), 3, 1, 'COMPLETED')
                """
            ),
            {"execution": execution_id, "run_id": PHASE7_BASE_RUN_ID},
        )
        conn.execute(
            text(
                """
                INSERT INTO public.ct_purchase_order_date_enrichment
                    (run_id, purchase_order_id, company_id, source_state,
                     enrichment_execution_id)
                VALUES (CAST(:run_id AS UUID), 700001, 3, 'cancel',
                        CAST(:execution AS UUID))
                """
            ),
            {"run_id": PHASE7_BASE_RUN_ID, "execution": execution_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO public.ct_finding (finding_id, company_id, current_status)
                VALUES ('finding-source', 3, 'OPEN')
                """
            )
        )
    try:
        candidate_id = _candidate(engine)
        _copy_service(engine).copy_forward(candidate_id, company_id=3)
        with engine.connect() as conn:
            enrichment_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM public.ct_purchase_order_date_enrichment
                    WHERE run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": candidate_id},
            ).scalar_one()
            finding_count = conn.execute(
                text("SELECT COUNT(*) FROM public.ct_finding")
            ).scalar_one()
            execution_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM public.ct_purchase_order_date_enrichment_execution
                    WHERE run_id = CAST(:run_id AS UUID)
                    """
                ),
                {"run_id": candidate_id},
            ).scalar_one()
        assert enrichment_count == 0
        assert execution_count == 0
        assert finding_count == 1
    finally:
        with engine.begin() as conn:
            for table in (
                "ct_purchase_order_date_enrichment",
                "ct_purchase_order_date_enrichment_execution",
                "ct_finding",
            ):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))


def test_company_scoped_copy_does_not_leak_rows(postgres_engine):
    engine = postgres_engine
    source_four = "00000000-0000-4000-8000-000000000401"
    _base_run(engine, source_four, company_id=4)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_native_record_snapshot (
                    extraction_run_id, model, record_id, document_number, state,
                    company_id, company_name, write_date, payload, extracted_at
                )
                VALUES (CAST(:run_id AS UUID), 'sale.order', 740001,
                        'SO-COMPANY-4', 'sale', 4, 'Company 4', :write_date,
                        CAST(:payload AS JSONB), :extracted_at)
                """
            ),
            {
                "run_id": source_four,
                "write_date": datetime(2026, 1, 1, 9, 55),
                "payload": '{"id": 740001, "name": "SO-COMPANY-4"}',
                "extracted_at": datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
            },
        )
    _publish_pointer(engine, source_four, company_id=4)
    candidate_four = _candidate(engine, company_id=4)
    result = _copy_service(engine).copy_forward(candidate_four, company_id=4)
    assert result["source_run_id"] == source_four
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT company_id, record_id
                FROM public.ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": candidate_four},
        ).all()
    assert rows == [(4, 740001)]


def test_concurrent_same_candidate_attempts_are_serialized(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    started = Event()
    release = Event()

    def wait_after_first_table(table_name, _conn):
        if table_name == SNAPSHOT_TABLE_NAMES[0]:
            started.set()
            assert release.wait(10)

    first_service = _copy_service(engine, copy_hook=wait_after_first_table)
    second_service = _copy_service(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            first_service.copy_forward,
            candidate_id,
            company_id=3,
        )
        assert started.wait(5)
        second_future = pool.submit(
            second_service.copy_forward,
            candidate_id,
            company_id=3,
        )
        time.sleep(0.2)
        assert not second_future.done()
        release.set()
        first = first_future.result(timeout=15)
        second = second_future.result(timeout=15)
    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert _counts(engine, candidate_id) == first["tables"]


def test_distinct_same_company_candidates_share_advisory_lock(postgres_engine):
    engine = postgres_engine
    first_candidate = _candidate(engine)
    second_candidate = _candidate(engine)
    started = Event()
    release = Event()

    def wait_after_first_table(table_name, _conn):
        if table_name == SNAPSHOT_TABLE_NAMES[0]:
            started.set()
            assert release.wait(10)

    first_service = _copy_service(engine, copy_hook=wait_after_first_table)
    second_service = _copy_service(engine)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(
            first_service.copy_forward,
            first_candidate,
            company_id=3,
        )
        assert started.wait(5)
        second_future = pool.submit(
            second_service.copy_forward,
            second_candidate,
            company_id=3,
        )
        time.sleep(0.2)
        assert not second_future.done()
        release.set()
        first = first_future.result(timeout=15)
        second = second_future.result(timeout=15)
    assert first["idempotent"] is False
    assert second["idempotent"] is False
    assert _counts(engine, first_candidate) == first["tables"]
    assert _counts(engine, second_candidate) == second["tables"]


def test_pointer_update_waits_for_copy_forward_transaction(postgres_engine):
    engine = postgres_engine
    candidate_id = _candidate(engine)
    alternate_source = "00000000-0000-4000-8000-000000000501"
    _base_run(engine, alternate_source)

    started = Event()
    release = Event()

    def wait_after_first_table(table_name, _conn):
        if table_name == SNAPSHOT_TABLE_NAMES[0]:
            started.set()
            assert release.wait(10)

    service = _copy_service(engine, copy_hook=wait_after_first_table)

    def repoint():
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE public.ct_published_snapshot
                    SET run_id = CAST(:run_id AS UUID)
                    WHERE company_id = 3
                    """
                ),
                {"run_id": alternate_source},
            )
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        copy_future = pool.submit(service.copy_forward, candidate_id, company_id=3)
        assert started.wait(5)
        repoint_future = pool.submit(repoint)
        time.sleep(0.2)
        assert not repoint_future.done()
        release.set()
        copy_result = copy_future.result(timeout=15)
        assert repoint_future.result(timeout=15) is True
    assert copy_result["source_run_id"] == PHASE7_BASE_RUN_ID
    with engine.connect() as conn:
        pointer = conn.execute(
            text(
                "SELECT run_id::text FROM public.ct_published_snapshot WHERE company_id = 3"
            )
        ).scalar_one()
    assert pointer == alternate_source
