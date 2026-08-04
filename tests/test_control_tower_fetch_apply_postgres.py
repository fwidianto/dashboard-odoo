"""Phase 8C-2 fetch/apply PostgreSQL tests: mocked Odoo + disposable PostgreSQL."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from src.control_tower.change_detection import IncrementalChangeDetectionService
from src.control_tower.copy_forward import CandidateSnapshotCopyForwardService
from src.control_tower.orchestration import OrchestrationError
from src.control_tower.fetch_apply import (
    FETCH_APPLY_CONTRACT_VERSION,
    FetchApplyError,
    FetchApplyService,
    _normalize_record,
)
from src.control_tower.progress import ProgressContractError, parse_progress_json
from src.control_tower.refresh_state import RefreshRunStateService
from src.control_tower.schema_guard import Phase8SchemaNotReady, ensure_phase8_fetch_schema_ready
from tests.control_tower_odoo_fake import (
    _DEFAULT_FIELD_TYPES,
    _RELATION_TARGETS,
    FakeOdoo,
    UnfilteredOdoo,
)
from tests.test_control_tower_change_detection_postgres import _upgrade_003
from tests.test_control_tower_refresh_contracts_postgres import (
    PHASE7_BASE_RUN_ID,
    _bootstrap_phase7,
    _upgrade,
)

POSTGRES_URL = os.getenv("CT_TEST_POSTGRES_URL")
ROOT = Path(__file__).parents[1]
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="Set CT_TEST_POSTGRES_URL to a disposable PostgreSQL URL.",
)

STAMP = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
WIRE = "2026-01-01 10:00:00"
COMMERCIAL_MODELS = ["sale.order", "sale.order.line"]


def _config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


@contextmanager
def _settings():
    import src.utils.settings as settings_module

    original = settings_module.get_settings
    settings_module.get_settings = lambda: SimpleNamespace(
        postgres=SimpleNamespace(connection_url=POSTGRES_URL)
    )
    try:
        yield
    finally:
        settings_module.get_settings = original


def _upgrade_004():
    with _settings():
        command.upgrade(_config(), "004")


def _upgrade_005():
    with _settings():
        command.upgrade(_config(), "005")


def _downgrade_004():
    with _settings():
        command.downgrade(_config(), "004")


def _downgrade_003():
    with _settings():
        command.downgrade(_config(), "003")


@pytest.fixture
def engine():
    db = create_engine(POSTGRES_URL, pool_pre_ping=True)
    _bootstrap_phase7(db)
    _upgrade(db)
    _upgrade_003()
    _upgrade_004()
    _upgrade_005()
    try:
        yield db
    finally:
        with db.begin() as conn:
            for table in (
                "ct_fetch_apply_batch", "ct_fetch_apply_evidence",
                "ct_fetch_apply_run", "ct_change_manifest", "ct_change_detection_run",
                "ct_control_tower_watermark", "ct_parent_reconciliation_queue",
                "ct_parent_reconciliation_cursor", "ct_published_snapshot",
                "ct_native_record_snapshot", "ct_document_link",
                "ct_extraction_run", "alembic_version",
            ):
                conn.execute(text(f"DROP TABLE IF EXISTS public.{table} CASCADE"))
        db.dispose()


def _client(engine):
    return SimpleNamespace(engine=engine)


def _service(engine, *, hooks=None, batch_size=500):
    return FetchApplyService(_client(engine), hooks=hooks, batch_size=batch_size)


def _create_run(engine, domains, *, company_id=3):
    svc = RefreshRunStateService(_client(engine))
    run = svc.create_run(company_id=company_id, selected_domains=domains, now=STAMP)
    svc.transition(run["run_id"], "PREPARING", now=STAMP)
    return run["run_id"]


def _seed_watermarks(engine, models):
    with engine.begin() as conn:
        for model in models:
            conn.execute(
                text(
                    """
                    INSERT INTO ct_control_tower_watermark
                        (company_id, model, last_successful_write_date, last_successful_id,
                         overlap_seconds, published_run_id, status)
                    VALUES (3, :model, :stamp, 1, 0, CAST(:run AS UUID), 'READY')
                    ON CONFLICT (company_id, model) DO NOTHING
                    """
                ),
                {"model": model, "stamp": STAMP, "run": PHASE7_BASE_RUN_ID},
            )


def _rows():
    return {
        "sale.order": [
            {"id": 1, "name": "SO001", "state": "sale", "company_id": [3, "Nobi"],
             "partner_id": [101, "Partner A"], "client_order_ref": "REF-1",
             "x_studio_tanggal_po_cust": False, "x_studio_io_1": [201],
             "date_order": "2026-01-01 09:00:00", "commitment_date": False,
             "write_date": WIRE},
        ],
        "sale.order.line": [
            {"id": 11, "order_id": [1, "SO001"], "product_id": [501, "Product A"],
             "product_uom": [601, "Unit"], "product_uom_qty": 2.0, "qty_delivered": 0.0,
             "qty_invoiced": 0.0, "price_unit": 100.0, "write_date": WIRE,
             "company_id": [3, "Nobi"]},
            {"id": 12, "order_id": [1, "SO001"], "product_id": [502, "Product B"],
             "product_uom": [601, "Unit"], "product_uom_qty": 1.0, "qty_delivered": 1.0,
             "qty_invoiced": 1.0, "price_unit": 50.0, "write_date": WIRE,
             "company_id": [3, "Nobi"]},
        ],
    }


def _run_row(engine, run_id):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT run_id::text, company_id, status, stage,
                       base_snapshot_run_id::text, progress
                FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).mappings().first()
    return dict(row)


def _progress(engine, run_id):
    return parse_progress_json(_run_row(engine, run_id)["progress"])


def _manifest_rows(engine, run_id):
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT model, record_id, source_write_date, detection_sequence, status
                    FROM ct_change_manifest
                    WHERE run_id = CAST(:run_id AS UUID)
                    ORDER BY model, detection_sequence
                    """
                ),
                {"run_id": run_id},
            ).mappings().all()
        ]


