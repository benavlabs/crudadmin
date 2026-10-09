import datetime
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime as dt
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import DeclarativeBase
from starlette.datastructures import FormData


class PasswordTransformer:
    """
    Configuration for transforming password fields in forms.

    This allows models to have different field names and hashing methods
    for password handling.
    """

    def __init__(
        self,
        password_field: str = "password",
        hashed_field: str = "hashed_password",
        hash_function: Callable[[str], str] | None = None,
        required_fields: list[str] | None = None,
    ):
        """
        Initialize password transformer.

        Args:
            password_field: Name of the password field in the form/schema
            hashed_field: Name of the hashed password field in the internal schema/model
            hash_function: Function to hash passwords (takes string, returns string).
                Required: without it the password would be stored as plaintext.
            required_fields: List of other required fields that must be present

        Raises:
            ValueError: If ``hash_function`` is not provided.
        """
        if hash_function is None:
            raise ValueError(
                "PasswordTransformer requires a hash_function; without one the "
                "password would be stored as plaintext."
            )
        self.password_field = password_field
        self.hashed_field = hashed_field
        self.hash_function: Callable[[str], str] = hash_function
        self.required_fields = required_fields or []

    def transform_create_data(
        self, form_data: dict[str, Any], item_data: BaseModel
    ) -> dict[str, Any]:
        """
        Transform form data for create operations.

        Args:
            form_data: Raw form data dictionary
            item_data: Validated schema instance

        Returns:
            Dictionary with transformed data for internal schema
        """
        transformed_data = {}

        for field_name, field_value in form_data.items():
            if field_name != self.password_field:
                transformed_data[field_name] = field_value

        password = getattr(item_data, self.password_field, None)
        if password is not None:
            transformed_data[self.hashed_field] = self.hash_function(password)

        return transformed_data

    def transform_update_data(
        self, form_data: dict[str, Any], item_data: BaseModel
    ) -> dict[str, Any]:
        """
        Transform form data for update operations.

        Args:
            form_data: Raw form data dictionary
            item_data: Validated schema instance

        Returns:
            Dictionary with transformed data for internal schema
        """
        transformed_data = {"updated_at": dt.now(datetime.timezone.utc)}

        for field_name, field_value in form_data.items():
            if field_name not in (self.password_field, "updated_at"):
                transformed_data[field_name] = field_value

        password = getattr(item_data, self.password_field, None)
        if password is not None:
            transformed_data[self.hashed_field] = self.hash_function(password)  # type: ignore[assignment]

        return transformed_data


@dataclass
class SubmittedForm:
    """What a create or update form sent.

    ``data`` is what gets validated and written. ``field_values`` is what the form
    shows again if the submission is refused.
    """

    data: dict[str, Any] = field(default_factory=dict)
    field_values: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.field_values[key] = value


def checkbox_value(raw_values: list[Any], default: Any) -> bool | None:
    """A checkbox's submitted value, or None to leave the field out.

    One submitted value is read as a boolean: ``"true"`` and ``"false"`` as such,
    anything else by its truthiness. No value means unchecked, so False, unless
    the field has a default, which then applies.
    """
    if raw_values and len(raw_values) == 1:
        value = raw_values[0]
        if value == "true":
            return True
        if value == "false":
            return False
        return bool(value)
    if default is None:
        return False
    return None


def read_create_form(
    form: FormData, form_fields: list[dict[str, Any]]
) -> SubmittedForm:
    """The create form's fields, each falling back to its default when left empty."""
    submitted = SubmittedForm()
    for form_field in form_fields:
        key = form_field["name"]
        raw_values = form.getlist(key)
        if form_field["type"] == "checkbox":
            checked = checkbox_value(raw_values, form_field.get("default"))
            if checked is not None:
                submitted.set(key, checked)
        elif len(raw_values) == 1:
            value = raw_values[0]
            submitted.data[key] = value if value else form_field.get("default")
            submitted.field_values[key] = value
        elif len(raw_values) > 1:
            submitted.set(key, raw_values)
        else:
            submitted.data[key] = form_field.get("default")
    return submitted


def read_update_form(
    form: FormData, form_fields: list[dict[str, Any]], clearable_columns: set[str]
) -> SubmittedForm:
    """The update form's changes.

    Checkboxes are read first. Then every submitted value: files as they are,
    text stripped. Empty text clears a column that may be NULL and is otherwise
    left out, so an untouched field keeps its value.
    """
    submitted = SubmittedForm()
    for form_field in form_fields:
        if form_field["type"] != "checkbox":
            continue
        key = form_field["name"]
        checked = checkbox_value(form.getlist(key), form_field.get("default"))
        if checked is not None:
            submitted.set(key, checked)

    for key, raw_value in form.items():
        if isinstance(raw_value, UploadFile):
            submitted.set(key, raw_value)
        elif isinstance(raw_value, str):
            value = raw_value.strip()
            if value:
                submitted.set(key, value)
            elif key in clearable_columns:
                submitted.set(key, None)
    return submitted


def clearable_column_names(model: type[DeclarativeBase]) -> set[str]:
    """Columns an empty form input sets to NULL: nullable ones that aren't keys.

    Whether a field may be cleared comes from the database column, not the
    update schema, where ``Optional`` usually means "may be left out".
    """
    return {
        column.key
        for column in model.__table__.columns
        if column.nullable and not column.primary_key
    }


def schema_input(schema: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    """``data`` limited to the fields ``schema`` declares.

    The update form adds ``updated_at`` for the internal schema; an update
    schema that forbids extra fields (like ``AdminUserUpdate``) would reject it.
    """
    return {key: value for key, value in data.items() if key in schema.model_fields}


def field_errors(error: ValidationError) -> dict[str, str]:
    """The message for each invalid field, keyed by the field name."""
    return {str(detail["loc"][0]): detail["msg"] for detail in error.errors()}
