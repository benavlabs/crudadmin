from typing import get_origin
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, HttpUrl, AnyHttpUrl


def _get_html_input_type(py_type: type) -> str:
    if py_type in [int, float]:
        return 'number'
    elif py_type == bool:
        return 'checkbox'
    elif py_type == EmailStr:
        return 'email'
    elif py_type in [HttpUrl, AnyHttpUrl]:
        return 'url'
    elif py_type in [date, datetime]:
        return 'datetime-local' if py_type == datetime else 'date'
    elif issubclass(py_type, BaseModel):
        return 'text'
    else:
        return 'text'

    
def _get_form_fields_from_schema(schema: BaseModel) -> list[dict]:
    form_fields = []
    for field_name, field_info in schema.__fields__.items():
        field_type = field_info.annotation
        origin_type = get_origin(field_type)
        if origin_type:
            input_type = 'text'
        else:
            input_type = _get_html_input_type(field_type)

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
            "default": default if default is not Ellipsis else None
        }

        form_fields.append(field_data)
    
    return form_fields