def _evidence_rows(engine, run_id):
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT run_id::text, company_id, model, record_id, detection_sequence,
                           batch_number, detection_source_write_date, fetched_write_date,
                           fetch_status, apply_status, source_drift, payload_fingerprint
                    FROM ct_fetch_apply_evidence
                    WHERE run_id = CAST(:run_id AS UUID)
                    ORDER BY model, detection_sequence
                    """
                ),
                {"run_id": run_id},
            ).mappings().all()
        ]


def _snapshot_rows(engine, run_id):
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT model, record_id, document_number, state, company_id,
                           company_name, write_date, payload
                    FROM ct_native_record_snapshot
                    WHERE extraction_run_id = CAST(:run_id AS UUID)
                    ORDER BY model, record_id
                    """
                ),
                {"run_id": run_id},
            ).mappings().all()
        ]


def _pipeline_to_fetching(engine, *, domains=("commercial",), fake=None):
    run = _create_run(engine, list(domains))
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    fake = fake or FakeOdoo(_rows())
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=run, company_id=3, selected_domains=list(domains),
        odoo_client=fake, now=STAMP,
    )
    row = _run_row(engine, run)
    assert row["status"] == "DETECTING_CHANGES"
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' WHERE run_id=CAST(:run_id AS UUID)"),
            {"run_id": run},
        )
    return run

# --- migration 004 ----------------------------------------------------------

def test_migration_004_upgrade_and_downgrade(engine):
    with engine.connect() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename LIKE 'ct_fetch_apply%'"
                )
            ).all()
        }
        assert {"ct_fetch_apply_run", "ct_fetch_apply_evidence", "ct_fetch_apply_batch"} <= tables
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "005"
    _downgrade_004()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "004"
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='ct_fetch_apply_run' "
                    "AND column_name LIKE 'field_contract%'"
                )
            ).all()
        }
        assert columns == set()
    _downgrade_003()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT to_regclass('public.ct_fetch_apply_evidence')")).scalar() is None
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "003"
    _upgrade_004()
    _upgrade_005()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "005"


def test_schema_guard_requires_revision_005(engine):
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='003'"))
    with pytest.raises(Phase8SchemaNotReady, match="revision 005"):
        ensure_phase8_fetch_schema_ready(_client(engine))
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='004'"))
    with pytest.raises(Phase8SchemaNotReady, match="revision 005"):
        ensure_phase8_fetch_schema_ready(_client(engine))
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='005'"))
    ensure_phase8_fetch_schema_ready(_client(engine))


def test_earlier_stage_guards_still_accept_their_revisions(engine):
    from src.control_tower.schema_guard import (
        ensure_phase8_detection_schema_ready,
        ensure_phase8_schema_ready,
    )

    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='004'"))
    ensure_phase8_detection_schema_ready(_client(engine))
    ensure_phase8_schema_ready(_client(engine))
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='005'"))
    ensure_phase8_detection_schema_ready(_client(engine))


def test_fetch_evidence_db_constraints_company_isolation(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    rows = _evidence_rows(engine, run)
    assert len(rows) == 3
    assert all(row["company_id"] == 3 for row in rows)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ct_fetch_apply_evidence
                        (run_id, company_id, model, record_id, detection_sequence,
                         batch_number, detection_source_write_date, fetched_write_date,
                         fetch_status, apply_status, source_drift, payload_fingerprint,
                         fetched_at, applied_at, error_evidence)
                    VALUES (CAST(:run_id AS UUID), 99, 'sale.order', 999, 999, 1,
                            :stamp, :stamp, 'FETCHED', 'INSERTED', FALSE, 'x', :stamp, :stamp, NULL)
                    """
                ),
                {"run_id": run, "stamp": STAMP},
            )


# --- full pipeline to RECONCILING -------------------------------------------

def test_full_fetch_apply_to_reconciling(engine):
    run = _pipeline_to_fetching(engine)
    before_wm = _wm_snapshot(engine)
    before_pointer = _pointer(engine)
    source_count = _snapshot_count(engine, PHASE7_BASE_RUN_ID)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    assert result["records_requested"] == 3
    assert result["records_fetched"] == 3
    assert result["inserted"] == 3
    assert result["applied_total"] == 3
    assert _run_row(engine, run)["status"] == "RECONCILING"
    assert len(_evidence_rows(engine, run)) == 3
    assert len(_snapshot_rows(engine, run)) == source_count + 3
    progress = _progress(engine, run)
    assert progress["fetch_apply_complete"] is True
    assert progress["fetch_apply_completion_fingerprint"]
    header = _header(engine, run)
    assert header["status"] == "COMPLETE"
    assert len(header["completion_fingerprint"]) == 64
    assert _wm_snapshot(engine) == before_wm
    assert _pointer(engine) == before_pointer


def test_completed_reuse_makes_zero_odoo_calls(engine):
    run = _pipeline_to_fetching(engine)
    first = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert first["current_state"] == "RECONCILING"
    progress_before = _progress(engine, run)
    second = _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)
    assert second["idempotent"] is True
    assert second["current_state"] == "RECONCILING"
    assert _progress(engine, run) == progress_before
    assert len(_evidence_rows(engine, run)) == 3
    assert len(_snapshot_rows(engine, run)) == 1 + 3


# --- classification ----------------------------------------------------------

def test_insert_update_unchanged_classification(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    evidence = _evidence_rows(engine, run)
    by_id = {(row["model"], row["record_id"]): row for row in evidence}
    assert by_id[("sale.order", 1)]["apply_status"] == "INSERTED"
    assert by_id[("sale.order.line", 11)]["apply_status"] == "INSERTED"
    assert by_id[("sale.order.line", 12)]["apply_status"] == "INSERTED"
    first_fingerprint = by_id[("sale.order", 1)]["payload_fingerprint"]
    snapshot = _snapshot_rows(engine, run)
    so_row = next(row for row in snapshot if row["model"] == "sale.order" and row["record_id"] == 1)
    assert len(so_row["payload"]) > 3

    changed = _rows()
    changed["sale.order"][0] = dict(changed["sale.order"][0])
    changed["sale.order"][0]["state"] = "cancel"
    changed["sale.order"][0]["write_date"] = "2026-01-01 10:00:05"
    second_run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=second_run, company_id=3, odoo_client=FakeOdoo(changed), now=STAMP)
    second_evidence = _evidence_rows(engine, second_run)
    second_by_id = {(row["model"], row["record_id"]): row for row in second_evidence}
    assert second_by_id[("sale.order", 1)]["apply_status"] == "INSERTED"
    assert second_by_id[("sale.order", 1)]["source_drift"] is True
    assert second_by_id[("sale.order", 1)]["payload_fingerprint"] != first_fingerprint


def _canonical_payload_json(model, record):
    metadata = {
        field: {
            "type": _DEFAULT_FIELD_TYPES.get(field, "char"),
            "relation": _RELATION_TARGETS.get(field),
        }
        for field in record
    }
    normalized = _normalize_record(record, model, 3, metadata)
    return json.dumps(normalized["payload"], sort_keys=True, separators=(",", ":"), default=str)


def test_unchanged_apply_is_idempotent_on_repeat_fetch(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    for model, records in rows.items():
        for record in records:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO ct_native_record_snapshot
                            (extraction_run_id, model, record_id, document_number, state,
                             company_id, company_name, write_date, payload, extracted_at)
                        VALUES (CAST(:run_id AS UUID), :model, :record_id, :document_number,
                                :state, :company_id, :company_name, :write_date,
                                CAST(:payload AS JSONB), :extracted_at)
                        """
                    ),
                    {
                        "run_id": run, "model": model, "record_id": record["id"],
                        "document_number": record.get("name") or record.get("display_name"),
                        "state": record.get("state") or record.get("request_status") or record.get("x_studio_status"),
                        "company_id": 3, "company_name": "Nobi",
                        "write_date": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
                        "payload": _canonical_payload_json(model, record),
                        "extracted_at": STAMP,
                    },
                )
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)
    assert result["unchanged"] == 3
    assert result["inserted"] == 0
    assert result["applied_total"] == 3
    progress = _progress(engine, run)
    assert progress["fetch_apply_unchanged"] == 3


