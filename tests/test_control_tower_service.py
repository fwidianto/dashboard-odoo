from uuid import UUID

from src.control_tower.service import json_safe


def test_json_safe_serializes_uuid() -> None:
    value = UUID("4ded6955-8ce5-4518-a1aa-64acc8e4e1f0")

    assert json_safe(value) == "4ded6955-8ce5-4518-a1aa-64acc8e4e1f0"


def test_json_safe_serializes_nested_uuid() -> None:
    value = {"latest_run": {"run_id": UUID("4ded6955-8ce5-4518-a1aa-64acc8e4e1f0")}}

    assert json_safe(value) == {
        "latest_run": {"run_id": "4ded6955-8ce5-4518-a1aa-64acc8e4e1f0"}
    }
