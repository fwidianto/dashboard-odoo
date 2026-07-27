import sys
import types
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Local isolated test fallback. In the real repository these modules exist.
try:
    import src.clients.odoo_client  # noqa: F401
except ModuleNotFoundError:
    clients_package = types.ModuleType("src.clients")
    odoo_module = types.ModuleType("src.clients.odoo_client")
    postgres_module = types.ModuleType("src.clients.postgres_client")
    logging_module = types.ModuleType("src.utils.logging")
    utils_package = types.ModuleType("src.utils")

    class OdooClient:  # pragma: no cover - import-only fallback
        pass

    class PostgresClient:  # pragma: no cover - import-only fallback
        pass

    odoo_module.OdooClient = OdooClient
    postgres_module.PostgresClient = PostgresClient
    logging_module.get_logger = lambda _name: None
    sys.modules.setdefault("src.clients", clients_package)
    sys.modules["src.clients.odoo_client"] = odoo_module
    sys.modules["src.clients.postgres_client"] = postgres_module
    sys.modules.setdefault("src.utils", utils_package)
    sys.modules["src.utils.logging"] = logging_module

from src.control_tower.relation_extractor import (
    CREATE_SCHEMA_SQL,
    ControlTowerRelationExtractor,
    IncrementalRefreshError,
    INSERT_LINK_SQL,
    MODEL_SPECS,
    UPSERT_STAGED_SNAPSHOT_SQL,
    normalize_value,
)
from src.clients.odoo_client import ALLOWED_METHODS, FORBIDDEN_METHODS


def test_normalize_many2one_preserves_native_id_and_name():
    result = normalize_value([42, "SO00042"], {"type": "many2one"})
    assert result == {"id": 42, "name": "SO00042"}


def test_normalize_many2many_preserves_native_ids():
    result = normalize_value([1081, 1361], {"type": "many2many"})
    assert result == [1081, 1361]


def test_so_to_io_direction_is_sales_order_parent():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    snapshots = [
        {"model": "sale.order", "record_id": 10, "document_number": "SO0010", "payload": {"x_studio_io_1": [1081, 1361]}},
        {"model": "approval.request", "record_id": 1081, "document_number": "IO1081", "payload": {}},
        {"model": "approval.request", "record_id": 1361, "document_number": "IO1361", "payload": {}},
    ]
    index = extractor._index_snapshots(snapshots)
    rows = [row for row in extractor._iter_direct_links(snapshots, index) if row["link_type"] == "SO_TO_IO"]

    assert {(row["parent_model"], row["parent_id"], row["child_model"], row["child_id"]) for row in rows} == {
        ("sale.order", 10, "approval.request", 1081),
        ("sale.order", 10, "approval.request", 1361),
    }
    assert all(row["confidence"] == "HIGH" for row in rows)


def test_exact_text_origin_link_is_secondary_medium_confidence():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    snapshots = [
        {"model": "sale.order", "record_id": 20, "document_number": "SO0020", "payload": {}},
        {"model": "mrp.production", "record_id": 30, "document_number": "MO0030", "payload": {"origin": "SO0020"}},
    ]
    name_index = extractor._name_index(snapshots)
    rows = list(extractor._iter_inferred_links(snapshots, name_index))

    assert len(rows) == 1
    assert rows[0]["link_type"] == "SO_TO_MO_ORIGIN"
    assert rows[0]["confidence"] == "MEDIUM"
    assert rows[0]["evidence"]["requires_human_review"] is True