# --- missing at fetch --------------------------------------------------------

def test_missing_at_fetch_is_durable_and_unresolved(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"] = []
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)
    assert result["records_missing_at_fetch"] == 1
    assert result["records_fetched"] == 2
    assert _run_row(engine, run)["status"] == "RECONCILING"
    evidence = _evidence_rows(engine, run)
    missing = [row for row in evidence if row["fetch_status"] == "MISSING_AT_FETCH"]
    assert len(missing) == 1
    assert missing[0]["model"] == "sale.order" and missing[0]["record_id"] == 1
    assert missing[0]["apply_status"] == "MISSING_AT_FETCH"
    assert missing[0]["payload_fingerprint"] is None
    manifest = _manifest_rows(engine, run)
    assert next(row for row in manifest if row["model"] == "sale.order")["status"] == "MISSING_AT_FETCH"
    snapshots = _snapshot_rows(engine, run)
    assert not any(row["model"] == "sale.order" and row["record_id"] == 1 for row in snapshots)


# --- source drift ------------------------------------------------------------

def test_newer_at_fetch_is_accepted_with_drift(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"][0] = dict(rows["sale.order"][0])
    rows["sale.order"][0]["write_date"] = "2026-01-01 10:00:30"
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)
    assert result["source_drift"] == 1
    evidence = _evidence_rows(engine, run)
    so = next(row for row in evidence if row["model"] == "sale.order")
    assert so["source_drift"] is True


