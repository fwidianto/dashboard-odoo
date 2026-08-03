"""Disposable PostgreSQL proof for the Phase 8 refresh contracts.

These tests deliberately use only CT_TEST_POSTGRES_URL.  They refuse a
database that already contains the named public objects and never target the
office-pilot database implicitly.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.clients.postgres_client import PostgresClient
from src.control_tower.relation_extractor import ControlTowerRelationExtractor
from src.control_tower.reconciliation import ReconciliationQueueService
from src.control_tower.reconciliation import normalize_reconciliation_timestamp
from src.control_tower.refresh_state import RefreshRunStateService
from src.control_tower.schema_guard import Phase8SchemaNotReady, ensure_phase8_schema_ready
from src.control_tower.watermarks import ControlTowerWatermarkStore


TEST_DATABASE_ENV = "CT_TEST_POSTGRES_URL"
POSTGRES_URL = os.getenv(TEST_DATABASE_ENV)
ROOT = Path(__file__).parents[1]
PHASE7_BASE_RUN_ID = "00000000-0000-4000-8000-000000000100"
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason=f"Set {TEST_DATABASE_ENV} to an explicit disposable development/test PostgreSQL URL.",
)


def _alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


@contextmanager
def _test_alembic_settings():
    import src.utils.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: SimpleNamespace(
        postgres=SimpleNamespace(connection_url=POSTGRES_URL)
    )
    try:
        yield
    finally:
        settings_module.get_settings = original


def _upgrade(engine) -> None:
    with _test_alembic_settings():
        command.upgrade(_alembic_config(), "002")


def _downgrade(engine) -> None:
    with _test_alembic_settings():
        command.downgrade(_alembic_config(), "001")


def _base_run(engine, run_id: str, company_id: int = 3, status: str = "SUCCEEDED") -> None:
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_extraction_run
                    (run_id, started_at, completed_at, finished_at, published_at,
                     status, company_id)
                VALUES (CAST(:run_id AS UUID), :started_at, :completed_at, :finished_at,
                        :published_at, :status, :company_id)
                """
            ),
            {
                "run_id": run_id,
                "started_at": now - timedelta(minutes=1),
                "completed_at": now,
                "finished_at": now,
                "published_at": now,
                "status": status,
                "company_id": company_id,
            },
        )


