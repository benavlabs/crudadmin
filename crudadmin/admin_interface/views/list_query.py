from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

ROWS_PER_PAGE_OPTIONS = (10, 20, 50, 100)
DEFAULT_ROWS_PER_PAGE = ROWS_PER_PAGE_OPTIONS[0]
TRUE_WORDS = ("true", "yes", "1", "t", "y")
FALSE_WORDS = ("false", "no", "0", "f", "n")


def rows_per_page(value: Optional[str]) -> int:
    """Parse the rows-per-page query value, falling back to the default.

    Only the page sizes the list page offers are accepted, so a request cannot
    ask for an unbounded number of rows.
    """
    try:
        rows = int(value) if value is not None else DEFAULT_ROWS_PER_PAGE
    except ValueError:
        return DEFAULT_ROWS_PER_PAGE
    return rows if rows in ROWS_PER_PAGE_OPTIONS else DEFAULT_ROWS_PER_PAGE


def search_filters(
    model: Type[DeclarativeBase], column_name: Optional[str], value: str
) -> Dict[str, Any]:
    """FastCRUD filters for a search of one column, matched by the column's type.

    Text matches anywhere, case-insensitively; numbers, booleans and UUIDs match
    exactly. A value that doesn't fit the column's type, or an unknown column,
    filters nothing.
    """
    if not column_name or not value:
        return {}
    column = model.__table__.columns.get(column_name)
    if column is None:
        return {}
    python_type = column.type.python_type
    try:
        if python_type is int:
            return {column_name: int(value)}
        if python_type is float:
            return {column_name: float(value)}
        if python_type is bool:
            word = value.lower()
            if word in TRUE_WORDS:
                return {column_name: True}
            if word in FALSE_WORDS:
                return {column_name: False}
            return {}
        if python_type is str:
            return {f"{column_name}__ilike": f"%{value}%"}
        if python_type is UUID:
            return {column_name: UUID(value)}
    except (ValueError, TypeError):
        return {}
    return {}


def table_columns(
    model: Type[DeclarativeBase], select_schema: Optional[Type[BaseModel]]
) -> List[str]:
    """The columns the list shows: the select schema's fields, or every column."""
    if select_schema:
        return list(select_schema.model_fields.keys())
    return [column.key for column in model.__table__.columns]


@dataclass(frozen=True)
class ListQuery:
    """The page, sort and search a list request asks for, checked against the model.

    An unknown sort column is ignored and an unknown sort order means ascending;
    a page below 1 or that isn't a number means the first page.
    """

    page: int
    rows_per_page: int
    sort_column: Optional[str]
    sort_order: str
    search_column: Optional[str]
    search_value: str

    @classmethod
    def from_request(
        cls, request: Request, model: Type[DeclarativeBase]
    ) -> "ListQuery":
        params = request.query_params
        try:
            page = max(1, int(params.get("page", "1")))
        except ValueError:
            page = 1

        sort_column = params.get("sort_by")
        if sort_column not in model.__table__.columns.keys():
            sort_column = None
        sort_order = params.get("sort_order")
        if sort_order not in ("asc", "desc"):
            sort_order = "asc"

        return cls(
            page=page,
            rows_per_page=rows_per_page(params.get("rows-per-page-select")),
            sort_column=sort_column,
            sort_order=sort_order,
            search_column=params.get("column-to-search"),
            search_value=params.get("search-input", "").strip(),
        )

    def filters(self, model: Type[DeclarativeBase]) -> Dict[str, Any]:
        return search_filters(model, self.search_column, self.search_value)

    def sorting(self) -> Dict[str, Optional[List[str]]]:
        """The ``sort_columns`` and ``sort_orders`` arguments for FastCRUD."""
        if not self.sort_column:
            return {"sort_columns": None, "sort_orders": None}
        return {"sort_columns": [self.sort_column], "sort_orders": [self.sort_order]}

    def last_page(self, total_items: int) -> int:
        return max(1, (total_items + self.rows_per_page - 1) // self.rows_per_page)