def test_older_at_fetch_fails_closed(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"][0] = dict(rows["sale.order"][0])
    rows["sale.order"][0]["write_date"] = "2026-01-01 09:59:00"
    with pytest.raises(FetchApplyError, match="older than detection"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)
    assert _run_row(engine, run)["status"] == "FETCHING"
    assert _evidence_count(engine, run) == 0


# --- malformed payloads ------------------------------------------------------

def test_wrong_company_payload_rejected(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"][0] = dict(rows["sale.order"][0])
    rows["sale.order"][0]["company_id"] = [4, "Other"]
    with pytest.raises(FetchApplyError, match="crossed company"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=UnfilteredOdoo(rows), now=STAMP)


def test_missing_required_field_rejected(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"][0] = {key: value for key, value in rows["sale.order"][0].items() if key != "state"}
    with pytest.raises(FetchApplyError, match="omitted approved fields"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)


class _UnfilteredFieldsOdoo(FakeOdoo):
    """Rogue client that returns every stored field regardless of the request."""

    def _wire(self, row, fields=None):
        out = {key: value for key, value in row.items() if key != "_true_write_date"}
        out["write_date"] = self._true_ts(row).strftime("%Y-%m-%d %H:%M:%S")
        return out


def test_unexpected_field_rejected(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"][0] = dict(rows["sale.order"][0])
    rows["sale.order"][0]["evil_field"] = True
    with pytest.raises(FetchApplyError, match="unexpected fields"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=_UnfilteredFieldsOdoo(rows), now=STAMP)


def test_malformed_relation_rejected(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order.line"][0] = dict(rows["sale.order.line"][0])
    rows["sale.order.line"][0]["order_id"] = "not-a-relation"
    with pytest.raises(FetchApplyError, match="many2one"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)


def test_duplicate_conflicting_rows_rejected(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"] = [rows["sale.order"][0], dict(rows["sale.order"][0])]
    with pytest.raises(FetchApplyError, match="duplicate conflicting"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)


def test_unrequested_record_rejected(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"] = [dict(rows["sale.order"][0]), {"id": 999, "name": "X", "state": "x",
                                                       "company_id": [3, "Nobi"], "partner_id": False,
                                                       "client_order_ref": False, "x_studio_tanggal_po_cust": False,
                                                       "x_studio_io_1": False, "date_order": False,
                                                       "commitment_date": False, "write_date": WIRE}]
    with pytest.raises(FetchApplyError, match="unrequested record"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=UnfilteredOdoo(rows), now=STAMP)

def _wm_snapshot(engine):
    with engine.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                text(
                    """
                    SELECT model, last_successful_write_date::text, last_successful_id,
                           overlap_seconds, status
                    FROM ct_control_tower_watermark WHERE company_id=3 ORDER BY model
                    """
                )
            ).all()
        ]


def _pointer(engine):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT run_id::text FROM ct_published_snapshot WHERE company_id=3")
        ).scalar()


def _header(engine, run_id):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT run_id::text, company_id, base_snapshot_run_id::text,
                       selected_domains, models, manifest_completion_fingerprint,
                       manifest_row_count, batch_size, contract_version, status,
                       started_at, finished_at, duration_seconds,
                       completion_fingerprint, model_fetch_counts
                FROM ct_fetch_apply_run WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).mappings().first()
    return dict(row) if row else None


def _snapshot_count(engine, run_id):
    with engine.connect() as conn:
        return conn.execute(
            text(
                """
                SELECT COUNT(*) FROM ct_native_record_snapshot
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).scalar()


def _evidence_count(engine, run_id):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT COUNT(*) FROM ct_fetch_apply_evidence WHERE run_id = CAST(:run_id AS UUID)"
            ),
            {"run_id": run_id},
        ).scalar()


def _move_pointer(engine):
    svc = RefreshRunStateService(_client(engine))
    other = svc.create_run(company_id=3, selected_domains=["commercial"], now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_extraction_run
                SET status='COMPLETED', completed_at=:now, finished_at=:now, published_at=:now
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": other["run_id"], "now": STAMP},
        )
        conn.execute(
            text(
                """
                UPDATE ct_published_snapshot SET run_id = CAST(:run_id AS UUID)
                WHERE company_id=3
                """
            ),
            {"run_id": other["run_id"]},
        )
    return other["run_id"]


class NoCallOdoo:
    def __getattr__(self, name):
        raise AssertionError(f"idempotent fetch/apply must not call Odoo: {name}")


def _boom(name):
    raise RuntimeError("injected " + name)


# --- partial fetch resume ----------------------------------------------------

def test_partial_fetch_resumes_from_proven_boundary(engine):
    run = _pipeline_to_fetching(engine)
    calls = {"n": 0}

    def fail_second_model(_name):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("injected model failure")

    with pytest.raises(RuntimeError, match="injected model failure"):
        _service(engine, hooks={"before_fetch": fail_second_model}).run(
            run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    row = _run_row(engine, run)
    assert row["status"] == "FETCHING"
    first_model_evidence = [e for e in _evidence_rows(engine, run) if e["model"] == "sale.order"]
    assert len(first_model_evidence) == 1
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    assert len(_evidence_rows(engine, run)) == 3
    assert _evidence_count(engine, run) == 3
    assert _snapshot_count(engine, run) == 1 + 3
    progress = _progress(engine, run)
    assert progress["fetch_apply_records_fetched"] == 3


def test_partial_batch_rolls_back_atomically(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order.line"] = [rows["sale.order.line"][0], dict(rows["sale.order.line"][1])]
    rows["sale.order.line"][1]["order_id"] = "broken"
    with pytest.raises(FetchApplyError, match="many2one"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=UnfilteredOdoo(rows), now=STAMP)
    assert _evidence_count(engine, run) == 1
    assert _snapshot_count(engine, run) == 1 + 1
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    assert _evidence_count(engine, run) == 3


def test_failure_after_persist_before_completion_resumes_without_odoo(engine):
    run = _pipeline_to_fetching(engine)
    with pytest.raises(RuntimeError, match="injected before_completion"):
        _service(engine, hooks={"before_completion": _boom}).run(
            run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    assert _evidence_count(engine, run) == 3
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    assert result["idempotent"] is False


def test_failure_after_transition_resumes_idempotently(engine):
    run = _pipeline_to_fetching(engine)
    with pytest.raises(RuntimeError, match="injected after_transition"):
        _service(engine, hooks={"after_transition": _boom}).run(
            run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    assert _run_row(engine, run)["status"] == "RECONCILING"
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    assert result["idempotent"] is True


# --- concurrency -------------------------------------------------------------

def test_same_run_concurrency_single_winner(engine):
    run = _pipeline_to_fetching(engine)
    entered = __import__("threading").Event()
    svc = _service(engine, hooks={"before_fetch": lambda _: entered.set()})
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(svc.run, run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
            for _ in range(2)
        ]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(("ok", future.result()))
            except Exception as exc:
                outcomes.append(("error", type(exc).__name__))
    assert any(outcome[0] == "ok" for outcome in outcomes)
    assert _run_row(engine, run)["status"] == "RECONCILING"
    assert _evidence_count(engine, run) == 3
    assert _snapshot_count(engine, run) == 1 + 3

# --- fail-closed guards ------------------------------------------------------

def test_stale_pointer_fails_closed(engine):
    run = _pipeline_to_fetching(engine)
    _move_pointer(engine)
    with pytest.raises(FetchApplyError, match="stale"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)


def test_wrong_company_fails_closed(engine):
    run = _pipeline_to_fetching(engine)
    with pytest.raises(FetchApplyError, match="company"):
        _service(engine).run(run_id=run, company_id=4, odoo_client=FakeOdoo(_rows()), now=STAMP)


def test_non_fetching_state_fails_closed(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with pytest.raises(FetchApplyError, match="not FETCHING"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)


def test_zero_manifest_fails_closed(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo({model: [] for model in COMMERCIAL_MODELS}), now=STAMP,
    )
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' WHERE run_id=CAST(:run_id AS UUID)"),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="non-empty completed manifest"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)


def test_incomplete_detection_fails_closed(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' WHERE run_id=CAST(:run_id AS UUID)"),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="detection header is missing"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)


def test_forged_completion_progress_rejected(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_extraction_run
                SET progress = progress || '{"fetch_apply_complete": true}'::jsonb
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(ProgressContractError, match="Completed fetch/apply requires planned models"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_candidate_row_tampering_detected(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_native_record_snapshot
                SET payload = payload || '{"tampered": true}'::jsonb
                WHERE extraction_run_id = CAST(:run_id AS UUID)
                  AND model = 'sale.order' AND record_id = 1
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="no longer matches recorded application evidence"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_stale_fetch_header_contradiction_rejected(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ct_fetch_apply_run
                    (run_id, company_id, base_snapshot_run_id, selected_domains, models,
                     manifest_completion_fingerprint, manifest_row_count, batch_size,
                     contract_version, field_contract_version,
                     field_contract_allowlist_fingerprint, status, started_at)
                VALUES (CAST(:run_id AS UUID), 3, CAST(:base AS UUID), '["commercial"]'::jsonb,
                        '["sale.order","sale.order.line"]'::jsonb, :fingerprint, 3, 500,
                        :version, :fc_version, :fc_fp, 'RUNNING', :stamp)
                """
            ),
            {
                "run_id": run, "base": PHASE7_BASE_RUN_ID,
                "fingerprint": "0" * 64, "version": FETCH_APPLY_CONTRACT_VERSION,
                "fc_version": FETCH_APPLY_CONTRACT_VERSION, "fc_fp": "e" * 64, "stamp": STAMP,
            },
        )
    with pytest.raises(FetchApplyError, match="immutable inputs contradict"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)


def test_unfiltered_odoo_fails_closed(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"].append({"id": 999, "name": "X", "state": "x", "company_id": [3, "Nobi"],
                               "partner_id": False, "client_order_ref": False,
                               "x_studio_tanggal_po_cust": False, "x_studio_io_1": False,
                               "date_order": False, "commitment_date": False, "write_date": WIRE})
    with pytest.raises(FetchApplyError, match="unrequested record"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=UnfilteredOdoo(rows), now=STAMP)


