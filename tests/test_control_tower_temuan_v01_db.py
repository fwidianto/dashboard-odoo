"""PostgreSQL lifecycle proof for the bounded DH2-SALES-001 Temuan rule."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import md5
import json
import os
from pathlib import Path
import time
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.clients.postgres_client import PostgresClient
from src.control_tower.service import ControlTowerService

ROOT = Path(__file__).parents[1]
PROJECTION_SQL = (ROOT / "sql/13_control_tower_temuan_v01.sql").read_text(encoding="utf-8")
TEST_DATABASE_ENV = "CT_TEST_POSTGRES_URL"
SCHEMA = "ct_temuan_v01_test"
COMPANY_3, COMPANY_4 = 3, 4
SO_3, SO_4 = 930001, 940001
RUN_IDS = [str(uuid4()) for _ in range(4)]
RUN_3, RUN_4_INITIAL, RUN_4_LATEST, RUN_3_RETURN = RUN_IDS
FINDING_3 = md5(f"DH2-SALES-001|sale.order|{SO_3}|{COMPANY_3}".encode()).hexdigest()
FINDING_4 = md5(f"DH2-SALES-001|sale.order|{SO_4}|{COMPANY_4}".encode()).hexdigest()

SCHEMA_SQL = """
CREATE TABLE ct_extraction_run (
    run_id UUID PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ, status TEXT NOT NULL, company_id BIGINT,
    model_counts JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE ct_native_record_snapshot (
    extraction_run_id UUID NOT NULL, model TEXT NOT NULL, record_id BIGINT NOT NULL,
    document_number TEXT, state TEXT, company_id BIGINT, payload JSONB NOT NULL,
    PRIMARY KEY (extraction_run_id, model, record_id)
);
CREATE TABLE mv_ct_rule_results (
    rule_id TEXT NOT NULL, document_model TEXT NOT NULL, document_id BIGINT NOT NULL,
    document_number TEXT, actual_condition JSONB NOT NULL,
    validation_status TEXT NOT NULL, detected_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE ct_finding (
    finding_id TEXT PRIMARY KEY,
    category TEXT NOT NULL, rule_code TEXT NOT NULL, affected_model TEXT NOT NULL,
    affected_document_id BIGINT NOT NULL, native_document_reference TEXT,
    company_id BIGINT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL,
    evidence_payload JSONB NOT NULL, first_detected_time TIMESTAMPTZ NOT NULL,
    last_detected_time TIMESTAMPTZ NOT NULL, current_status TEXT NOT NULL,
    destination_url TEXT NOT NULL,
    UNIQUE (rule_code, affected_model, affected_document_id, company_id)
);
CREATE VIEW vw_ct_current_run AS
SELECT run_id, started_at, completed_at, company_id, model_counts
FROM ct_extraction_run
WHERE status = 'COMPLETED'
ORDER BY completed_at DESC, started_at DESC
LIMIT 1;
CREATE VIEW vw_ct_native_record_snapshot_current AS
SELECT snapshot.*
FROM ct_native_record_snapshot snapshot
JOIN vw_ct_current_run current_run ON current_run.run_id = snapshot.extraction_run_id;
"""


@contextmanager
def _tx(engine):
    with engine.begin() as conn:
        conn.execute(text(f"SET LOCAL search_path TO {SCHEMA}, public"))
        yield conn


def _now(offset=0):
    return datetime.now(timezone.utc) + timedelta(seconds=offset)


def _payload(client_ref=None, po_date=None):
    return json.dumps({"date_order": "2026-01-15 09:00:00", "client_order_ref": client_ref, "x_studio_tanggal_po_cust": po_date})


def _insert_run(conn, run_id, company_id, completed_at):
    conn.execute(text("""
        INSERT INTO ct_extraction_run
            (run_id, started_at, completed_at, status, company_id, model_counts)
        VALUES (CAST(:run_id AS UUID), :started_at, :completed_at, 'COMPLETED',
                :company_id, CAST(:model_counts AS JSONB))
    """), {"run_id": run_id, "started_at": completed_at - timedelta(minutes=1), "completed_at": completed_at, "company_id": company_id, "model_counts": json.dumps({"sale.order": 1})})


def _insert_so(conn, run_id, company_id, record_id, reference, client_ref=None, po_date=None):
    conn.execute(text("""
        INSERT INTO ct_native_record_snapshot
            (extraction_run_id, model, record_id, document_number, state, company_id, payload)
        VALUES (CAST(:run_id AS UUID), 'sale.order', :record_id, :reference, 'sale',
                :company_id, CAST(:payload AS JSONB))
    """), {"run_id": run_id, "record_id": record_id, "reference": reference, "company_id": company_id, "payload": _payload(client_ref, po_date)})


def _update_so(conn, run_id, record_id, client_ref=None, po_date=None):
    conn.execute(text("""
        UPDATE ct_native_record_snapshot
        SET payload = CAST(:payload AS JSONB)
        WHERE extraction_run_id = CAST(:run_id AS UUID)
          AND model = 'sale.order' AND record_id = :record_id
    """), {"run_id": run_id, "record_id": record_id, "payload": _payload(client_ref, po_date)})


def _source_rule(engine, run_id, record_id):
    with _tx(engine) as conn:
        row = conn.execute(text("""
            SELECT document_number, state, payload
            FROM ct_native_record_snapshot
            WHERE extraction_run_id = CAST(:run_id AS UUID)
              AND model = 'sale.order' AND record_id = :record_id
        """), {"run_id": run_id, "record_id": record_id}).mappings().one()
        payload = row["payload"]
        missing = [
            name for name, key in (("Customer Reference", "client_order_ref"), ("Customer PO Date", "x_studio_tanggal_po_cust"))
            if not str(payload.get(key) or "").strip()
        ]
        conn.execute(text("DELETE FROM mv_ct_rule_results WHERE rule_id = 'SO-PO-001' AND document_id = :record_id"), {"record_id": record_id})
        conn.execute(text("""
            INSERT INTO mv_ct_rule_results
                (rule_id, document_model, document_id, document_number, actual_condition, validation_status, detected_at)
            VALUES ('SO-PO-001', 'sale.order', :record_id, :document_number,
                    CAST(:actual_condition AS JSONB), :validation_status, clock_timestamp())
        """), {"record_id": record_id, "document_number": row["document_number"], "actual_condition": json.dumps({"client_order_ref": payload.get("client_order_ref"), "customer_po_date": payload.get("x_studio_tanggal_po_cust"), "state": row["state"]}), "validation_status": "MISMATCH" if missing else "VALIDATED"})


def _projection(engine):
    with _tx(engine) as conn:
        conn.exec_driver_sql(PROJECTION_SQL)


def _finding(engine, finding_id):
    with _tx(engine) as conn:
        row = conn.execute(text("SELECT * FROM ct_finding WHERE finding_id = :finding_id"), {"finding_id": finding_id}).mappings().first()
        return dict(row) if row else None


def _service(engine, url):
    api_engine = create_engine(url, connect_args={"options": f"-csearch_path={SCHEMA},public"})
    client = PostgresClient(connection_url=url)
    client._engine = api_engine
    return ControlTowerService(client)


@pytest.fixture
def test_postgres_engine():
    url = os.getenv(TEST_DATABASE_ENV)
    if not url:
        pytest.skip(f"Set {TEST_DATABASE_ENV} to an explicit development/test PostgreSQL URL.")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
            conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
            conn.execute(text(f"SET LOCAL search_path TO {SCHEMA}, public"))
            conn.exec_driver_sql(SCHEMA_SQL)
    except (SQLAlchemyError, OSError) as exc:
        engine.dispose()
        pytest.skip(f"Development/test PostgreSQL unavailable ({type(exc).__name__}).")
    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        engine.dispose()


def test_temuan_postgres_lifecycle_and_company_isolation(test_postgres_engine):
    engine = test_postgres_engine
    url = os.environ[TEST_DATABASE_ENV]
    with _tx(engine) as conn:
        _insert_run(conn, RUN_3, COMPANY_3, _now(20))
        _insert_so(conn, RUN_3, COMPANY_3, SO_3, "SO-TEST-3-001")
        _insert_run(conn, RUN_4_INITIAL, COMPANY_4, _now(-20))
        _insert_so(conn, RUN_4_INITIAL, COMPANY_4, SO_4, "SO-TEST-4-001")
    _source_rule(engine, RUN_3, SO_3)
    _source_rule(engine, RUN_4_INITIAL, SO_4)
    _projection(engine)

    first = _finding(engine, FINDING_3)
    assert first and first["finding_id"] == FINDING_3
    assert first["rule_code"] == "DH2-SALES-001" and first["category"] == "DATA_BELUM_LENGKAP"
    assert first["affected_model"] == "sale.order" and first["affected_document_id"] == SO_3
    assert first["native_document_reference"] == "SO-TEST-3-001" and first["company_id"] == COMPANY_3
    assert first["summary"] == "Lengkapi Customer Reference dan Customer PO Date pada SO SO-TEST-3-001."
    assert first["destination_url"] == f"/dashboard/sales-orders?sales_order_id={SO_3}"
    assert first["evidence_payload"]["source_check"] == "SO-PO-001"
    assert set(first["evidence_payload"]["missing_fields"]) == {"Customer Reference", "Customer PO Date"}
    assert first["evidence_payload"]["state"] == "sale" and first["evidence_payload"]["date_order"] == "2026-01-15 09:00:00"
    assert first["first_detected_time"] == first["last_detected_time"] and first["current_status"] == "OPEN"
    assert _finding(engine, FINDING_4) is None
    first_detected = first["first_detected_time"]

    time.sleep(0.02)
    _source_rule(engine, RUN_3, SO_3)
    _projection(engine)
    repeated = _finding(engine, FINDING_3)
    assert repeated["finding_id"] == first["finding_id"] and repeated["first_detected_time"] == first_detected
    assert repeated["last_detected_time"] > first_detected and repeated["current_status"] == "OPEN"

    with _tx(engine) as conn:
        _update_so(conn, RUN_3, SO_3, "CUST-REF-3", "2026-01-20")
    _source_rule(engine, RUN_3, SO_3)
    _projection(engine)
    resolved = _finding(engine, FINDING_3)
    assert resolved["finding_id"] == FINDING_3 and resolved["current_status"] == "RESOLVED"
    assert resolved["first_detected_time"] == first_detected
    service = _service(engine, url)
    try:
        ids = {row["finding_id"] for row in service.findings()["rows"]}
        assert FINDING_3 not in ids and FINDING_4 not in ids
    finally:
        service.close()

    with _tx(engine) as conn:
        _update_so(conn, RUN_3, SO_3)
    time.sleep(0.02)
    _source_rule(engine, RUN_3, SO_3)
    _projection(engine)
    recurring = _finding(engine, FINDING_3)
    assert recurring["finding_id"] == FINDING_3 and recurring["current_status"] == "OPEN"
    assert recurring["first_detected_time"] == first_detected and recurring["last_detected_time"] > repeated["last_detected_time"]
    before_company_4 = dict(recurring)

    with _tx(engine) as conn:
        _insert_run(conn, RUN_4_LATEST, COMPANY_4, _now(30))
        _insert_so(conn, RUN_4_LATEST, COMPANY_4, SO_4, "SO-TEST-4-001")
    _source_rule(engine, RUN_4_LATEST, SO_4)
    _projection(engine)
    company_4_finding = _finding(engine, FINDING_4)
    assert company_4_finding and company_4_finding["company_id"] == COMPANY_4
    after_company_4 = _finding(engine, FINDING_3)
    assert after_company_4["current_status"] == before_company_4["current_status"]
    assert after_company_4["first_detected_time"] == before_company_4["first_detected_time"]
    assert after_company_4["last_detected_time"] == before_company_4["last_detected_time"]
    service = _service(engine, url)
    try:
        ids = {row["finding_id"] for row in service.findings()["rows"]}
        assert FINDING_4 in ids and FINDING_3 not in ids
        assert all(row["company_id"] == COMPANY_4 for row in service.findings()["rows"])
    finally:
        service.close()

    with _tx(engine) as conn:
        _insert_run(conn, RUN_3_RETURN, COMPANY_3, _now(40))
        _insert_so(conn, RUN_3_RETURN, COMPANY_3, SO_3, "SO-TEST-3-001")
    _source_rule(engine, RUN_3_RETURN, SO_3)
    _projection(engine)
    service = _service(engine, url)
    try:
        ids = {row["finding_id"] for row in service.findings()["rows"]}
        assert FINDING_3 in ids and FINDING_4 not in ids
        assert all(row["company_id"] == COMPANY_3 for row in service.findings()["rows"])
    finally:
        service.close()
