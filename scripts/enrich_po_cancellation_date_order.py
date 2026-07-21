#!/usr/bin/env python3
"""Read-only date-order enrichment for the current PO cancellation snapshot.

This is deliberately narrower than a Control Tower extraction: it reads only
the cancelled Purchase Order IDs already evaluated by ``PO-CANCEL-001`` and
publishes their date scope into a separate PostgreSQL analytical table.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path
import sys
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4
import xmlrpc.client

from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.clients.postgres_client import PostgresClient


COMPANY_ID = 3
RULE_ID = "PO-CANCEL-001"
DATE_START = date(2026, 1, 1)
BATCH_SIZE = 250
REQUIRED_ENV_KEYS = ("ODOO_URL", "ODOO_DB", "ODOO_USERNAME", "ODOO_API_KEY")
READ_ONLY_METHODS = frozenset({"fields_get", "search", "read", "search_read", "search_count"})
PO_FIELDS = ("id", "state", "company_id", "date_order", "write_date")


class EnrichmentError(RuntimeError):
    """Expected, sanitized failure for the enrichment workflow."""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ct_purchase_order_date_enrichment_execution (
    execution_id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    company_id BIGINT NOT NULL,
    expected_count BIGINT NOT NULL,
    returned_count BIGINT,
    null_date_order_count BIGINT,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    failure_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_ct_po_date_enrichment_execution_run
    ON ct_purchase_order_date_enrichment_execution (run_id, status, completed_at DESC);

CREATE TABLE IF NOT EXISTS ct_purchase_order_date_enrichment (
    run_id UUID NOT NULL,
    purchase_order_id BIGINT NOT NULL,
    company_id BIGINT NOT NULL,
    source_state TEXT NOT NULL,
    date_order TIMESTAMP WITHOUT TIME ZONE,
    source_write_date TIMESTAMP WITHOUT TIME ZONE,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    enrichment_status TEXT NOT NULL CHECK (enrichment_status = 'COMPLETED'),
    enrichment_execution_id UUID NOT NULL
        REFERENCES ct_purchase_order_date_enrichment_execution (execution_id),
    PRIMARY KEY (run_id, purchase_order_id)
);

CREATE INDEX IF NOT EXISTS idx_ct_po_date_enrichment_scope
    ON ct_purchase_order_date_enrichment (run_id, date_order, purchase_order_id);
"""


def stage(name: str) -> None:
    print(f"[START] {name}", flush=True)


def done(name: str, started: float) -> None:
    print(f"[DONE ] {name} ({perf_counter() - started:.2f}s)", flush=True)


def load_sandbox_env() -> dict[str, str]:
    """Load only the repository-root sandbox credentials without logging them."""
    env_path = PROJECT_ROOT / ".env.sandbox"
    if not env_path.is_file():
        raise EnrichmentError("config: .env.sandbox tidak ditemukan")

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in REQUIRED_ENV_KEYS:
            values[key] = value.strip().strip('"').strip("'")

    missing = [key for key in REQUIRED_ENV_KEYS if not values.get(key)]
    if missing:
        raise EnrichmentError("config: key sandbox wajib tidak lengkap")
    return values


