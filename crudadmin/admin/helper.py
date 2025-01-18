from typing import get_origin
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, EmailStr, HttpUrl, AnyHttpUrl

def _get_html_input_type(py_type: type) -> tuple[str, dict]:
    """Get HTML input type and any additional attributes."""
    extra = {}
    
    if py_type in [int, float]:
        return 'number', extra
    elif py_type == bool:
        return 'checkbox', extra
    elif py_type == EmailStr:
        return 'email', extra
    elif py_type in [HttpUrl, AnyHttpUrl]:
        return 'url', extra
    elif py_type == date:
        return 'date', extra
    elif py_type == datetime:
        return 'datetime-local', extra
    elif py_type == time:
        return 'time', extra
    elif py_type == Decimal:
        return 'number', {"step": "0.01"}
    elif isinstance(py_type, type) and issubclass(py_type, Enum):
        return 'select', {"options": [
            {"value": item.value, "label": item.name} 
            for item in py_type
        ]}
    elif issubclass(py_type, BaseModel):
        return 'json', extra
    else:
        return 'text', extra

def _get_form_fields_from_schema(schema: BaseModel) -> list[dict]:
    form_fields = []
    for field_name, field_info in schema.__fields__.items():
        field_type = field_info.annotation
        origin_type = get_origin(field_type)
        if origin_type:
            input_type = 'text'
            extra = {}
        else:
            input_type, extra = _get_html_input_type(field_type)

        default = field_info.default
        if callable(field_info.default_factory):
            default = field_info.default_factory()

        field_data = {
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
            **extra  # Add any extra attributes
        }

        form_fields.append(field_data)
    
    return form_fields
