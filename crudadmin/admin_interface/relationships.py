"""
Relationship detection and display for CRUDAdmin.

Detection of relationships is delegated to fastcrud's native relationship
support (``discover_model_relationships``), and loading of related data uses
fastcrud's ``get_joined`` / ``get_multi`` rather than hand-rolled queries. This
module only adds the UI-facing metadata fastcrud does not provide: which field
to show as a related record's label, and a summary shaped for the admin
templates.

The label field is never guessed. It is taken from the related model's
registered admin view (``add_view(..., display_field=...)``) and falls back to
the related model's primary key when not configured. See
:func:`resolve_display_field`.

Relationship types (from the perspective of the model being viewed):

- ``BelongsTo``: this model has a foreign key to the related model (many-to-one)
- ``HasOne``: the related model has a foreign key back to this model (scalar)
- ``HasMany``: the related model has a foreign key back to this model (collection)
- ``ManyToMany``: association-table relationship
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type

from fastcrud import FastCRUD
from fastcrud.core.field_management import discover_model_relationships
from fastcrud.core.introspection import sa_inspect
from sqlalchemy.orm import MANYTOMANY, MANYTOONE, ONETOMANY, DeclarativeBase

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RelationshipType(str, Enum):
    BELONGS_TO = "BelongsTo"
    HAS_ONE = "HasOne"
    HAS_MANY = "HasMany"
    MANY_TO_MANY = "ManyToMany"


@dataclass
class RelationshipInfo:
    """Information about a relationship on a model.

    Attributes:
        name: The relationship attribute name on the owning model.
        relationship_type: One of the :class:`RelationshipType` values.
        related_model: The model on the other end of the relationship.
        related_model_name: ``related_model.__name__`` (used for admin URLs).
        foreign_key: The foreign key column backing the relationship, if any.
        back_populates: The inverse relationship attribute name, if defined.
        uselist: Whether the relationship is a collection.
        display_field: Column used as the related record's label. Defaults to
            the related model's primary key; the explicit label configured via
            ``add_view(display_field=...)`` is applied at request time by
            :func:`resolve_display_field`. Never guessed from column names.
        available_options: Cached options for relationship dropdowns.
    """

    name: str
    relationship_type: RelationshipType
    related_model: Type[DeclarativeBase]
    related_model_name: str
    foreign_key: Optional[str] = None
    back_populates: Optional[str] = None
    uselist: bool = False
    display_field: str = "id"
    available_options: List[Dict[str, Any]] = field(default_factory=list)


def detect_relationships(model: Type[DeclarativeBase]) -> Dict[str, RelationshipInfo]:
    """Detect relationships defined on a SQLAlchemy model.

    Discovery is delegated to fastcrud's ``discover_model_relationships``; this
    function maps each discovered relationship to the UI-facing
    :class:`RelationshipInfo`.

    Args:
        model: The SQLAlchemy model class to inspect.

    Returns:
        Dictionary mapping relationship names to :class:`RelationshipInfo`.
    """
    relationships: Dict[str, RelationshipInfo] = {}

    for name, prop in discover_model_relationships(model):
        rel_info = _analyze_relationship(name, prop)
        if rel_info is not None:
            relationships[name] = rel_info
            logger.debug(
                "Detected relationship: %s.%s -> %s",
                model.__name__,
                name,
                rel_info.relationship_type.value,
            )

    return relationships


def _analyze_relationship(name: str, prop: Any) -> Optional[RelationshipInfo]:
    """Map a SQLAlchemy relationship property to a :class:`RelationshipInfo`."""
    related_model = prop.mapper.class_

    if prop.direction == MANYTOONE:
        rel_type = RelationshipType.BELONGS_TO
        foreign_key = _local_foreign_key(prop)
    elif prop.direction == ONETOMANY:
        rel_type = (
            RelationshipType.HAS_MANY if prop.uselist else RelationshipType.HAS_ONE
        )
        foreign_key = _remote_foreign_key(prop)
    elif prop.direction == MANYTOMANY:
        rel_type = RelationshipType.MANY_TO_MANY
        foreign_key = None
    else:
        return None

    return RelationshipInfo(
        name=name,
        relationship_type=rel_type,
        related_model=related_model,
        related_model_name=related_model.__name__,
        foreign_key=foreign_key,
        back_populates=prop.back_populates,
        uselist=bool(prop.uselist),
        display_field=_primary_key_name(related_model),
    )


def _local_foreign_key(prop: Any) -> Optional[str]:
    """Foreign key column on this model for a BelongsTo relationship."""
    for local, _remote in prop.local_remote_pairs or []:
        return str(local.name)
    return None


def _remote_foreign_key(prop: Any) -> Optional[str]:
    """Foreign key column on the related model for a HasOne/HasMany relationship."""
    for _local, remote in prop.local_remote_pairs or []:
        return str(remote.name)
    return None


def _primary_key_name(model: Type[DeclarativeBase]) -> str:
    """Return the name of the model's first primary key column."""
    mapper = sa_inspect(model)
    if mapper.primary_key:
        return str(mapper.primary_key[0].name)
    return "id"


