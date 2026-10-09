"""How a schema field's type picks its form input, and the timestamp schema's output."""

from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum

import pytest
from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, HttpUrl

from crudadmin.admin_interface.helper import (
    _get_form_fields_from_schema,
    _get_html_input_type,
)
from crudadmin.core.schemas import TimestampSchema


class Color(Enum):
    RED = "red"
    BLUE = "blue"


class Address(BaseModel):
    street: str


@pytest.mark.parametrize(
    "python_type, input_type",
    [
        (int, "number"),
        (float, "number"),
        (bool, "checkbox"),
        (EmailStr, "email"),
        (HttpUrl, "url"),
        (AnyHttpUrl, "url"),
        (date, "date"),
        (datetime, "datetime-local"),
        (time, "time"),
        (Address, "json"),
        (str, "text"),
    ],
)
def test_a_python_type_picks_its_input(python_type, input_type):
    assert _get_html_input_type(python_type)[0] == input_type


def test_a_decimal_is_a_number_with_cents():
    assert _get_html_input_type(Decimal) == ("number", {"step": "0.01"})


def test_an_enum_is_a_select_of_its_members():
    assert _get_html_input_type(Color) == (
        "select",
        {
            "options": [
                {"value": "red", "label": "RED"},
                {"value": "blue", "label": "BLUE"},
            ]
        },
    )


def test_a_generic_type_is_a_text_input():
    class Tagged(BaseModel):
        tags: list[str] = []

    [field] = _get_form_fields_from_schema(Tagged)

    assert field["type"] == "text"


def test_a_default_factory_is_called_for_the_form_default():
    class Stamped(BaseModel):
        on: date = Field(default_factory=lambda: date(2026, 1, 1))

    [field] = _get_form_fields_from_schema(Stamped)

    assert field["default"] == date(2026, 1, 1)


def test_timestamps_are_written_as_iso_strings():
    created = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)

    assert TimestampSchema(created_at=created, updated_at=created).model_dump() == {
        "created_at": "2026-10-09T12:00:00+00:00",
        "updated_at": "2026-10-09T12:00:00+00:00",
    }
    assert TimestampSchema(created_at=created).model_dump()["updated_at"] is None
