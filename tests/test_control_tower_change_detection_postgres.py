"""Disposable PostgreSQL proof for Phase 8B-2B2R precision-safe detection."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from src.control_tower.change_detection import (
    BootstrapRequired,
    ChangeDetectionError,
    DETECTION_BUCKET_PAGE_SIZE,
    DETECTION_CURSOR_ALGORITHM_VERSION,
    IncrementalChangeDetectionService,
)
from src.control_tower.progress import parse_progress_json
from tests.control_tower_odoo_fake import FakeOdoo, UnfilteredOdoo
from tests.test_control_tower_copy_forward_postgres import _candidate, _copy_service
from tests.test_control_tower_refresh_contracts_postgres import (
    PHASE7_BASE_RUN_ID,
    _base_run,
    _bootstrap_phase7,
    _publish_pointer,
    _upgrade,
)

POSTGRES_URL = os.getenv("CT_TEST_POSTGRES_URL")
ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="Set CT_TEST_POSTGRES_URL to a disposable PostgreSQL URL.")


def _config():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


@contextmanager
def _settings():
    import src.utils.settings as settings_module
    original = settings_module.get_settings
    settings_module.get_settings = lambda: SimpleNamespace(postgres=SimpleNamespace(connection_url=POSTGRES_URL))
    try:
        yield
    finally:
        settings_module.get_settings = original


def _upgrade_003():
    with _settings():
        command.upgrade(_config(), "003")


def _downgrade_002():
    with _settings():
        command.downgrade(_config(), "002")


@pytest.fixture
def engine():
    db = create_engine(POSTGRES_URL, pool_pre_ping=True)
    _bootstrap_phase7(db)
    _upgrade(db)
    _upgrade_003()
    try:
        yield db
    finally:
        with db.begin() as conn:
            for table in (
                "ct_change_manifest", "ct_change_detection_run",
                "ct_control_tower_watermark", "ct_parent_reconciliation_queue",
                "ct_parent_reconciliation_cursor", "ct_published_snapshot",
                "ct_native_record_snapshot", "ct_document_link",
                "ct_extraction_run", "alembic_version",
            ):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
        db.dispose()


def _client(engine):
    return SimpleNamespace(engine=engine)


def _watermark(engine, model, *, company_id=3, stamp=datetime(2026, 1, 1, 10, tzinfo=timezone.utc), record_id=1, overlap=0):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO ct_control_tower_watermark
                (company_id, model, last_successful_write_date, last_successful_id,
                 overlap_seconds, published_run_id, status)
            VALUES (:company_id, :model, :stamp, :record_id, :overlap,
                    CAST(:run_id AS UUID), 'READY')
        """), {"company_id": company_id, "model": model, "stamp": stamp, "record_id": record_id,
               "overlap": overlap, "run_id": PHASE7_BASE_RUN_ID})


def _ready_candidate(engine):
    candidate = _candidate(engine)
    _copy_service(engine).copy_forward(candidate, company_id=3)
    return candidate


def _seed_watermarks(engine):
    _watermark(engine, "sale.order")
    _watermark(engine, "sale.order.line")


def _rows():
    return {
        "sale.order": [
            {"id": 2, "write_date": "2026-01-01 10:00:01", "company_id": [3, "Nobi"]},
        ],
        "sale.order.line": [
            {"id": 4, "write_date": "2026-01-01 10:00:02", "company_id": [3, "Nobi"], "order_id": [2, "SO"]},
        ],
    }


def _progress(engine, run_id):
    with engine.connect() as conn:
        return parse_progress_json(conn.execute(text("""
            SELECT progress FROM ct_extraction_run WHERE run_id=CAST(:run_id AS UUID)
        """), {"run_id": run_id}).scalar())


def _header_fingerprint(engine, run_id):
    with engine.connect() as conn:
        return conn.execute(text("""
            SELECT contract_fingerprint FROM ct_change_detection_run WHERE run_id=CAST(:run_id AS UUID)
        """), {"run_id": run_id}).scalar()


def test_upgrade_and_reversible_downgrade(engine):
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.ct_change_manifest')")).scalar()
    _downgrade_002()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.ct_change_manifest')")).scalar() is None