# --- immutability ------------------------------------------------------------

def test_source_snapshot_pointer_watermarks_unchanged(engine):
    run = _pipeline_to_fetching(engine)
    source_rows = _snapshot_rows(engine, PHASE7_BASE_RUN_ID)
    before_wm = _wm_snapshot(engine)
    before_pointer = _pointer(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert _snapshot_rows(engine, PHASE7_BASE_RUN_ID) == source_rows
    assert _wm_snapshot(engine) == before_wm
    assert _pointer(engine) == before_pointer
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM ct_parent_reconciliation_queue")).scalar()
        assert count == 0


# --- CT-8C2-R1 blocker regressions -------------------------------------------

def test_orchestrator_reconciling_reuse_detects_evidence_tampering(engine):
    from src.control_tower.orchestration import RefreshPipelineOrchestrator

    run = _pipeline_to_fetching(engine)
    orch = RefreshPipelineOrchestrator(_client(engine))
    first = orch.orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    assert first["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_fetch_apply_evidence
                SET detection_sequence = 99
                WHERE run_id = CAST(:run_id AS UUID)
                  AND model = 'sale.order.line' AND record_id = 11
                """
            ),
            {"run_id": run},
        )
    with pytest.raises((FetchApplyError, OrchestrationError)):
        orch.orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=NoCallOdoo(), now=STAMP,
        )


def test_direct_completed_reuse_fails_after_stale_pointer(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    _move_pointer(engine)
    with pytest.raises(FetchApplyError, match="stale"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_orchestrator_completed_reuse_fails_after_stale_pointer(engine):
    from src.control_tower.orchestration import RefreshPipelineOrchestrator

    run = _pipeline_to_fetching(engine)
    orch = RefreshPipelineOrchestrator(_client(engine))
    result = orch.orchestrate(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    assert result["current_state"] == "RECONCILING"
    _move_pointer(engine)
    with pytest.raises(OrchestrationError, match="stale"):
        orch.orchestrate(
            run_id=run, company_id=3, selected_domains=["commercial"],
            odoo_client=NoCallOdoo(), now=STAMP,
        )


def test_manifest_record_id_substitution_detected_before_fetch(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_change_manifest SET record_id = 9999
                WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order' AND record_id = 1
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="fingerprint changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert _evidence_count(engine, run) == 0


def test_manifest_source_write_date_alteration_detected(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_change_manifest SET source_write_date = '2026-01-01 10:00:30+00'
                WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order' AND record_id = 1
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="fingerprint changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert _evidence_count(engine, run) == 0


def test_manifest_detection_sequence_alteration_detected(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_change_manifest SET detection_sequence = 999
                WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order' AND record_id = 1
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="fingerprint changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert _evidence_count(engine, run) == 0


def test_manifest_same_count_row_swap_detected(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_change_manifest SET record_id = 9999
                WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order' AND record_id = 1
                """
            ),
            {"run_id": run},
        )
        conn.execute(
            text(
                """
                UPDATE ct_change_manifest SET record_id = 1
                WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order.line' AND record_id = 11
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="fingerprint changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert _evidence_count(engine, run) == 0


def test_detection_header_domain_change_detected(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_change_detection_run
                SET selected_domains = '["warehouse"]'::jsonb
                WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="selected domains changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert _evidence_count(engine, run) == 0


def test_db_rejects_wrong_company_header(engine):
    run = _pipeline_to_fetching(engine)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ct_fetch_apply_run
                        (run_id, company_id, base_snapshot_run_id, selected_domains, models,
                         manifest_completion_fingerprint, manifest_row_count, batch_size,
                         contract_version, field_contract_version,
                         field_contract_allowlist_fingerprint, status, started_at)
                    VALUES (CAST(:run_id AS UUID), 99, CAST(:base AS UUID),
                            '["commercial"]'::jsonb, '["sale.order"]'::jsonb,
                            :fingerprint, 1, 500, :version, :fc_version, :fc_fp,
                            'RUNNING', :stamp)
                    """
                ),
                {
                    "run_id": run, "base": PHASE7_BASE_RUN_ID,
                    "fingerprint": "a" * 64, "version": "ct-fetch-apply-v1",
                    "fc_version": "ct-fetch-apply-v1", "fc_fp": "e" * 64, "stamp": STAMP,
                },
            )