def _has_column(model: Type[DeclarativeBase], name: str) -> bool:
    """Whether the model has a (non-relationship) column with the given name."""
    return name in {c.name for c in sa_inspect(model).columns}


def resolve_display_field(
    related_model: Type[DeclarativeBase], configured: Optional[str]
) -> str:
    """Resolve the label field to show for a related model.

    The label is explicit, not guessed: it uses the field configured on the
    related model's admin view (``add_view(..., display_field=...)``) when that
    field is a real column, and otherwise falls back to the primary key.

    Args:
        related_model: The model whose label field is being resolved.
        configured: The ``display_field`` registered for that model, if any.

    Returns:
        The column name to use as the label.
    """
    if configured and _has_column(related_model, configured):
        return configured
    if configured:
        logger.warning(
            "Configured display_field '%s' is not a column on %s; "
            "falling back to the primary key.",
            configured,
            related_model.__name__,
        )
    return _primary_key_name(related_model)


async def load_relationship_options(
    db: "AsyncSession",
    relationship: RelationshipInfo,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Load options for a relationship dropdown using fastcrud's ``get_multi``.

    Returns:
        List of ``{"id": ..., "display_name": ...}`` dictionaries.
    """
    related_model = relationship.related_model
    mapper = sa_inspect(related_model)
    pk_name = mapper.primary_key[0].name

    crud: FastCRUD[Any, Any, Any, Any, Any, Any] = FastCRUD(related_model)
    result = await crud.get_multi(db=db, limit=limit)

    options: List[Dict[str, Any]] = []
    for record in result.get("data", []):
        pk_value = record.get(pk_name)
        display_value = record.get(relationship.display_field, pk_value)
        options.append({"id": pk_value, "display_name": str(display_value)})
    return options


async def load_related_data(
    crud: "FastCRUD[Any, Any, Any, Any, Any, Any]",
    db: "AsyncSession",
    parent_pk_name: str,
    pk_value: Any,
    relationship: RelationshipInfo,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Load related records for a single parent record.

    Uses fastcrud's ``get_joined`` with ``auto_detect_relationships`` scoped to
    the single relationship being expanded, then returns the nested data
    normalized to a list of dictionaries.

    Args:
        crud: A fastcrud instance bound to the parent model.
        db: Database session.
        parent_pk_name: Primary key column name of the parent model.
        pk_value: Primary key value of the parent record.
        relationship: The relationship to load.
        limit: Maximum number of related records to return.

    Returns:
        List of related record dictionaries (empty if none / parent missing).
    """
    parent = await crud.get_joined(
        db=db,
        auto_detect_relationships=[relationship.name],
        nest_joins=True,
        **{parent_pk_name: pk_value},
    )

    if not parent:
        return []

    nested = parent.get(relationship.name)
    if nested is None:
        return []
    if isinstance(nested, list):
        return nested[:limit]
    return [nested]


def get_relationship_summary(
    record: Dict[str, Any],
    relationship: RelationshipInfo,
    related_data: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Summarize relationship data for display in the list view.

    Returns a dict with ``count``, ``display_value`` and ``items`` (plus a
    ``preview`` string for collection relationships).
    """
    count = len(related_data)
    is_collection = relationship.relationship_type in (
        RelationshipType.HAS_MANY,
        RelationshipType.MANY_TO_MANY,
    )

    if not is_collection:
        if related_data:
            item = related_data[0]
            display = item.get(relationship.display_field, item.get("id", "-"))
            return {
                "count": 1,
                "display_value": str(display),
                "items": related_data[:1],
            }
        return {"count": 0, "display_value": "-", "items": []}

    if related_data:
        previews = [
            str(item.get(relationship.display_field, item.get("id", "")))
            for item in related_data[:3]
        ]
        return {
            "count": count,
            "display_value": f"{count} items",
            "items": related_data[:5],
            "preview": ", ".join(previews) + ("..." if count > 3 else ""),
        }
    return {"count": 0, "display_value": "0 items", "items": [], "preview": ""}