def test_detection_persists_ordered_manifest_and_preserves_immutability(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    before = {}
    with engine.connect() as conn:
        before["pointer"] = conn.execute(text("SELECT run_id::text FROM ct_published_snapshot WHERE company_id=3")).scalar()
        before["watermarks"] = conn.execute(text("SELECT model, last_successful_write_date, last_successful_id FROM ct_control_tower_watermark ORDER BY model")).all()
        before["snapshot"] = conn.execute(text("SELECT COUNT(*) FROM ct_native_record_snapshot WHERE extraction_run_id=CAST(:run_id AS UUID)"), {"run_id": candidate}).scalar()

    result = IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=candidate, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
    )
    assert result["status"] == "COMPLETE"
    assert result["manifest_rows"] == 2
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT model, record_id, parent_model, parent_record_id,
                   from_overlap, detection_sequence
            FROM ct_change_manifest WHERE run_id=CAST(:run_id AS UUID)
            ORDER BY model, detection_sequence
        """), {"run_id": candidate}).all()
        assert [(r[0], r[1], r[2], r[3], r[4]) for r in rows] == [
            ("sale.order", 2, None, None, False),
            ("sale.order.line", 4, "sale.order", 2, False),
        ]
        assert [r[5] for r in rows] == [1, 1]
        progress = parse_progress_json(conn.execute(text("SELECT progress FROM ct_extraction_run WHERE run_id=CAST(:run_id AS UUID)"), {"run_id": candidate}).scalar())
        assert progress["change_detection_complete"] is True
        assert progress["detection_manifest_rows_persisted"] == 2
        assert conn.execute(text("SELECT run_id::text FROM ct_published_snapshot WHERE company_id=3")).scalar() == before["pointer"]
        assert conn.execute(text("SELECT COUNT(*) FROM ct_native_record_snapshot WHERE extraction_run_id=CAST(:run_id AS UUID)"), {"run_id": candidate}).scalar() == before["snapshot"]
        assert conn.execute(text("SELECT model, last_successful_write_date, last_successful_id FROM ct_control_tower_watermark ORDER BY model")).all() == before["watermarks"]


def test_repeated_complete_detection_is_idempotent_without_odoo_call(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()), now=datetime(2026, 1, 1, 10, tzinfo=timezone.utc))
    class NoCall:
        def search_read(self, *args, **kwargs):
            raise AssertionError("idempotent detection must not call Odoo")
    result = service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=NoCall(), now=datetime(2026, 1, 1, 10, tzinfo=timezone.utc))
    assert result["idempotent"] is True


def test_missing_watermark_fails_closed_without_manifest(engine):
    candidate = _ready_candidate(engine)
    with pytest.raises(BootstrapRequired, match="BOOTSTRAP_REQUIRED"):
        IncrementalChangeDetectionService(_client(engine)).detect(
            run_id=candidate, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows()),
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ct_change_detection_run")).scalar() == 0


def test_injected_failure_rolls_back_model_manifest_and_leaves_watermarks_unchanged(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    fake = FakeOdoo(_rows(), fail_model="sale.order.line")
    with pytest.raises(RuntimeError, match="injected"):
        IncrementalChangeDetectionService(_client(engine)).detect(
            run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=fake,
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ct_change_manifest")).scalar() == 1
        assert conn.execute(text("SELECT status FROM ct_change_detection_run WHERE run_id=CAST(:run_id AS UUID)"), {"run_id": candidate}).scalar() == "RUNNING"
        assert conn.execute(text("SELECT status FROM ct_extraction_run WHERE run_id=CAST(:run_id AS UUID)"), {"run_id": candidate}).scalar() == "DETECTING_CHANGES"
        assert conn.execute(text("SELECT COUNT(*) FROM ct_native_record_snapshot WHERE extraction_run_id=CAST(:run_id AS UUID)"), {"run_id": candidate}).scalar() == 1


def test_same_run_concurrency_cannot_write_conflicting_manifests(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    entered = Event()
    release = Event()

    class BlockingOdoo(FakeOdoo):
        def search_read(self, model, domain, *, fields=None, order=None, limit=None):
            entered.set()
            if not release.wait(timeout=10):
                raise AssertionError("first detector did not release")
            return super().search_read(model, domain, fields=fields, order=order, limit=limit)

    first_service = IncrementalChangeDetectionService(_client(engine))
    second_service = IncrementalChangeDetectionService(_client(engine))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(
            first_service.detect, run_id=candidate, company_id=3,
            selected_domains=["commercial"], odoo_client=BlockingOdoo(_rows()),
        )
        assert entered.wait(timeout=10)
        second = pool.submit(
            second_service.detect, run_id=candidate, company_id=3,
            selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()),
        )
        with pytest.raises(ChangeDetectionError, match="already running"):
            second.result(timeout=10)
        release.set()
        assert first.result(timeout=20)["status"] == "COMPLETE"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ct_change_manifest WHERE run_id=CAST(:run_id AS UUID)"), {"run_id": candidate}).scalar() == 2


def test_wrong_company_response_is_rejected_without_manifest_rows(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    wrong = {
        "sale.order": [{"id": 2, "write_date": "2026-01-01 10:00:01", "company_id": [4, "Other"]}],
        "sale.order.line": [],
    }
    with pytest.raises(ChangeDetectionError, match="company scope"):
        IncrementalChangeDetectionService(_client(engine)).detect(
            run_id=candidate, company_id=3, selected_domains=["commercial"],
            odoo_client=UnfilteredOdoo(wrong),
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ct_change_manifest")).scalar() == 0


def test_stale_watermark_input_rejects_completed_manifest(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()), now=datetime(2026, 1, 1, 10, tzinfo=timezone.utc))
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_control_tower_watermark
            SET last_successful_id = last_successful_id + 1
            WHERE company_id=3 AND model='sale.order'
        """))
    with pytest.raises(ChangeDetectionError, match="watermark inputs changed"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_manifest_company_fk_and_audit_delete_restriction(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()),
    )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO ct_change_manifest
                    (run_id, company_id, business_domains, model, record_id, source_write_date,
                     parent_hints, from_overlap, detection_sequence, detected_at, status)
                VALUES (CAST(:run_id AS UUID), 4, '[]'::jsonb, 'sale.order', 99, :stamp,
                        '[]'::jsonb, FALSE, 99, :stamp, 'DETECTED')
            """), {"run_id": candidate, "stamp": datetime(2026, 1, 1, 10, tzinfo=timezone.utc)})
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM ct_change_detection_run WHERE run_id=CAST(:run_id AS UUID)"), {"run_id": candidate})


def test_completed_manifest_rejects_equal_count_identity_change(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_change_manifest SET record_id = 99
            WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order'
        """), {"run_id": candidate})
    with pytest.raises(ChangeDetectionError, match="fingerprint"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_completed_manifest_rejects_changed_parent_hints_and_sequence(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_change_manifest
            SET parent_hints=CAST(:hints AS JSONB),
                parent_model='sale.order', parent_record_id=999, detection_sequence=9
            WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order.line'
        """), {"run_id": candidate, "hints": json.dumps([{
            "field": "order_id", "parent_model": "sale.order", "parent_record_id": 999,
        }])})
    with pytest.raises(ChangeDetectionError, match="sequence|fingerprint"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_completed_manifest_rejects_missing_or_extra_rows(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    with engine.begin() as conn:
        conn.execute(text("""
            DELETE FROM ct_change_manifest
            WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order'
        """), {"run_id": candidate})
    with pytest.raises(ChangeDetectionError, match="row count|fingerprint"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_forged_completion_progress_on_partial_run_remains_unreusable(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    with pytest.raises(RuntimeError, match="injected"):
        service.detect(
            run_id=candidate, company_id=3, selected_domains=["commercial"],
            odoo_client=FakeOdoo(_rows(), fail_model="sale.order.line"),
        )
    forged_progress = _progress(engine, candidate)
    forged_progress.update({
        "change_detection_complete": True,
        "detection_selected_domains": ["commercial"],
        "detection_models_planned": ["sale.order", "sale.order.line"],
        "detection_models_completed": ["sale.order", "sale.order.line"],
        "detection_started_at": "2026-01-01T10:00:00+00:00",
        "detection_finished_at": "2026-01-01T10:00:00+00:00",
        "detection_elapsed_seconds": 0,
        "detection_contract_fingerprint": "a" * 64,
        "detection_cursor_algorithm_version": DETECTION_CURSOR_ALGORITHM_VERSION,
        "detection_bucket_page_size": DETECTION_BUCKET_PAGE_SIZE,
        "detection_replay_start_seconds": {
            "sale.order": "2026-01-01T10:00:00+00:00",
            "sale.order.line": "2026-01-01T10:00:00+00:00",
        },
        "detection_scan_upper_exclusives": {
            "sale.order": "2026-01-01T10:00:02+00:00",
            "sale.order.line": "2026-01-01T10:00:03+00:00",
        },
        "detection_completion_fingerprint": "b" * 64,
        "detection_completion_contract_version": "ct-change-manifest-v1",
        "detection_manifest_row_count": 1,
        "detection_manifest_rows_persisted": 1,
        "detection_model_row_counts": {"sale.order": 1, "sale.order.line": 0},
    })
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_extraction_run SET progress = CAST(:progress AS JSONB)
            WHERE run_id=CAST(:run_id AS UUID)
        """), {"run_id": candidate, "progress": json.dumps(forged_progress)})
    with pytest.raises(ChangeDetectionError, match="partial|copy-forward"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_completed_progress_cannot_be_overwritten_by_stale_writer(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    before = _progress(engine, candidate)
    stale = dict(before, change_detection_complete=False, detection_current_model="sale.order")
    with pytest.raises(ChangeDetectionError, match="no longer writable"):
        with engine.begin() as conn:
            service._update_run_progress(conn, candidate, stale)
    assert _progress(engine, candidate) == before


# --- Phase 8B-2B2R new contract coverage -------------------------------------

def test_real_format_timestamps_persist_as_aware_utc_timestamptz(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()),
    )
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT model, record_id, source_write_date
            FROM ct_change_manifest WHERE run_id=CAST(:run_id AS UUID)
            ORDER BY model, record_id
        """), {"run_id": candidate}).all()
    assert rows[0][0:2] == ("sale.order", 2)
    assert rows[1][0:2] == ("sale.order.line", 4)
    for row in rows:
        assert row[2].tzinfo is not None
        assert row[2].microsecond == 0
    assert rows[0][2].astimezone(timezone.utc) == datetime(2026, 1, 1, 10, 0, 1, tzinfo=timezone.utc)
    assert rows[1][2].astimezone(timezone.utc) == datetime(2026, 1, 1, 10, 0, 2, tzinfo=timezone.utc)


def test_completed_evidence_includes_cursor_contract_version_and_final_fingerprint(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    progress = _progress(engine, candidate)
    header_fingerprint = _header_fingerprint(engine, candidate)
    assert progress["detection_cursor_algorithm_version"] == DETECTION_CURSOR_ALGORITHM_VERSION
    assert progress["detection_bucket_page_size"] == DETECTION_BUCKET_PAGE_SIZE
    assert progress["detection_contract_fingerprint"] == header_fingerprint
    assert len(header_fingerprint) == 64


def test_replay_start_and_scan_upper_persist_deterministically(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()),
    )
    progress = _progress(engine, candidate)
    assert progress["detection_replay_start_seconds"] == {
        "sale.order": "2026-01-01T10:00:00+00:00",
        "sale.order.line": "2026-01-01T10:00:00+00:00",
    }
    assert progress["detection_scan_upper_exclusives"] == {
        "sale.order": "2026-01-01T10:00:02+00:00",
        "sale.order.line": "2026-01-01T10:00:03+00:00",
    }


def test_completed_manifest_reuse_succeeds_with_identical_bucket_inputs(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    first = service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    class NoCall:
        def search_read(self, *args, **kwargs):
            raise AssertionError("idempotent detection must not call Odoo")
    second = service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=NoCall())
    assert first["manifest_rows"] == second["manifest_rows"] == 2
    assert second["idempotent"] is True


def test_changed_cursor_version_rejects_reuse(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    with engine.begin() as conn:
        progress = parse_progress_json(conn.execute(text("""
            SELECT progress FROM ct_extraction_run WHERE run_id=CAST(:run_id AS UUID)
        """), {"run_id": candidate}).scalar())
        progress["detection_cursor_algorithm_version"] = "ct-second-bucket-stale"
        conn.execute(text("""
            UPDATE ct_extraction_run SET progress = CAST(:progress AS JSONB)
            WHERE run_id=CAST(:run_id AS UUID)
        """), {"run_id": candidate, "progress": json.dumps(progress)})
    with pytest.raises(ChangeDetectionError, match="cursor algorithm"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_changed_replay_start_rejects_reuse(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE ct_control_tower_watermark
            SET last_successful_write_date = last_successful_write_date + interval '1 second'
            WHERE company_id=3 AND model='sale.order'
        """))
    with pytest.raises(ChangeDetectionError, match="watermark inputs changed"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_changed_scan_upper_boundary_rejects_reuse(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))
    with engine.begin() as conn:
        progress = parse_progress_json(conn.execute(text("""
            SELECT progress FROM ct_extraction_run WHERE run_id=CAST(:run_id AS UUID)
        """), {"run_id": candidate}).scalar())
        progress["detection_scan_upper_exclusives"]["sale.order"] = "2026-01-01T10:00:03+00:00"
        conn.execute(text("""
            UPDATE ct_extraction_run SET progress = CAST(:progress AS JSONB)
            WHERE run_id=CAST(:run_id AS UUID)
        """), {"run_id": candidate, "progress": json.dumps(progress)})
    with pytest.raises(ChangeDetectionError, match="contract inputs changed"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_changed_page_size_rejects_reuse(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()), bucket_page_size=50)
    with pytest.raises(ChangeDetectionError, match="contract inputs changed"):
        service.detect(run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(_rows()))


