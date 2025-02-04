from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Type, TypeVar, cast, get_origin

from pydantic import AnyHttpUrl, BaseModel, EmailStr, HttpUrl

T = TypeVar("T")
HTMLInputType = tuple[str, Dict[str, Any]]
FormField = Dict[str, Any]


def _get_html_input_type(py_type: Type[T]) -> HTMLInputType:
    """
    Convert Python/Pydantic type to HTML input type with extra attributes.

    Maps Python types to appropriate HTML form input types and generates
    any additional attributes needed for the input.

    Args:
        py_type: Python type to convert

    Returns:
        Tuple of (html_input_type, extra_attributes) where:
            - html_input_type is string like "text", "number", "datetime-local"
            - extra_attributes is dict of additional HTML attributes

    Special cases:
        - Decimal -> number input with step="0.01"
        - Enum -> select input with options from enum values
        - BaseModel -> json input
        - Unknown types default to text input
    """
    extra: Dict[str, Any] = {}

    if py_type in [int, float]:
        return "number", extra
    elif py_type is bool:
        return "checkbox", extra
    elif py_type == EmailStr:
        return "email", extra
    elif py_type in [HttpUrl, AnyHttpUrl]:
        return "url", extra
    elif py_type == date:
        return "date", extra
    elif py_type == datetime:
        return "datetime-local", extra
    elif py_type == time:
        return "time", extra
    elif py_type == Decimal:
        return "number", {"step": "0.01"}
    elif isinstance(py_type, type) and issubclass(py_type, Enum):
        return "select", {
            "options": [{"value": item.value, "label": item.name} for item in py_type]
        }
    elif issubclass(py_type, BaseModel):
        return "json", extra
    else:
        return "text", extra


def _get_form_fields_from_schema(schema: Type[BaseModel]) -> List[FormField]:
    """
    Generate HTML form field configurations from a Pydantic model schema.

    Analyzes schema fields to determine appropriate HTML input types,
    validation rules, and defaults for form generation.

    Args:
        schema: Pydantic model class to analyze

    Returns:
        List of form field configurations, each containing:
            - name: Field name
            - type: HTML input type
            - required: Whether field is required
            - title: Display title
            - description: Field description
            - examples: Example values
            - min_length/max_length: String length constraints
            - pattern: Regex pattern
            - min/max: Numeric constraints
            - default: Default value
            - Any extra type-specific attributes
    """
    form_fields: List[FormField] = []

    fields_dict = cast(Dict[str, Any], schema.__fields__)

    for field_name, field_info in fields_dict.items():
        field_type = field_info.annotation
        origin_type = get_origin(field_type)

        if origin_type:
            input_type = "text"
            extra: Dict[str, Any] = {}
        else:
            input_type, extra = _get_html_input_type(field_type)

        default = field_info.default
        if callable(field_info.default_factory):
            default = field_info.default_factory()

        field_data: FormField = {
            "name": field_name,
            "type": input_type,
            "required": field_info.is_required(),
            "title": field_info.title or field_name.capitalize(),
            "description": field_info.description,
            "examples": field_info.examples or [],
            "min_length": None,
            "max_length": None,
            "pattern": None,
            "min": None,
            "max": None,
            "default": default if default is not Ellipsis else None,
            **extra,
        }

        form_fields.append(field_data)

    return form_fields