def validate_target_url(raw_url: str) -> str:
    """Accept only a sandbox Odoo root URL and never echo it back."""
    parsed = urlsplit(raw_url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise EnrichmentError("config: ODOO_URL bukan HTTP(S) yang valid")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise EnrichmentError("config: ODOO_URL harus berupa root URL")
    if not host.endswith(".dev.odoo.com") or host.split(".")[0] in {
        "prod",
        "production",
        "live",
        "main",
    }:
        raise EnrichmentError("safety: target bukan sandbox .dev.odoo.com")
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


class ReadOnlyOdooRpc:
    """Small XML-RPC wrapper that physically rejects non-read model methods."""

    def __init__(self, root_url: str, db: str, username: str, api_key: str) -> None:
        self.db = db
        self.username = username
        self.api_key = api_key
        self.common = xmlrpc.client.ServerProxy(
            f"{root_url}/xmlrpc/2/common", allow_none=True, use_builtin_types=True
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{root_url}/xmlrpc/2/object", allow_none=True, use_builtin_types=True
        )
        self.uid: int | None = None

    def version(self) -> dict[str, Any]:
        try:
            value = self.common.version()
        except (OSError, xmlrpc.client.Error) as exc:
            raise EnrichmentError("odoo: version tidak dapat dibaca") from exc
        if not isinstance(value, dict):
            raise EnrichmentError("odoo: respons version tidak valid")
        return value

    def authenticate(self) -> int:
        try:
            uid = self.common.authenticate(self.db, self.username, self.api_key, {})
        except (OSError, xmlrpc.client.Error) as exc:
            raise EnrichmentError("odoo: autentikasi read-only gagal") from exc
        if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
            raise EnrichmentError("odoo: autentikasi read-only ditolak")
        self.uid = uid
        return uid

    def read(
        self,
        model: str,
        method: str,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        if method not in READ_ONLY_METHODS:
            raise EnrichmentError("safety: method non-read diblokir")
        if self.uid is None:
            raise EnrichmentError("safety: RPC belum diautentikasi")
        try:
            return self.models.execute_kw(
                self.db,
                self.uid,
                self.api_key,
                model,
                method,
                args,
                kwargs or {},
            )
        except (OSError, xmlrpc.client.Error) as exc:
            raise EnrichmentError("odoo: operasi baca gagal") from exc


def relation_id(value: Any) -> int | None:
    if isinstance(value, (list, tuple)) and value:
        value = value[0]
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def parse_odoo_datetime(value: Any) -> datetime | None:
    """Preserve Odoo's local datetime representation; never derive scope from write_date."""
    if value in (None, False, ""):
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EnrichmentError("odoo: format datetime tidak valid") from exc
        return parsed.replace(tzinfo=None)
    raise EnrichmentError("odoo: tipe datetime tidak valid")


def scope_for_date(value: datetime | None) -> str:
    if value is None:
        return "DATE_SCOPE_UNKNOWN"
    return "ACTIVE_2026_PLUS" if value.date() >= DATE_START else "HISTORICAL_PRE_2026"


def ensure_schema(pg: PostgresClient) -> None:
    with pg.engine.begin() as conn:
        conn.execute(text(SCHEMA_SQL))


def load_expected_purchase_orders(pg: PostgresClient) -> tuple[str, list[int]]:
    with pg.engine.connect() as conn:
        current = conn.execute(
            text("SELECT run_id::text AS run_id, company_id FROM vw_ct_current_run")
        ).mappings().one_or_none()
        if current is None or int(current["company_id"]) != COMPANY_ID:
            raise EnrichmentError("snapshot: run COMPLETED company 3 tidak tersedia")
        rows = conn.execute(
            text(
                """
                SELECT document_id
                FROM mv_ct_rule_results
                WHERE rule_id = :rule_id
                  AND document_model = 'purchase.order'
                ORDER BY document_id
                """
            ),
            {"rule_id": RULE_ID},
        ).scalars().all()

    purchase_order_ids = [int(value) for value in rows]
    if not purchase_order_ids:
        raise EnrichmentError("snapshot: tidak ada PO-CANCEL-001 untuk dienrich")
    if len(purchase_order_ids) != len(set(purchase_order_ids)):
        raise EnrichmentError("snapshot: grain PO-CANCEL-001 bukan PO root unik")
    return str(current["run_id"]), purchase_order_ids


def create_execution(pg: PostgresClient, run_id: str, expected_count: int) -> str:
    execution_id = str(uuid4())
    with pg.engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ct_purchase_order_date_enrichment_execution (
                    execution_id, run_id, company_id, expected_count, status
                ) VALUES (
                    :execution_id, :run_id, :company_id, :expected_count, 'RUNNING'
                )
                """
            ),
            {
                "execution_id": execution_id,
                "run_id": run_id,
                "company_id": COMPANY_ID,
                "expected_count": expected_count,
            },
        )
    return execution_id


def mark_failed(pg: PostgresClient, execution_id: str, reason: str) -> None:
    with pg.engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE ct_purchase_order_date_enrichment_execution
                SET status = 'FAILED', completed_at = NOW(), failure_reason = :reason
                WHERE execution_id = :execution_id
                  AND status = 'RUNNING'
                """
            ),
            {"execution_id": execution_id, "reason": reason[:120]},
        )


