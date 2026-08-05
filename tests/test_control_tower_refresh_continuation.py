"""CT-8E1 end-to-end incremental refresh continuation tests.

Mocked Odoo + disposable PostgreSQL.  These tests prove that a run that has
reached RECONCILING (changed) or VALIDATING (no changes) completes through
reconciliation, validation, derived-data refresh, atomic publication, and
watermark advancement, and that failures never move the trusted pointer or
advance watermarks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text

from src.control_tower.refresh import SQL_PATHS
from src.control_tower.refresh_continuation import RefreshContinuationError, RefreshContinuationService
from src.control_tower.refresh_state import RefreshRunStateService
from src.control_tower.orchestration import RefreshPipelineOrchestrator
from tests.control_tower_odoo_fake import FakeOdoo
from tests.test_control_tower_change_detection_postgres import _upgrade_003
from tests.test_control_tower_fetch_apply_postgres import _upgrade_004, _upgrade_005
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
TEST_DERIVED_BUNDLE = ROOT / "tests" / "ct_test_derived_bundle.sql"


def _client(engine):
    return SimpleNamespace(engine=engine)


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


def _create_run(engine, domains, *, company_id=3):
    svc = RefreshRunStateService(_client(engine))
    run = svc.create_run(company_id=company_id, selected_domains=domains, now=STAMP)
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


def _rows_no_change():
    return {
        "sale.order": [
            {"id": 700001, "name": "SO-PHASE8-TEST", "state": "sale",
             "company_id": [3, "Nobi"], "partner_id": [101, "Partner A"],
             "client_order_ref": "PHASE8", "x_studio_tanggal_po_cust": False,
             "x_studio_io_1": False, "date_order": "2026-01-01 08:00:00",
             "commitment_date": False, "write_date": "2026-01-01 09:00:00"},
        ],
        "sale.order.line": [
            {"id": 700002, "order_id": [700001, "SO-PHASE8-TEST"],
             "product_id": [501, "Product A"], "product_uom": [601, "Unit"],
             "product_uom_qty": 1.0, "qty_delivered": 0.0, "qty_invoiced": 0.0,
             "price_unit": 10.0, "write_date": "2026-01-01 09:00:00",
             "company_id": [3, "Nobi"]},
        ],
    }


def _run_row(engine, run_id):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT run_id::text, company_id, status, stage,
                       base_snapshot_run_id::text, progress, published_at,
                       completed_at, finished_at, duration_seconds, model_counts
                FROM ct_extraction_run WHERE run_id = CAST(:run_id AS UUID)
                """
            ),
            {"run_id": run_id},
        ).mappings().first()
    return dict(row)


def _pointer(engine):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT run_id::text FROM ct_published_snapshot WHERE company_id=3")
        ).scalar()


def _watermarks(engine):
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT model, last_successful_write_date::text, last_successful_id, status
            FROM ct_control_tower_watermark WHERE company_id=3 ORDER BY model
        """)).mappings().all()
    return {row["model"]: (row["last_successful_write_date"], row["last_successful_id"], row["status"]) for row in rows}


def _continuation(engine, *, sql_paths=(TEST_DERIVED_BUNDLE,)):
    return RefreshContinuationService(_client(engine), sql_paths=tuple(sql_paths))


def _orchestrate_to_boundary(engine, run_id, fake):
    RefreshPipelineOrchestrator(_client(engine)).orchestrate(
        run_id=run_id, company_id=3, selected_domains=["commercial"],
        odoo_client=fake, now=STAMP,
    )


# --- changed path -----------------------------------------------------------

def test_changed_run_completes_to_succeeded(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows())
    _orchestrate_to_boundary(engine, run, fake)
    assert _run_row(engine, run)["status"] == "RECONCILING"

    result = _continuation(engine).complete(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    assert result["current_state"] == "SUCCEEDED"
    row = _run_row(engine, run)
    assert row["status"] == "SUCCEEDED"
    assert row["stage"] == "SUCCEEDED"
    assert row["published_at"] is not None
    assert row["completed_at"] is not None
    assert row["finished_at"] is not None
    assert _pointer(engine) == run
    assert row["model_counts"] is not None

    wm = _watermarks(engine)
    assert wm["sale.order"][2] == "READY"
    assert wm["sale.order.line"][2] == "READY"

    with engine.connect() as conn:
        evidence = conn.execute(text("""
            SELECT published_run_id::text, snapshot_count FROM vw_ct_test_published_evidence
        """)).mappings().first()
    assert evidence["published_run_id"] == run
    assert evidence["snapshot_count"] >= 3


def test_no_change_run_completes_to_succeeded_no_changes(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows_no_change())
    _orchestrate_to_boundary(engine, run, fake)
    assert _run_row(engine, run)["status"] == "VALIDATING"

    result = _continuation(engine).complete(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    assert result["current_state"] == "SUCCEEDED_NO_CHANGES"
    assert result["no_changes"] is True
    row = _run_row(engine, run)
    assert row["status"] == "SUCCEEDED_NO_CHANGES"
    assert _pointer(engine) == PHASE7_BASE_RUN_ID
    wm = _watermarks(engine)
    assert wm["sale.order"][2] == "READY"


def test_failure_during_reconciliation_keeps_pointer(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows(), fail_model="sale.order.line")
    _orchestrate_to_boundary(engine, run, FakeOdoo(_rows()))
    before_pointer = _pointer(engine)
    before_wm = _watermarks(engine)

    with pytest.raises(RefreshContinuationError) as excinfo:
        _continuation(engine).complete(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    assert excinfo.value.requires_new_retry is True
    assert _pointer(engine) == before_pointer
    assert _watermarks(engine) == before_wm
    assert _run_row(engine, run)["status"] in {"RECONCILING", "FAILED_TRANSIENT", "INTERRUPTED"}


def test_failure_during_publication_keeps_pointer_and_watermarks(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows())
    _orchestrate_to_boundary(engine, run, fake)
    before_pointer = _pointer(engine)
    before_wm = _watermarks(engine)

    bad_path = ROOT / "tests" / "no_such_derived_bundle.sql"
    with pytest.raises(RefreshContinuationError) as excinfo:
        _continuation(engine, sql_paths=(bad_path,)).complete(
            run_id=run, company_id=3, odoo_client=fake, now=STAMP,
        )
    assert excinfo.value.requires_new_retry is True
    assert _pointer(engine) == before_pointer
    assert _watermarks(engine) == before_wm
    status = _run_row(engine, run)["status"]
    assert status in {"FAILED_TRANSIENT", "FAILED_PERMANENT", "INTERRUPTED", "PUBLISHING"}


def test_idempotent_completion_reuse(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows())
    _orchestrate_to_boundary(engine, run, fake)
    first = _continuation(engine).complete(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    assert first["current_state"] == "SUCCEEDED"
    second = _continuation(engine).complete(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    assert second["current_state"] == "SUCCEEDED"
    assert _pointer(engine) == run


def test_watermark_advance_binds_to_published_run(engine):
    run = _create_run(engine, ["commercial"])
    _seed_watermarks(engine, COMMERCIAL_MODELS)
    fake = FakeOdoo(_rows())
    _orchestrate_to_boundary(engine, run, fake)
    _continuation(engine).complete(run_id=run, company_id=3, odoo_client=fake, now=STAMP)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT model, published_run_id::text, last_successful_write_date::text, last_successful_id
            FROM ct_control_tower_watermark WHERE company_id=3 ORDER BY model
        """)).mappings().all()
    for row in rows:
        assert row["published_run_id"] == run
        assert row["last_successful_write_date"] is not None
        assert row["last_successful_id"] is not None
