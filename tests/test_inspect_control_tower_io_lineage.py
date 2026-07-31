from scripts.inspect_control_tower_io_lineage import build_match_matrix, output_filename


def test_build_match_matrix_requires_exact_product_and_uom() -> None:
    io_lines = [
        {
            "approval_line_id": 10,
            "product_id": 100,
            "product_name": "Panel FG",
            "uom_id": 1,
            "uom_name": "Unit",
            "requested_qty": 2,
        }
    ]
    manufacturing_orders = [
        {
            "manufacturing_order_id": 20,
            "manufacturing_order_number": "MO/EXACT",
            "product_id": 100,
            "uom_id": 1,
        },
        {
            "manufacturing_order_id": 21,
            "manufacturing_order_number": "MO/OTHER-UOM",
            "product_id": 100,
            "uom_id": 2,
        },
    ]

    result = build_match_matrix(io_lines, manufacturing_orders)

    assert result["quantity_allocation_performed"] is False
    assert result["matched_io_line_count"] == 1
    assert result["unmatched_io_line_count"] == 0
    assert result["unmatched_manufacturing_order_count"] == 1
    assert result["line_matches"][0]["exact_matches"][0]["manufacturing_order_id"] == 20
    assert result["unmatched_manufacturing_orders"][0]["manufacturing_order_id"] == 21


def test_build_match_matrix_keeps_missing_native_ids_unmatched() -> None:
    io_lines = [
        {
            "approval_line_id": 11,
            "product_id": None,
            "product_name": "Unknown",
            "uom_id": 1,
            "uom_name": "Unit",
            "requested_qty": 1,
        }
    ]
    manufacturing_orders = [
        {
            "manufacturing_order_id": 22,
            "manufacturing_order_number": "MO/UNKNOWN",
            "product_id": None,
            "uom_id": 1,
        }
    ]

    result = build_match_matrix(io_lines, manufacturing_orders)

    assert result["matched_io_line_count"] == 0
    assert result["unmatched_io_line_count"] == 1
    assert result["unmatched_manufacturing_order_count"] == 1


def test_output_filename_is_safe() -> None:
    assert output_filename(" 125IO015 ") == "ct_io_lineage_125IO015.json"
    assert output_filename("125/IO 015") == "ct_io_lineage_125_IO_015.json"