def test_db_rejects_fetched_without_applied_at(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ct_fetch_apply_run
                    (run_id, company_id, base_snapshot_run_id, selected_domains, models,
                     manifest_completion_fingerprint, manifest_row_count, batch_size,
                     contract_version, field_contract_version,
                     field_contract_allowlist_fingerprint, status, started_at)
                VALUES (CAST(:run_id AS UUID), 3, CAST(:base AS UUID),
                        '["commercial"]'::jsonb, '["sale.order","sale.order.line"]'::jsonb,
                        :fingerprint, 3, 500, :version, :fc_version, :fc_fp,
                        'RUNNING', :stamp)
                """
            ),
            {
                "run_id": run, "base": PHASE7_BASE_RUN_ID,
                "fingerprint": "b" * 64, "version": "ct-fetch-apply-v1",
                "fc_version": "ct-fetch-apply-v1", "fc_fp": "e" * 64, "stamp": STAMP,
            },
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ct_fetch_apply_evidence
                        (run_id, company_id, model, record_id, detection_sequence,
                         batch_number, detection_source_write_date, fetched_write_date,
                         fetch_status, apply_status, source_drift, payload_fingerprint,
                         fetched_at, applied_at, error_evidence)
                    VALUES (CAST(:run_id AS UUID), 3, 'sale.order', 1, 1, 1,
                            :stamp, :stamp, 'FETCHED', 'INSERTED', FALSE,
                            :fingerprint, :stamp, NULL, NULL)
                    """
                ),
                {"run_id": run, "stamp": STAMP, "fingerprint": "c" * 64},
            )


def test_db_rejects_malformed_fingerprint(engine):
    run = _pipeline_to_fetching(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ct_fetch_apply_run
                    (run_id, company_id, base_snapshot_run_id, selected_domains, models,
                     manifest_completion_fingerprint, manifest_row_count, batch_size,
                     contract_version, field_contract_version,
                     field_contract_allowlist_fingerprint, status, started_at)
                VALUES (CAST(:run_id AS UUID), 3, CAST(:base AS UUID),
                        '["commercial"]'::jsonb, '["sale.order"]'::jsonb,
                        :fingerprint, 1, 500, :version, :fc_version, :fc_fp,
                        'RUNNING', :stamp)
                """
            ),
            {
                "run_id": run, "base": PHASE7_BASE_RUN_ID,
                "fingerprint": "d" * 64, "version": "ct-fetch-apply-v1",
                "fc_version": "ct-fetch-apply-v1", "fc_fp": "e" * 64, "stamp": STAMP,
            },
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO ct_fetch_apply_evidence
                        (run_id, company_id, model, record_id, detection_sequence,
                         batch_number, detection_source_write_date, fetched_write_date,
                         fetch_status, apply_status, source_drift, payload_fingerprint,
                         fetched_at, applied_at, error_evidence)
                    VALUES (CAST(:run_id AS UUID), 3, 'sale.order', 1, 1, 1,
                            :stamp, :stamp, 'FETCHED', 'INSERTED', FALSE,
                            'not-a-fingerprint', :stamp, :stamp, NULL)
                    """
                ),
                {"run_id": run, "stamp": STAMP},
            )


