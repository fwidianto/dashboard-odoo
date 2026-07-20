import sys
import types

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
    ControlTowerRelationExtractor,
    normalize_value,
)


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