def _publish_pointer(engine, run_id: str, company_id: int = 3) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_published_snapshot
                    (company_id, run_id, published_at)
                VALUES (:company_id, CAST(:run_id AS UUID), :published_at)
                ON CONFLICT (company_id) DO UPDATE SET
                    run_id = EXCLUDED.run_id,
                    published_at = EXCLUDED.published_at
                """
            ),
            {"company_id": company_id, "run_id": run_id, "published_at": datetime.now(timezone.utc)},
        )


def _bootstrap_phase7(engine) -> None:
    postgres_client = PostgresClient(connection_url=POSTGRES_URL)
    try:
        ControlTowerRelationExtractor(
            odoo_client=object(),
            postgres_client=postgres_client,
            company_id=3,
        ).ensure_schema()
    finally:
        postgres_client.engine.dispose()

    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_extraction_run
                    (run_id, started_at, completed_at, finished_at, published_at,
                     status, company_id, trigger, requested_by)
                VALUES (CAST(:run_id AS UUID), :started_at, :completed_at, :finished_at,
                        :published_at, 'COMPLETED', 3, 'test-bootstrap', 'phase8-test')
                """
            ),
            {
                "run_id": PHASE7_BASE_RUN_ID,
                "started_at": now - timedelta(minutes=1),
                "completed_at": now,
                "finished_at": now,
                "published_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO public.ct_native_record_snapshot
                    (extraction_run_id, model, record_id, document_number, state,
                     company_id, company_name, write_date, payload, extracted_at)
                VALUES (CAST(:run_id AS UUID), 'sale.order', 700001, 'SO-PHASE8-TEST',
                        'sale', 3, 'PT Nobi Putra Angkasa', :write_date,
                        CAST(:payload AS JSONB), :extracted_at)
                """
            ),
            {
                "run_id": PHASE7_BASE_RUN_ID,
                "write_date": datetime(2026, 1, 1, 9, 55),
                "payload": '{"id": 700001, "name": "SO-PHASE8-TEST"}',
                "extracted_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO public.ct_document_link
                    (extraction_run_id, link_type, parent_model, parent_id,
                     parent_number, child_model, child_id, child_number,
                     source_field, confidence, evidence, extracted_at)
                VALUES (CAST(:run_id AS UUID), 'SO_TO_LINE', 'sale.order', 700001,
                        'SO-PHASE8-TEST', 'sale.order.line', 700002,
                        'SOL-PHASE8-TEST', 'order_id', 'HIGH',
                        CAST(:evidence AS JSONB), :extracted_at)
                """
            ),
            {
                "run_id": PHASE7_BASE_RUN_ID,
                "evidence": '{"source": "phase7-bootstrap"}',
                "extracted_at": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO public.ct_published_snapshot
                    (company_id, run_id, published_at, trigger, requested_by)
                VALUES (3, CAST(:run_id AS UUID), :published_at,
                        'test-bootstrap', 'phase8-test')
                """
            ),
            {"run_id": PHASE7_BASE_RUN_ID, "published_at": now},
        )
        conn.execute(
            text(
                """
                CREATE TABLE public.alembic_version
                    (version_num VARCHAR(32) NOT NULL PRIMARY KEY)
                """
            )
        )
        conn.execute(
            text("INSERT INTO public.alembic_version (version_num) VALUES ('001')")
        )


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
                f"{TEST_DATABASE_ENV} must point to an empty disposable database; "
                f"existing objects found: {sorted(existing)}"
            )
        _bootstrap_phase7(engine)
    except (SQLAlchemyError, OSError) as exc:
        engine.dispose()
        pytest.skip(f"Disposable PostgreSQL unavailable ({type(exc).__name__}).")
    try:
        yield engine
    finally:
        try:
            with engine.begin() as conn:
                for table in (
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
        except SQLAlchemyError:
            pass
        engine.dispose()


def _ready_phase8(engine) -> None:
    _upgrade(engine)


def test_phase7_fixture_has_real_bootstrap_columns_before_revision_002(postgres_engine):
    engine = postgres_engine
    with engine.connect() as conn:
        run_columns = {
            row["column_name"]: row["udt_name"]
            for row in conn.execute(
                text(
                    """
                    SELECT column_name, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'ct_extraction_run'
                      AND column_name = ANY(:names)
                    """
                ),
                {
                    "names": [
                        "run_id", "started_at", "completed_at", "finished_at",
                        "published_at", "status", "company_id", "requested_by",
                    ]
                },
            ).mappings().all()
        }
        snapshot_columns = {
            row["column_name"]: row["udt_name"]
            for row in conn.execute(
                text(
                    """
                    SELECT column_name, udt_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'ct_published_snapshot'
                      AND column_name = ANY(:names)
                    """
                ),
                {"names": ["company_id", "run_id", "published_at", "requested_by"]},
            ).mappings().all()
        }
        revision = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()
        phase8_column = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'ct_extraction_run'
                  AND column_name = 'requested_at'
                """
            )
        ).scalar()
    assert run_columns == {
        "run_id": "uuid",
        "started_at": "timestamptz",
        "completed_at": "timestamptz",
        "finished_at": "timestamptz",
        "published_at": "timestamptz",
        "status": "text",
        "company_id": "int8",
        "requested_by": "text",
    }
    assert snapshot_columns == {
        "company_id": "int8",
        "run_id": "uuid",
        "published_at": "timestamptz",
        "requested_by": "text",
    }
    assert revision == "001"
    assert phase8_column is None


