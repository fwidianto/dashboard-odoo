from src.api import _build_internal_order_dashboard_summary


def test_internal_order_dashboard_summary_excludes_cancelled_records():
    rows = [
        {
            "traceability_status": "HAS_ACCOUNTING_LINK",
            "linked_mo_count": 2,
            "linked_so_count": 1,
            "has_delivered_so": True,
            "has_invoiced_so": True,
            "total_so_ordered_qty": 10,
            "total_so_delivered_qty": 8,
            "total_so_invoiced_qty": 6,
            "total_po_ordered_qty": 5,
            "total_po_received_qty": 4,
            "total_po_invoiced_qty": 3,
        },
        {
            "traceability_status": "CANCELLED_RECORD",
            "linked_mo_count": 1,
            "linked_so_count": 1,
            "has_delivered_so": True,
            "has_invoiced_so": True,
            "total_so_ordered_qty": 100,
            "total_so_delivered_qty": 100,
            "total_so_invoiced_qty": 100,
            "total_po_ordered_qty": 100,
            "total_po_received_qty": 100,
            "total_po_invoiced_qty": 100,
        },
    ]

    summary = _build_internal_order_dashboard_summary(rows)

    assert summary["active_internal_orders"] == 1
    assert summary["internal_orders_with_mo"] == 1
    assert summary["internal_orders_with_so"] == 1
    assert summary["internal_orders_delivered"] == 1
    assert summary["internal_orders_invoiced"] == 1
    assert summary["delivery_progress_ratio"] == 0.8
    assert summary["invoice_progress_ratio"] == 0.6
    assert summary["procurement_receipt_progress_ratio"] == 0.8
    assert summary["procurement_billing_progress_ratio"] == 0.6


def test_internal_order_dashboard_summary_handles_zero_denominators():
    rows = [
        {
            "traceability_status": "HAS_MO_NO_SO_YET",
            "linked_mo_count": 1,
            "linked_so_count": 0,
            "has_delivered_so": False,
            "has_invoiced_so": False,
            "total_so_ordered_qty": 0,
            "total_so_delivered_qty": 0,
            "total_so_invoiced_qty": 0,
            "total_po_ordered_qty": 0,
            "total_po_received_qty": 0,
            "total_po_invoiced_qty": 0,
        }
    ]

    summary = _build_internal_order_dashboard_summary(rows)

    assert summary["active_internal_orders"] == 1
    assert summary["delivery_progress_ratio"] is None
    assert summary["invoice_progress_ratio"] is None
    assert summary["procurement_receipt_progress_ratio"] is None
    assert summary["procurement_billing_progress_ratio"] is None