def verify_target(rpc: ReadOnlyOdooRpc) -> None:
    version = rpc.version()
    if not str(version.get("server_version", "")).startswith("18.0"):
        raise EnrichmentError("odoo: versi target bukan Odoo 18.0")
    uid = rpc.authenticate()
    user_rows = rpc.read("res.users", "read", [[uid]], {"fields": ["company_id"]})
    if not isinstance(user_rows, list) or len(user_rows) != 1:
        raise EnrichmentError("odoo: scope company user tidak dapat diverifikasi")
    if relation_id(user_rows[0].get("company_id")) != COMPANY_ID:
        raise EnrichmentError("odoo: company aktif bukan company_id 3")
    metadata = rpc.read(
        "purchase.order",
        "fields_get",
        [["state", "company_id", "date_order", "write_date"]],
        {"attributes": ["type"]},
    )
    if not isinstance(metadata, dict) or any(
        field not in metadata for field in ("state", "company_id", "date_order", "write_date")
    ):
        raise EnrichmentError("odoo: field Purchase Order wajib tidak tersedia")


def fetch_purchase_orders(
    rpc: ReadOnlyOdooRpc,
    purchase_order_ids: list[int],
) -> list[dict[str, Any]]:
    expected_ids = set(purchase_order_ids)
    received: dict[int, dict[str, Any]] = {}
    total_batches = (len(purchase_order_ids) + BATCH_SIZE - 1) // BATCH_SIZE

    for index, offset in enumerate(range(0, len(purchase_order_ids), BATCH_SIZE), start=1):
        batch = purchase_order_ids[offset : offset + BATCH_SIZE]
        rows = rpc.read("purchase.order", "read", [batch], {"fields": list(PO_FIELDS)})
        if not isinstance(rows, list):
            raise EnrichmentError("odoo: respons read Purchase Order tidak valid")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), int):
                raise EnrichmentError("odoo: record Purchase Order tidak valid")
            purchase_order_id = int(row["id"])
            if purchase_order_id in received:
                raise EnrichmentError("odoo: ID Purchase Order dikembalikan lebih dari sekali")
            received[purchase_order_id] = row
        print(
            f"[READ ] batch {index}/{total_batches}: diminta {len(batch)}, diterima {len(rows)}",
            flush=True,
        )

    if set(received) != expected_ids:
        raise EnrichmentError("odoo: ID Purchase Order yang dikembalikan tidak lengkap")

    normalized: list[dict[str, Any]] = []
    for purchase_order_id in purchase_order_ids:
        row = received[purchase_order_id]
        company_id = relation_id(row.get("company_id"))
        source_state = str(row.get("state") or "").strip().lower()
        if company_id != COMPANY_ID:
            raise EnrichmentError("odoo: record di luar company_id 3 ditemukan")
        if source_state not in {"cancel", "cancelled"}:
            raise EnrichmentError("odoo: state PO tidak lagi cancelled pada snapshot ini")
        normalized.append(
            {
                "purchase_order_id": purchase_order_id,
                "company_id": company_id,
                "source_state": source_state,
                "date_order": parse_odoo_datetime(row.get("date_order")),
                "source_write_date": parse_odoo_datetime(row.get("write_date")),
            }
        )
    return normalized