def test_po_to_receipt_is_derived_from_native_move_relations():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    snapshots = [
        {"model": "purchase.order", "record_id": 1, "document_number": "PO001", "payload": {}},
        {"model": "purchase.order.line", "record_id": 2, "document_number": None, "payload": {"order_id": {"id": 1, "name": "PO001"}}},
        {"model": "stock.picking", "record_id": 3, "document_number": "WH/IN/003", "payload": {}},
        {"model": "stock.move", "record_id": 4, "document_number": None, "payload": {"purchase_line_id": {"id": 2, "name": "Line"}, "picking_id": {"id": 3, "name": "WH/IN/003"}}},
    ]
    index = extractor._index_snapshots(snapshots)
    rows = list(extractor._iter_derived_links(snapshots, index))

    assert len(rows) == 1
    assert rows[0]["link_type"] == "PO_TO_RECEIPT"
    assert rows[0]["parent_id"] == 1
    assert rows[0]["child_id"] == 3
    assert rows[0]["confidence"] == "HIGH"


def test_incremental_purchase_order_payload_keeps_business_date_order():
    purchase_order = next(spec for spec in MODEL_SPECS if spec.model == "purchase.order")

    assert "date_order" in purchase_order.fields
    assert "write_date" in purchase_order.fields


def test_incremental_upsert_is_duplicate_safe():
    sql = str(UPSERT_STAGED_SNAPSHOT_SQL)

    assert "ON CONFLICT (extraction_run_id, model, record_id) DO UPDATE" in sql
    assert "IS DISTINCT FROM" in sql
    assert "RETURNING record_id" in sql


def test_link_owner_is_normalized_for_indexed_selective_refresh():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)

    assert extractor._link_owner({
        "evidence": {"field_owner_model": "sale.order", "field_owner_record_id": 41},
        "child_model": "approval.request",
        "child_id": 8,
    }) == ("sale.order", 41)
    assert extractor._link_owner({
        "evidence": {"via_stock_move_id": 51},
        "child_model": "stock.picking",
        "child_id": 9,
    }) == ("stock.move", 51)
    assert extractor._link_owner({
        "evidence": {"relation_kind": "exact_text_reference"},
        "child_model": "mrp.production",
        "child_id": 61,
    }) == ("mrp.production", 61)

    assert "owner_model" in str(INSERT_LINK_SQL)
    assert "owner_record_id" in str(INSERT_LINK_SQL)
    assert "idx_ct_link_run_owner" in CREATE_SCHEMA_SQL
    assert "idx_ct_snapshot_aml_move" in CREATE_SCHEMA_SQL
    assert "idx_ct_snapshot_aml_cogs" in CREATE_SCHEMA_SQL


def test_full_backfill_inserts_document_links_in_existing_batch_size():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    extractor.batch_size = 2
    extractor.pg = MagicMock()
    connection = extractor.pg.engine.begin.return_value.__enter__.return_value
    batch_sizes = []
    connection.execute.side_effect = lambda _statement, parameters: batch_sizes.append(len(parameters))
    links = [
        {
            "link_type": "SO_TO_INVOICE",
            "parent_model": "sale.order",
            "parent_id": number,
            "parent_number": f"SO{number}",
            "child_model": "account.move",
            "child_id": number + 10,
            "child_number": f"INV{number}",
            "source_field": "sale_line_ids",
            "confidence": "HIGH",
            "evidence": {"field_owner_model": "account.move.line", "field_owner_record_id": number},
        }
        for number in range(3)
    ]

    assert extractor._insert_links(links, "run", datetime.now(timezone.utc)) == 3
    assert batch_sizes == [2, 1]


def test_incremental_query_uses_write_date_only_as_change_watermark():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    extractor.company_id = 3
    extractor.progress_callback = None
    extractor.batch_size = 10
    extractor.odoo = MagicMock()
    extractor.odoo.get_model_fields.return_value = {
        "id": {"type": "integer"},
        "name": {"type": "char"},
        "state": {"type": "selection"},
        "date_order": {"type": "datetime"},
        "company_id": {"type": "many2one"},
        "write_date": {"type": "datetime"},
    }
    extractor.odoo.read_batched.return_value = []
    extractor.pg = MagicMock()
    spec = next(spec for spec in MODEL_SPECS if spec.model == "purchase.order")
    watermark = datetime(2026, 7, 1, tzinfo=timezone.utc)

    assert extractor._extract_model_incremental(spec, "run", watermark, watermark) == []
    domain = extractor.odoo.read_batched.call_args.args[1]
    assert ("write_date", ">=", "2026-07-01 00:00:00") in domain
    assert not any(item[0] == "date_order" for item in domain)