def test_completed_reuse_detects_batch_count_tampering(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_fetch_apply_batch
                SET inserted = 0, updated = 1
                WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order' AND batch_number = 1
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_completed_reuse_detects_evidence_row_substitution(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_fetch_apply_evidence
                SET detection_sequence = 99, detection_source_write_date = '2026-01-01 10:00:05+00'
                WHERE run_id = CAST(:run_id AS UUID)
                  AND model = 'sale.order.line' AND record_id = 11
                """
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_stale_writer_finalize_fails_closed(engine):
    run = _pipeline_to_fetching(engine)
    entered = __import__("threading").Event()

    def move_run(_name):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE ct_extraction_run SET status='VALIDATING', stage='VALIDATING' "
                    "WHERE run_id = CAST(:run_id AS UUID)"
                ),
                {"run_id": run},
            )

    with pytest.raises(FetchApplyError, match="Stale refresh run state"):
        _service(engine, hooks={"before_completion": move_run}).run(
            run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    with engine.connect() as conn:
        header_status = conn.execute(
            text("SELECT status FROM ct_fetch_apply_run WHERE run_id = CAST(:run_id AS UUID)"),
            {"run_id": run},
        ).scalar()
    assert header_status != "COMPLETE"


def test_migration_005_upgrade_use_downgrade(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.connect() as conn:
        header = conn.execute(
            text(
                "SELECT field_contract_version, field_contract_fingerprint, "
                "field_contract_allowlist_fingerprint FROM ct_fetch_apply_run "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        ).mappings().one()
    assert header["field_contract_version"] == "ct-fetch-apply-v1"
    assert len(header["field_contract_fingerprint"]) == 64
    assert len(header["field_contract_allowlist_fingerprint"]) == 64
    _downgrade_004()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "004"
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name='ct_fetch_apply_run' "
                    "AND column_name LIKE 'field_contract%'"
                )
            ).all()
        }
        assert columns == set()
    _upgrade_005()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "005"


def test_migration_004_downgrade_with_missing_at_fetch_data(engine):
    run = _pipeline_to_fetching(engine)
    rows = _rows()
    rows["sale.order"] = []
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)
    assert result["records_missing_at_fetch"] == 1
    with engine.connect() as conn:
        missing = conn.execute(
            text(
                "SELECT COUNT(*) FROM ct_change_manifest "
                "WHERE run_id = CAST(:run_id AS UUID) AND status = 'MISSING_AT_FETCH'"
            ),
            {"run_id": run},
        ).scalar()
    assert missing == 1
    _downgrade_003()
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "003"
        leftover = conn.execute(
            text("SELECT COUNT(*) FROM ct_change_manifest WHERE run_id = CAST(:run_id AS UUID)"),
            {"run_id": run},
        ).scalar()
        assert leftover == 3
    _upgrade_004()


# --- CT-8C2-R2 blocker regressions -------------------------------------------

def test_completed_header_contract_version_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE ct_fetch_apply_run SET contract_version='tampered' WHERE run_id=CAST(:run_id AS UUID)"),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="immutable inputs contradict"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_completed_run_selected_domains_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET selected_domains='[\"warehouse\"]'::jsonb "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="selected domains"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_completed_header_base_and_batch_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_run SET batch_size=999 WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="immutable inputs contradict"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_run SET models='[\"sale.order\"]'::jsonb "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="immutable inputs contradict"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_field_contract_change_invalidates_completed_reuse(engine):
    from src.control_tower import fetch_apply as fa_mod

    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"

    original_build = fa_mod._build_field_contract

    def changed_build(model):
        fields = original_build(model)
        if model == "sale.order":
            fields = fields + ("x_studio_extra_new_field",)
        return fields

    fa_mod._build_field_contract = changed_build
    try:
        with pytest.raises(FetchApplyError, match="immutable inputs contradict"):
            _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)
    finally:
        fa_mod._build_field_contract = original_build


def test_completed_evidence_timestamp_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_evidence SET fetched_at = fetched_at + interval '1 hour' "
                "WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order'"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_completed_error_evidence_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_evidence SET error_evidence = CAST(:ev AS JSONB) "
                "WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order'"
            ),
            {"run_id": run, "ev": '{"x":1}'},
        )
    with pytest.raises(FetchApplyError):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_completed_batch_completed_at_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_batch SET completed_at = completed_at + interval '1 hour' "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_completed_model_fetch_counts_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_run SET model_fetch_counts = CAST(:counts AS JSONB) "
                "WHERE run_id = CAST(:run_id AS UUID)"
            ),
            {"run_id": run, "counts": '{"sale.order":{"records_requested":99}}'},
        )
    with pytest.raises(FetchApplyError, match="model counts contradict"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_completed_progress_count_contradiction_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET progress = progress || "
                "'{\"fetch_apply_records_fetched\": 99}'::jsonb "
                "WHERE run_id = CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    with pytest.raises((FetchApplyError, ProgressContractError)):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_false_drift_with_newer_timestamp_fails(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_evidence SET fetched_write_date = '2026-01-01 10:00:05+00', "
                "source_drift = FALSE WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order'"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="source-drift flag is inconsistent"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_true_drift_without_newer_timestamp_rejected_by_db(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE ct_fetch_apply_evidence SET source_drift = TRUE "
                    "WHERE run_id = CAST(:run_id AS UUID) AND model = 'sale.order'"
                ),
                {"run_id": run},
            )


def test_mismatched_batch_drift_total_fails(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_batch SET source_drift = 1 "
                "WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order.line' AND batch_number=1"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="source-drift count does not reconcile"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_manifest_status_mismatch_fails_completed_reuse(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_change_manifest SET status='DETECTED' "
                "WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order' AND record_id=1"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="lifecycle status"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_missing_baseline_candidate_deletion_fails(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    fetch_rows = _rows()
    fetch_rows["sale.order"] = []
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(fetch_rows), now=STAMP)
    assert result["records_missing_at_fetch"] == 1
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ct_native_record_snapshot "
                "(extraction_run_id, model, record_id, payload, extracted_at) "
                "VALUES (CAST(:run_id AS UUID), 'sale.order', 1, "
                "'{\"x\" : 1}'::jsonb, :stamp)"
            ),
            {"run_id": run, "stamp": STAMP},
        )
    with pytest.raises(FetchApplyError, match="baseline policy"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_missing_baseline_base_exists_candidate_deleted_fails(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ct_native_record_snapshot "
                "(extraction_run_id, model, record_id, payload, extracted_at) "
                "VALUES (CAST(:base AS UUID), 'sale.order', 1, "
                "'{\"x\" : 1}'::jsonb, :stamp)"
            ),
            {"base": PHASE7_BASE_RUN_ID, "stamp": STAMP},
        )
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    rows = _rows()
    rows["sale.order"] = []
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(rows), now=STAMP)
    assert result["records_missing_at_fetch"] == 1
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM ct_native_record_snapshot "
                "WHERE extraction_run_id=CAST(:run_id AS UUID) AND model='sale.order' AND record_id=1"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="baseline policy"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_missing_baseline_absent_consistency_passes(engine):
    run = _pipeline_to_fetching(engine)
    fetch_rows = _rows()
    fetch_rows["sale.order"] = []
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(fetch_rows), now=STAMP)
    assert result["records_missing_at_fetch"] == 1
    assert result["current_state"] == "RECONCILING"
    second = _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)
    assert second["idempotent"] is True


def test_candidate_column_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_native_record_snapshot SET state='tampered' "
                "WHERE extraction_run_id=CAST(:run_id AS UUID) AND model='sale.order' AND record_id=1"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="Candidate state changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_candidate_write_date_column_tampering_fails(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_native_record_snapshot SET write_date='2026-01-01 09:00:00' "
                "WHERE extraction_run_id=CAST(:run_id AS UUID) AND model='sale.order' AND record_id=1"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="write_date changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_batch_membership_shuffle_fails(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_fetch_apply_evidence SET batch_number = 2 "
                "WHERE run_id=CAST(:run_id AS UUID) AND model='sale.order.line' AND record_id=11"
            ),
            {"run_id": run},
        )
        conn.execute(
            text(
                "INSERT INTO ct_fetch_apply_batch (run_id, model, batch_number, records_requested, "
                "records_fetched, records_missing, inserted, updated, unchanged, source_drift, completed_at) "
                "VALUES (CAST(:run_id AS UUID), 'sale.order.line', 2, 2, 2, 0, 2, 0, 0, 0, :stamp) "
                "ON CONFLICT DO NOTHING"
            ),
            {"run_id": run, "stamp": STAMP},
        )
    with pytest.raises(FetchApplyError):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_fetching_with_complete_evidence_no_false_success(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="false success"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


# --- CT-8C2-R3 final contract regressions ------------------------------------

def test_fetch_service_guard_rejects_revision_004(engine):
    from src.control_tower.schema_guard import Phase8SchemaNotReady

    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='004'"))
    with pytest.raises(Phase8SchemaNotReady, match="revision 005"):
        FetchApplyService(_client(engine))
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='005'"))
    FetchApplyService(_client(engine))


def test_metadata_relation_target_change_blocks_resume(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    with pytest.raises(RuntimeError, match="injected before_fetch"):
        _service(engine, hooks={"before_fetch": _boom}).run(
            run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP,
        )
    tampered = FakeOdoo(_rows())
    tampered._fields = dict(tampered._fields)
    tampered._fields["sale.order"] = dict(tampered._fields["sale.order"])
    tampered._fields["sale.order"]["company_id"] = {
        "type": "many2one", "relation": "res.company.tampered",
    }
    with pytest.raises(FetchApplyError, match="metadata no longer matches"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=tampered, now=STAMP)


def test_missing_metadata_for_approved_field_fails_before_fetch(engine):
    run = _pipeline_to_fetching(engine)
    fake = FakeOdoo(_rows())
    fake._fields = dict(fake._fields)
    fake._fields["sale.order"] = {
        key: value for key, value in fake._fields["sale.order"].items() if key != "state"
    }
    with pytest.raises(FetchApplyError, match="missing a definition for approved field sale.order.state"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    assert _evidence_count(engine, run) == 0


def test_blank_metadata_field_type_fails_closed(engine):
    run = _pipeline_to_fetching(engine)
    fake = FakeOdoo(_rows())
    fake._fields = dict(fake._fields)
    fake._fields["sale.order"] = dict(fake._fields["sale.order"])
    fake._fields["sale.order"]["state"] = {"type": "", "relation": None}
    with pytest.raises(FetchApplyError, match="blank or malformed field type"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    assert _evidence_count(engine, run) == 0


def test_missing_at_fetch_present_row_payload_tamper_fails(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ct_native_record_snapshot "
                "(extraction_run_id, model, record_id, payload, extracted_at) "
                "VALUES (CAST(:base AS UUID), 'sale.order', 1, "
                "'{\"x\" : 1}'::jsonb, :stamp)"
            ),
            {"base": PHASE7_BASE_RUN_ID, "stamp": STAMP},
        )
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    fetch_rows = _rows()
    fetch_rows["sale.order"] = []
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(fetch_rows), now=STAMP)
    assert result["records_missing_at_fetch"] == 1
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_native_record_snapshot SET payload = CAST(:p AS JSONB) "
                "WHERE extraction_run_id=CAST(:run_id AS UUID) AND model='sale.order' AND record_id=1"
            ),
            {"run_id": run, "p": '{"x":2}'},
        )
    with pytest.raises(FetchApplyError, match="exact copy of the base"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_missing_at_fetch_present_row_document_tamper_fails(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ct_native_record_snapshot "
                "(extraction_run_id, model, record_id, document_number, payload, extracted_at) "
                "VALUES (CAST(:base AS UUID), 'sale.order', 1, 'BASE-DOC', "
                "'{\"x\" : 1}'::jsonb, :stamp)"
            ),
            {"base": PHASE7_BASE_RUN_ID, "stamp": STAMP},
        )
    CandidateSnapshotCopyForwardService(_client(engine)).copy_forward(run, company_id=3, now=STAMP)
    IncrementalChangeDetectionService(_client(engine)).detect(
        run_id=run, company_id=3, selected_domains=["commercial"],
        odoo_client=FakeOdoo(_rows()), now=STAMP,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_extraction_run SET status='FETCHING', stage='FETCHING' "
                "WHERE run_id=CAST(:run_id AS UUID)"
            ),
            {"run_id": run},
        )
    fetch_rows = _rows()
    fetch_rows["sale.order"] = []
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(fetch_rows), now=STAMP)
    assert result["records_missing_at_fetch"] == 1
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_native_record_snapshot SET document_number='TAMPERED' "
                "WHERE extraction_run_id=CAST(:run_id AS UUID) AND model='sale.order' AND record_id=1"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="exact copy of the base"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_fetched_company_name_tamper_fails(engine):
    run = _pipeline_to_fetching(engine)
    result = _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    assert result["current_state"] == "RECONCILING"
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE ct_native_record_snapshot SET company_name='TAMPERED' "
                "WHERE extraction_run_id=CAST(:run_id AS UUID) AND model='sale.order' AND record_id=1"
            ),
            {"run_id": run},
        )
    with pytest.raises(FetchApplyError, match="Candidate company name changed"):
        _service(engine).run(run_id=run, company_id=3, odoo_client=NoCallOdoo(), now=STAMP)


def test_no_reconciliation_or_watermark_advance(engine):
    run = _pipeline_to_fetching(engine)
    _service(engine).run(run_id=run, company_id=3, odoo_client=FakeOdoo(_rows()), now=STAMP)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ct_parent_reconciliation_queue")).scalar() == 0
        assert conn.execute(text("SELECT COUNT(*) FROM ct_parent_reconciliation_cursor")).scalar() == 0
        assert conn.execute(
            text("SELECT COUNT(*) FROM ct_control_tower_watermark WHERE checked_at IS NOT NULL")
        ).scalar() == 0