def test_hidden_precision_rows_produce_deterministic_manifest_evidence(engine):
    rows = {
        "sale.order": [],
        "sale.order.line": [
            {"id": 101, "write_date": "2026-01-01 10:00:00", "company_id": [3, "Nobi"], "order_id": [2, "SO"],
             "_true_write_date": datetime(2026, 1, 1, 10, 0, 0, 500000, tzinfo=timezone.utc)},
            {"id": 102, "write_date": "2026-01-01 10:00:00", "company_id": [3, "Nobi"], "order_id": [2, "SO"],
             "_true_write_date": datetime(2026, 1, 1, 10, 0, 0, 750000, tzinfo=timezone.utc)},
            {"id": 103, "write_date": "2026-01-01 10:00:00", "company_id": [3, "Nobi"], "order_id": [2, "SO"],
             "_true_write_date": datetime(2026, 1, 1, 10, 0, 0, 999000, tzinfo=timezone.utc)},
        ],
    }
    first_candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    service = IncrementalChangeDetectionService(_client(engine))
    fixed_now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    first = service.detect(run_id=first_candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(rows), now=fixed_now)
    second_candidate = _ready_candidate(engine)
    second = service.detect(run_id=second_candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(rows), now=fixed_now)
    assert first["manifest_rows"] == second["manifest_rows"] == 3
    first_progress = _progress(engine, first_candidate)
    second_progress = _progress(engine, second_candidate)
    assert first_progress["detection_completion_fingerprint"] == second_progress["detection_completion_fingerprint"]
    with engine.connect() as conn:
        manifest = conn.execute(text("""
            SELECT record_id, source_write_date, detection_sequence
            FROM ct_change_manifest WHERE run_id=CAST(:run_id AS UUID)
            ORDER BY record_id
        """), {"run_id": first_candidate}).all()
    assert [row[0] for row in manifest] == [101, 102, 103]
    assert [row[2] for row in manifest] == [1, 2, 3]
    assert all(row[1] == datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc) for row in manifest)