def test_failed_incremental_run_is_marked_failed_without_publication():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    extractor.company_id = 3
    extractor.progress_callback = None
    extractor._current_completed_run = MagicMock(
        return_value={
            "run_id": "00000000-0000-0000-0000-000000000001",
            "source_watermark": datetime(2026, 7, 1, tzinfo=timezone.utc),
        }
    )
    extractor._verify_source_compatibility = MagicMock(return_value=("f" * 64, "stored_fingerprint"))
    extractor._start_incremental_run = MagicMock()
    extractor._extract_model_incremental = MagicMock(side_effect=RuntimeError("source unavailable"))
    extractor._mark_incremental_failed = MagicMock()
    extractor._publish_incremental_run = MagicMock()
    extractor.logger = MagicMock()

    try:
        extractor._run_incremental_locked()
    except IncrementalRefreshError:
        pass
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("Incremental refresh failure must be surfaced")

    extractor._mark_incremental_failed.assert_called_once()
    extractor._publish_incremental_run.assert_not_called()


def test_unchanged_incremental_refresh_is_idempotent_and_advances_only_on_publish():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    extractor.company_id = 3
    extractor.progress_callback = None
    extractor._current_completed_run = MagicMock(
        return_value={
            "run_id": "00000000-0000-0000-0000-000000000001",
            "source_watermark": datetime(2026, 7, 1, tzinfo=timezone.utc),
        }
    )
    extractor._verify_source_compatibility = MagicMock(
        return_value=("f" * 64, "stored_fingerprint")
    )
    extractor._start_incremental_run = MagicMock()
    extractor._extract_model_incremental = MagicMock(return_value=[])
    extractor._copy_links = MagicMock(return_value=100)
    extractor._refresh_links_selective = MagicMock()
    extractor._model_counts_for_run = MagicMock(return_value={"sale.order": 10})
    published_at = datetime(2026, 7, 2, tzinfo=timezone.utc)
    extractor._publish_incremental_run = MagicMock(return_value=published_at)
    extractor._mark_incremental_failed = MagicMock()
    extractor.logger = MagicMock()

    result = extractor._run_incremental_locked()

    assert result["outcome"] == "NO_CHANGES"
    assert result["changed_documents"] == 0
    assert result["recalculated_rule_ids"] == []
    extractor._copy_links.assert_called_once()
    extractor._refresh_links_selective.assert_not_called()
    publish_args = extractor._publish_incremental_run.call_args.kwargs
    assert publish_args["changed_models"] == {}
    assert publish_args["recalculated_rules"] == []
    extractor._mark_incremental_failed.assert_not_called()


def test_stored_source_fingerprint_blocks_cross_instance_refresh():
    extractor = ControlTowerRelationExtractor.__new__(ControlTowerRelationExtractor)
    extractor.odoo = MagicMock(url="https://sandbox.dev.odoo.com", db="sandbox")

    try:
        extractor._verify_source_compatibility(
            {"run_id": "00000000-0000-0000-0000-000000000001", "source_fingerprint": "0" * 64}
        )
    except IncrementalRefreshError as exc:
        assert "tidak sama" in str(exc)
    else:  # pragma: no cover - assertion clarity
        raise AssertionError("A different Odoo source must be blocked")

    assert len(extractor._source_fingerprint()) == 64
    assert "sandbox" not in extractor._source_fingerprint()


def test_odoo_connector_allowlist_cannot_write():
    assert ALLOWED_METHODS == {"search", "read", "search_read", "search_count", "fields_get"}
    assert {"create", "write", "unlink", "action_archive"}.issubset(FORBIDDEN_METHODS)
    assert ALLOWED_METHODS.isdisjoint(FORBIDDEN_METHODS)