def test_missing_phase7_prerequisite_rolls_back_without_phase8_objects(postgres_engine):
    engine = postgres_engine
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE public.ct_published_snapshot"))
    with pytest.raises(SQLAlchemyError, match="Phase 8 migration"):
        _upgrade(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.ct_control_tower_watermark')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.ct_parent_reconciliation_queue')")).scalar() is None
        assert conn.execute(text("SELECT to_regclass('public.ct_parent_reconciliation_cursor')")).scalar() is None
        assert conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one() == "001"
        assert conn.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'ct_extraction_run'
              AND column_name = 'requested_at'
        """)).scalar() is None


def test_upgrade_metadata_and_reversible_downgrade_preserve_phase7(postgres_engine):
    engine = postgres_engine
    _upgrade(engine)
    with engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    """
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN (
                          'ct_extraction_run', 'ct_published_snapshot',
                          'ct_control_tower_watermark',
                          'ct_parent_reconciliation_queue',
                          'ct_parent_reconciliation_cursor'
                      )
                    """
                )
            ).scalars()
        )
        constraints = set(
            conn.execute(
                text(
                    """
                    SELECT conname FROM pg_constraint
                    WHERE conname IN (
                        'ck_ct_run_failure_class', 'ck_ct_run_retry_not_self',
                        'fk_ct_run_retry_of', 'fk_ct_run_base_snapshot',
                        'fk_ct_watermark_published_run',
                        'fk_ct_reconcile_source_run',
                        'ck_ct_watermark_overlap_nonnegative'
                    )
                    """
                )
            ).scalars()
        )
    assert {
        "ct_extraction_run",
        "ct_published_snapshot",
        "ct_control_tower_watermark",
        "ct_parent_reconciliation_queue",
        "ct_parent_reconciliation_cursor",
    } <= tables
    assert {
        "ck_ct_run_failure_class",
        "ck_ct_run_retry_not_self",
        "fk_ct_run_retry_of",
        "fk_ct_run_base_snapshot",
        "fk_ct_watermark_published_run",
        "fk_ct_reconcile_source_run",
        "ck_ct_watermark_overlap_nonnegative",
    } <= constraints
    _base_run(engine, "00000000-0000-4000-8000-000000000001")
    _publish_pointer(engine, "00000000-0000-4000-8000-000000000001")
    _downgrade(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM public.ct_extraction_run")).scalar() == 2
        assert conn.execute(text("SELECT count(*) FROM public.ct_published_snapshot")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM public.ct_native_record_snapshot")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM public.ct_document_link")).scalar() == 1
        assert conn.execute(text("SELECT run_id::text FROM public.ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)"), {"run_id": PHASE7_BASE_RUN_ID}).scalar_one() == PHASE7_BASE_RUN_ID
        assert conn.execute(text("SELECT run_id::text FROM public.ct_published_snapshot WHERE company_id = 3")).scalar_one() == "00000000-0000-4000-8000-000000000001"
        assert conn.execute(text("SELECT to_regclass('public.ct_control_tower_watermark')")).scalar() is None


def test_runtime_guard_rejects_before_revision_and_accepts_after(postgres_engine):
    engine = postgres_engine
    client = type("Client", (), {"engine": engine})()
    with pytest.raises(Phase8SchemaNotReady, match="revision 002"):
        ensure_phase8_schema_ready(client)
    _ready_phase8(engine)
    ensure_phase8_schema_ready(client)


def test_persisted_state_no_change_metadata_and_snapshot_guard(postgres_engine):
    engine = postgres_engine
    _ready_phase8(engine)
    base_id = "00000000-0000-4000-8000-000000000010"
    _base_run(engine, base_id)
    _publish_pointer(engine, base_id)
    service = RefreshRunStateService(type("Client", (), {"engine": engine})())
    run = service.create_run(company_id=3, selected_domains=["commercial"], now=datetime(2026, 1, 1, 11, tzinfo=timezone.utc))
    for target in ("PREPARING", "DETECTING_CHANGES", "VALIDATING", "PUBLISHING"):
        service.transition(run["run_id"], target, now=datetime(2026, 1, 1, 11, tzinfo=timezone.utc))
    service.finalize_no_change(run["run_id"], now=datetime(2026, 1, 1, 11, 1, tzinfo=timezone.utc))
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT status, completed_at, finished_at, published_at, heartbeat_at,
                       stage_started_at, duration_seconds
                FROM public.ct_extraction_run
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run["run_id"]},
        ).mappings().one()
    assert row["status"] == "SUCCEEDED_NO_CHANGES"
    assert all(row[field] is not None for field in ("completed_at", "finished_at", "published_at", "heartbeat_at", "stage_started_at", "duration_seconds"))
    race_base_id = "00000000-0000-4000-8000-000000000011"
    _base_run(engine, race_base_id)
    _publish_pointer(engine, race_base_id)
    race_run = service.create_run(company_id=3, selected_domains=["commercial"], now=datetime(2026, 1, 1, 11, 3, tzinfo=timezone.utc))
    for target in ("PREPARING", "DETECTING_CHANGES", "VALIDATING", "PUBLISHING"):
        service.transition(race_run["run_id"], target, now=datetime(2026, 1, 1, 11, 3, tzinfo=timezone.utc))
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE public.ct_published_snapshot SET run_id = CAST(:run_id AS UUID) WHERE company_id = 3"),
            {"run_id": base_id},
        )
    with pytest.raises(ValueError, match="trusted snapshot"):
        service.finalize_no_change(race_run["run_id"], now=datetime(2026, 1, 1, 11, 4, tzinfo=timezone.utc))


def test_retry_persistence_source_immutability_and_database_self_reference_guard(postgres_engine):
    engine = postgres_engine
    _ready_phase8(engine)
    base_id = "00000000-0000-4000-8000-000000000020"
    source_id = "00000000-0000-4000-8000-000000000021"
    _base_run(engine, base_id)
    _publish_pointer(engine, base_id)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_extraction_run
                    (run_id, started_at, status, company_id, attempt, selected_domains,
                     retry_of_run_id, base_snapshot_run_id, failure_class)
                VALUES (CAST(:run_id AS UUID), :started_at, 'FAILED_TRANSIENT', 3, 4,
                        '["commercial"]'::jsonb, NULL, CAST(:base AS UUID), 'TRANSIENT')
                """
            ),
            {"run_id": source_id, "base": base_id, "started_at": datetime.now(timezone.utc)},
        )
    service = RefreshRunStateService(type("Client", (), {"engine": engine})())
    retry = service.create_retry(source_id, now=datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
    with engine.connect() as conn:
        source = conn.execute(
            text("SELECT status, attempt, retry_of_run_id FROM public.ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)"),
            {"run_id": source_id},
        ).mappings().one()
        child = conn.execute(
            text("SELECT status, attempt, retry_of_run_id FROM public.ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)"),
            {"run_id": retry["run_id"]},
        ).mappings().one()
    assert source["status"] == "FAILED_TRANSIENT" and source["attempt"] == 4 and source["retry_of_run_id"] is None
    assert child["status"] == "REQUESTED" and child["attempt"] == 5 and str(child["retry_of_run_id"]) == source_id
    cycle_a = "00000000-0000-4000-8000-000000000023"
    cycle_b = "00000000-0000-4000-8000-000000000024"
    with engine.begin() as conn:
        for cycle_id in (cycle_a, cycle_b):
            conn.execute(
                text(
                    """
                    INSERT INTO public.ct_extraction_run
                        (run_id, started_at, status, company_id, attempt,
                         selected_domains, base_snapshot_run_id, failure_class)
                    VALUES (CAST(:run_id AS UUID), :started_at, 'FAILED_TRANSIENT', 3, 1,
                            '["commercial"]'::jsonb, CAST(:base AS UUID), 'TRANSIENT')
                    """
                ),
                {"run_id": cycle_id, "base": base_id, "started_at": datetime.now(timezone.utc)},
            )
        conn.execute(
            text(
                "UPDATE public.ct_extraction_run SET retry_of_run_id = CAST(:parent AS UUID) "
                "WHERE run_id = CAST(:child AS UUID)"
            ),
            {"child": cycle_a, "parent": cycle_b},
        )
        conn.execute(
            text(
                "UPDATE public.ct_extraction_run SET retry_of_run_id = CAST(:parent AS UUID) "
                "WHERE run_id = CAST(:child AS UUID)"
            ),
            {"child": cycle_b, "parent": cycle_a},
        )
    with pytest.raises(ValueError, match="cycle"):
        service.create_retry(cycle_a, now=datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc))
    with pytest.raises(SQLAlchemyError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO public.ct_extraction_run
                        (run_id, started_at, status, company_id, retry_of_run_id)
                    VALUES (CAST(:run_id AS UUID), :started_at, 'REQUESTED', 3,
                            CAST(:run_id AS UUID))
                    """
                ),
                {"run_id": "00000000-0000-4000-8000-000000000022", "started_at": datetime.now(timezone.utc)},
            )


def test_watermark_monotonic_concurrent_and_no_change_checked_at_only(postgres_engine):
    engine = postgres_engine
    _ready_phase8(engine)
    run_id = "00000000-0000-4000-8000-000000000030"
    no_change_id = "00000000-0000-4000-8000-000000000031"
    _base_run(engine, run_id)
    _publish_pointer(engine, run_id)
    client = type("Client", (), {"engine": engine})()

    def advance(write_date, record_id):
        return ControlTowerWatermarkStore(client).advance_after_publication(
            company_id=3,
            model="stock.move",
            run_id=run_id,
            write_date=write_date,
            record_id=record_id,
            now=datetime(2026, 1, 1, 13, tzinfo=timezone.utc),
        )

    def concurrent_advance(write_date, record_id):
        try:
            advance(write_date, record_id)
        except ValueError as exc:
            return str(exc)
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda pair: concurrent_advance(*pair),
                (
                    (datetime(2026, 1, 1, 10, tzinfo=timezone.utc), 10),
                    (datetime(2026, 1, 1, 9, tzinfo=timezone.utc), 9),
                ),
            )
        )
    assert any(result is None for result in results)
    store = ControlTowerWatermarkStore(client)
    current = store.get(3, "stock.move")
    assert current["last_successful_id"] == 10
    equal_before = dict(current)
    advance(datetime(2026, 1, 1, 10, tzinfo=timezone.utc), 10)
    equal_after = store.get(3, "stock.move")
    assert equal_after["last_successful_write_date"] == equal_before["last_successful_write_date"]
    assert equal_after["last_successful_id"] == equal_before["last_successful_id"]
    with pytest.raises(ValueError, match="backward"):
        advance(datetime(2025, 12, 31, 23, tzinfo=timezone.utc), 1)
    older_after = store.get(3, "stock.move")
    assert older_after["last_successful_write_date"] == equal_after["last_successful_write_date"]
    assert older_after["last_successful_id"] == equal_after["last_successful_id"]
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_extraction_run
                    (run_id, started_at, status, company_id, published_at,
                     base_snapshot_run_id)
                VALUES (CAST(:run_id AS UUID), :started_at, 'SUCCEEDED_NO_CHANGES', 3,
                        :published_at, CAST(:base AS UUID))
                """
            ),
            {
                "run_id": no_change_id,
                "base": run_id,
                "started_at": datetime.now(timezone.utc),
                "published_at": datetime.now(timezone.utc),
            },
        )
    before = dict(current)
    store.record_no_change_checked_at(
        company_id=3,
        model="stock.move",
        run_id=no_change_id,
        now=datetime(2026, 1, 1, 14, tzinfo=timezone.utc),
    )
    after = store.get(3, "stock.move")
    assert after["last_successful_write_date"] == before["last_successful_write_date"]
    assert after["last_successful_id"] == before["last_successful_id"]
    assert after["published_run_id"] == before["published_run_id"]
    assert after["checked_at"] > before["checked_at"]
    with pytest.raises(ValueError):
        store.advance_after_publication(
            company_id=3,
            model="stock.move",
            run_id=no_change_id,
            write_date=datetime(2026, 1, 2, tzinfo=timezone.utc),
            record_id=20,
        )