def test_mandatory_watermark_second_replay_with_zero_overlap(engine):
    candidate = _ready_candidate(engine)
    _seed_watermarks(engine)
    rows = {
        "sale.order": [],
        "sale.order.line": [
            {"id": 9, "write_date": "2026-01-01 10:00:00", "company_id": [3, "Nobi"], "order_id": [2, "SO"]},
            {"id": 11, "write_date": "2026-01-01 10:00:00", "company_id": [3, "Nobi"], "order_id": [2, "SO"]},
            {"id": 12, "write_date": "2026-01-01 10:00:01", "company_id": [3, "Nobi"], "order_id": [2, "SO"]},
        ],
    }
    result = IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=candidate, company_id=3, selected_domains=["commercial"], odoo_client=FakeOdoo(rows),
    )
    assert result["manifest_rows"] == 3
    with engine.connect() as conn:
        manifest = conn.execute(text("""
            SELECT record_id, from_overlap, detection_sequence
            FROM ct_change_manifest WHERE run_id=CAST(:run_id AS UUID)
            ORDER BY detection_sequence
        """), {"run_id": candidate}).all()
        assert [(row[0], row[1]) for row in manifest] == [(9, True), (11, True), (12, False)]
        assert [row[2] for row in manifest] == [1, 2, 3]
    progress = _progress(engine, candidate)
    assert progress["detection_configured_overlap_rows"] == 0
    assert progress["detection_watermark_second_replay_rows"] == 2
    assert progress["detection_genuinely_newer_rows"] == 1
    assert progress["detection_overlap_rows_rechecked"] == 2