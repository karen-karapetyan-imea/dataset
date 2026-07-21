from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from etl.history import (
    activity_code_for_field,
    diff_tracked_fields,
    ensure_activity_type_id,
    serialize_value,
)


def test_serialize_value_decimal_normalizes_scale() -> None:
    assert serialize_value(Decimal("1200")) == "1200.00"
    assert serialize_value(Decimal("1200.00")) == "1200.00"
    assert serialize_value(Decimal("1200.1")) == "1200.10"


def test_diff_tracked_fields_ignores_decimal_scale_differences() -> None:
    old_row = {"price": Decimal("1200"), "currency": "USD"}
    new_row = {"price": Decimal("1200.00"), "currency": "USD"}
    assert diff_tracked_fields(old_row, new_row, ["price", "currency"]) == []


def test_diff_tracked_fields_detects_changes() -> None:
    old_row = {"price": Decimal("1200"), "currency": "USD"}
    new_row = {"price": Decimal("1300"), "currency": "USD"}
    changes = diff_tracked_fields(old_row, new_row, ["price", "currency"])
    assert changes == [("price", "1200.00", "1300.00")]


def test_diff_tracked_fields_none_to_value() -> None:
    old_row = {"availability": None}
    new_row = {"availability": "in_stock"}
    changes = diff_tracked_fields(old_row, new_row, ["availability"])
    assert changes == [("availability", None, "in_stock")]


def test_activity_code_for_field() -> None:
    assert activity_code_for_field("price") == "price_changed"
    assert activity_code_for_field("artwork_cover_url") == "image_changed"
    assert activity_code_for_field("artwork_year") == "artwork_year_changed"


def test_ensure_activity_type_id_returns_existing_id() -> None:
    cursor = MagicMock()
    cursor.fetchone.return_value = (42,)

    activity_id = ensure_activity_type_id(cursor, "price_changed", "Price changed")
    assert activity_id == 42

    # Verify we're using an upsert query shape (create if missing, otherwise reuse).
    execute_args = cursor.execute.call_args[0]
    sql = execute_args[0]
    params = execute_args[1]
    assert "ON CONFLICT" in sql
    assert "DO UPDATE" in sql
    assert params["code"] == "price_changed"