def publish(
    pg: PostgresClient,
    *,
    execution_id: str,
    run_id: str,
    records: list[dict[str, Any]],
) -> None:
    null_date_order_count = sum(record["date_order"] is None for record in records)
    rows = [
        {
            **record,
            "run_id": run_id,
            "execution_id": execution_id,
        }
        for record in records
    ]
    with pg.engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM ct_purchase_order_date_enrichment
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO ct_purchase_order_date_enrichment (
                    run_id, purchase_order_id, company_id, source_state,
                    date_order, source_write_date, enrichment_status,
                    enrichment_execution_id
                ) VALUES (
                    :run_id, :purchase_order_id, :company_id, :source_state,
                    :date_order, :source_write_date, 'COMPLETED', :execution_id
                )
                """
            ),
            rows,
        )
        updated = conn.execute(
            text(
                """
                UPDATE ct_purchase_order_date_enrichment_execution
                SET status = 'COMPLETED',
                    returned_count = :returned_count,
                    null_date_order_count = :null_date_order_count,
                    completed_at = NOW(),
                    failure_reason = NULL
                WHERE execution_id = :execution_id
                  AND status = 'RUNNING'
                """
            ),
            {
                "execution_id": execution_id,
                "returned_count": len(records),
                "null_date_order_count": null_date_order_count,
            },
        )
        if updated.rowcount != 1:
            raise EnrichmentError("postgres: execution enrichment tidak dapat dipublikasikan")


def self_check() -> int:
    assert scope_for_date(None) == "DATE_SCOPE_UNKNOWN"
    assert scope_for_date(datetime(2025, 12, 31, 23, 59, 59)) == "HISTORICAL_PRE_2026"
    assert scope_for_date(datetime(2026, 1, 1, 0, 0, 0)) == "ACTIVE_2026_PLUS"
    rpc = ReadOnlyOdooRpc.__new__(ReadOnlyOdooRpc)
    rpc.uid = 1
    try:
        rpc.read("purchase.order", "write", [], {})
    except EnrichmentError:
        pass
    else:
        raise AssertionError("non-read Odoo method was not blocked")
    print("Self-check passed: scope boundary and read-only method guard are enforced.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Targeted read-only date_order enrichment for PO-CANCEL-001."
    )
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        return self_check()

    pg = PostgresClient()
    execution_id: str | None = None
    try:
        started = perf_counter()
        stage("Menyiapkan tabel enrichment analitis")
        ensure_schema(pg)
        done("Menyiapkan tabel enrichment analitis", started)

        started = perf_counter()
        stage("Membaca PO root dari snapshot COMPLETED")
        run_id, purchase_order_ids = load_expected_purchase_orders(pg)
        print(f"[INFO ] PO cancelled unik yang diminta: {len(purchase_order_ids)}", flush=True)
        done("Membaca PO root dari snapshot COMPLETED", started)

        execution_id = create_execution(pg, run_id, len(purchase_order_ids))

        started = perf_counter()
        stage("Memverifikasi target Odoo read-only")
        env = load_sandbox_env()
        rpc = ReadOnlyOdooRpc(
            validate_target_url(env["ODOO_URL"]),
            env["ODOO_DB"],
            env["ODOO_USERNAME"],
            env["ODOO_API_KEY"],
        )
        verify_target(rpc)
        print("[INFO ] Odoo 18.0 dan company_id 3 terverifikasi melalui method read-only.", flush=True)
        done("Memverifikasi target Odoo read-only", started)

        started = perf_counter()
        stage("Membaca date_order Purchase Order dalam batch aman")
        records = fetch_purchase_orders(rpc, purchase_order_ids)
        print(
            "[INFO ] date_order NULL: "
            f"{sum(record['date_order'] is None for record in records)}; "
            "record ini akan menjadi DATE_SCOPE_UNKNOWN.",
            flush=True,
        )
        done("Membaca date_order Purchase Order dalam batch aman", started)

        started = perf_counter()
        stage("Mempublikasikan enrichment secara atomik")
        publish(pg, execution_id=execution_id, run_id=run_id, records=records)
        done("Mempublikasikan enrichment secara atomik", started)
        print(
            "Enrichment selesai: seluruh PO diminta telah dibaca. "
            "Tidak ada full extraction dan tidak ada method Odoo mutating.",
            flush=True,
        )
        return 0
    except EnrichmentError as exc:
        if execution_id is not None:
            mark_failed(pg, execution_id, exc.args[0])
        print(f"[FAIL ] Enrichment tidak dipublikasikan: {exc.args[0]}", flush=True)
        return 1
    except Exception:
        if execution_id is not None:
            mark_failed(pg, execution_id, "UNEXPECTED_ENRICHMENT_FAILURE")
        print("[FAIL ] Enrichment tidak dipublikasikan: kegagalan tak terduga.", flush=True)
        return 1
    finally:
        pg.close()


if __name__ == "__main__":
    raise SystemExit(main())