def test_reconciliation_touch_claim_completion_and_cursor_cas(postgres_engine):
    engine = postgres_engine
    _ready_phase8(engine)
    run_id = "00000000-0000-4000-8000-000000000040"
    _base_run(engine, run_id)
    service = ReconciliationQueueService(type("Client", (), {"engine": engine})())
    first_time = datetime(2026, 1, 1, 15, tzinfo=timezone.utc)
    service.enqueue(
        company_id=3,
        parent_model="mrp.production",
        parent_id=100,
        child_model="stock.move",
        reason="initial",
        source_run_id=run_id,
        now=first_time,
    )
    claimed = service.claim(company_id=3, worker_id="worker-1", now=first_time + timedelta(minutes=1))
    assert len(claimed) == 1
    assert claimed[0]["last_touched_at"] == first_time
    assert claimed[0]["updated_at"] == first_time + timedelta(minutes=1)
    key = {name: claimed[0][name] for name in ("company_id", "parent_model", "parent_id", "child_model")}
    local_touch = datetime(2026, 1, 1, 22, 2, tzinfo=timezone(timedelta(hours=7)))
    service.enqueue(
        **key,
        reason="touched-while-running",
        source_run_id=run_id,
        now=local_touch,
    )
    with engine.connect() as conn:
        touched = conn.execute(
            text(
                """
                SELECT generation, status, last_touched_at,
                       last_touched_at AT TIME ZONE 'UTC' AS last_touched_utc
                FROM public.ct_parent_reconciliation_queue
                WHERE company_id = 3 AND parent_model = 'mrp.production'
                  AND parent_id = 100 AND child_model = 'stock.move'
                """
            )
        ).mappings().one()
    assert touched["generation"] == 2 and touched["status"] == "RUNNING"
    assert touched["last_touched_utc"] == datetime(2026, 1, 1, 15, 2)
    assert service.complete(key, claimed_generation=claimed[0]["claimed_generation"], now=first_time + timedelta(minutes=3)) == "PENDING"
    reclaimed = service.claim(company_id=3, worker_id="worker-2", now=first_time + timedelta(minutes=4))
    assert reclaimed[0]["last_touched_at"] == normalize_reconciliation_timestamp(local_touch)
    assert service.complete(key, claimed_generation=reclaimed[0]["claimed_generation"], now=first_time + timedelta(minutes=5)) == "COMPLETED"
    failure_touch = datetime(2026, 1, 1, 22, 5, 1, tzinfo=timezone(timedelta(hours=7)))
    service.enqueue(
        company_id=3,
        parent_model="mrp.production",
        parent_id=101,
        child_model="stock.move",
        reason="retryable",
        source_run_id=run_id,
        now=failure_touch,
    )
    failed_claim = service.claim(
        company_id=3,
        worker_id="worker-3",
        now=datetime(2026, 1, 1, 22, 5, 2, tzinfo=timezone(timedelta(hours=7))),
    )
    assert failed_claim[0]["last_touched_at"] == normalize_reconciliation_timestamp(failure_touch)
    failed_key = {name: failed_claim[0][name] for name in ("company_id", "parent_model", "parent_id", "child_model")}
    assert service.fail(failed_key, claimed_generation=failed_claim[0]["claimed_generation"], now=first_time + timedelta(minutes=5, seconds=3)) == "PENDING"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.ct_parent_reconciliation_cursor
                    (company_id, parent_model, child_model)
                VALUES (3, 'mrp.production', 'stock.move')
                """
            )
        )
    cursor_return = service.advance_cursor(
        company_id=3,
        parent_model="mrp.production",
        child_model="stock.move",
        expected_version=0,
        last_parent_id=100,
        now=first_time + timedelta(minutes=6),
    )
    assert cursor_return["last_sweep_completed_at"] == first_time + timedelta(minutes=6)
    with engine.connect() as conn:
        cursor = conn.execute(
            text(
                """
                SELECT version, last_parent_id, last_sweep_completed_at,
                       last_sweep_completed_at AT TIME ZONE 'UTC' AS completed_utc
                FROM public.ct_parent_reconciliation_cursor
                WHERE company_id = 3
                  AND parent_model = 'mrp.production'
                  AND child_model = 'stock.move'
                """
            )
        ).mappings().one()
    assert cursor["version"] == 1 and cursor["last_parent_id"] == 100
    assert cursor["completed_utc"] == datetime(2026, 1, 1, 15, 6)
    with pytest.raises(ValueError, match="timezone-aware"):
        service.enqueue(
            company_id=3,
            parent_model="mrp.production",
            parent_id=102,
            child_model="stock.move",
            reason="naive-rejected",
            source_run_id=run_id,
            now=datetime(2026, 1, 1, 15),
        )
    with pytest.raises(ValueError, match="Stale"):
        service.advance_cursor(
            company_id=3,
            parent_model="mrp.production",
            child_model="stock.move",
            expected_version=0,
            last_parent_id=101,
            now=first_time + timedelta(minutes=7),
        )
