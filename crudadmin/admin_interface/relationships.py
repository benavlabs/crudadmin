"""
Relationship detection and handling for CRUDAdmin.

Supports:
- BelongsTo: Current model has foreign key to another model
- HasOne: Another model has foreign key to current model (single record)
- HasMany: Another model has foreign key to current model (multiple records)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.orm import RelationshipProperty, ONETOMANY, MANYTOONE, MANYTOMANY
from sqlalchemy.orm import DeclarativeBase

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
    """Information about a relationship on a model."""
    name: str
    relationship_type: RelationshipType
    related_model: Type[DeclarativeBase]
    related_model_name: str
    foreign_key: Optional[str] = None
    back_populates: Optional[str] = None
    uselist: bool = False
    # For display purposes
    display_field: str = "id"
    # Runtime data
    available_options: List[Dict[str, Any]] = field(default_factory=list)


def detect_relationships(model: Type[DeclarativeBase]) -> Dict[str, RelationshipInfo]:
    """
    Detect relationships defined on a SQLAlchemy model.

    Args:
        model: The SQLAlchemy model class to inspect

    Returns:
        Dictionary mapping relationship names to RelationshipInfo objects
    """
    relationships: Dict[str, RelationshipInfo] = {}

    try:
        mapper = inspect(model)
    except Exception as e:
        logger.warning(f"Could not inspect model {model}: {e}")
        return relationships

    for prop in mapper.relationships:
        try:
            rel_info = _analyze_relationship(prop)
            if rel_info:
                relationships[prop.key] = rel_info
                logger.debug(f"Detected relationship: {model.__name__}.{prop.key} -> {rel_info.relationship_type.value}")
        except Exception as e:
            logger.warning(f"Error analyzing relationship {prop.key}: {e}")

    return relationships


def _analyze_relationship(prop: RelationshipProperty) -> Optional[RelationshipInfo]:
    """Analyze a relationship property and return RelationshipInfo."""

    related_model = prop.mapper.class_
    related_model_name = related_model.__name__

    # Determine relationship type based on direction and uselist
    if prop.direction == MANYTOONE:
        # This model has a foreign key to the related model
        rel_type = RelationshipType.BELONGS_TO
        foreign_key = _get_foreign_key_column(prop)
    elif prop.direction == ONETOMANY:
        if prop.uselist:
            # Related model has FK to this model, multiple records
            rel_type = RelationshipType.HAS_MANY
        else:
            # Related model has FK to this model, single record
            rel_type = RelationshipType.HAS_ONE
        foreign_key = _get_remote_foreign_key(prop)
    elif prop.direction == MANYTOMANY:
        rel_type = RelationshipType.MANY_TO_MANY
        foreign_key = None
    else:
        return None

    # Try to find a good display field on the related model
    display_field = _find_display_field(related_model)

    return RelationshipInfo(
        name=prop.key,
        relationship_type=rel_type,
        related_model=related_model,
        related_model_name=related_model_name,
        foreign_key=foreign_key,
        back_populates=prop.back_populates,
        uselist=prop.uselist,
        display_field=display_field,
    )


def _get_foreign_key_column(prop: RelationshipProperty) -> Optional[str]:
    """Get the foreign key column name for a BelongsTo relationship."""
    for local, remote in prop.local_remote_pairs:
        return local.name
    return None


def _get_remote_foreign_key(prop: RelationshipProperty) -> Optional[str]:
    """Get the foreign key column on the remote model."""
    for local, remote in prop.local_remote_pairs:
        return remote.name
    return None


def _find_display_field(model: Type[DeclarativeBase]) -> str:
    """Find a suitable display field for a model (name, title, etc.)."""
    try:
        mapper = inspect(model)
        column_names = [c.name for c in mapper.columns]

        # Priority list of common display field names
        display_candidates = ['name', 'title', 'label', 'display_name', 'hostname', 'username', 'email']

        for candidate in display_candidates:
            if candidate in column_names:
                return candidate

        # Fall back to first string column that isn't an ID
        for col in mapper.columns:
            if hasattr(col.type, 'python_type'):
                try:
                    if col.type.python_type == str and not col.name.endswith('_id') and col.name != 'id':
                        return col.name
                except:
                    pass

        # Last resort: use primary key
        pk_cols = mapper.primary_key
        if pk_cols:
            return pk_cols[0].name

    except Exception as e:
        logger.warning(f"Error finding display field for {model}: {e}")

    return "id"


async def load_relationship_options(
    db: "AsyncSession",
    relationship: RelationshipInfo,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Load available options for a relationship (for dropdowns/selects).

    Args:
        db: Database session
        relationship: The relationship to load options for
        limit: Maximum number of options to load

    Returns:
        List of dictionaries with 'id' and 'display_name' keys
    """
    from sqlalchemy import select

    try:
        model = relationship.related_model
        mapper = inspect(model)
        pk_col = mapper.primary_key[0]
        display_col = getattr(model, relationship.display_field, pk_col)

        stmt = select(model).limit(limit)
        result = await db.execute(stmt)
        records = result.scalars().all()

        options = []
        for record in records:
            pk_value = getattr(record, pk_col.name)
            display_value = getattr(record, relationship.display_field, pk_value)
            options.append({
                "id": pk_value,
                "display_name": str(display_value),
            })

        return options
    except Exception as e:
        logger.error(f"Error loading relationship options: {e}")
        return []


async def load_related_data(
    db: "AsyncSession",
    model: Type[DeclarativeBase],
    pk_value: Any,
    relationship: RelationshipInfo,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Load related records for a specific relationship.

    Args:
        db: Database session
        model: The parent model
        pk_value: Primary key value of the parent record
        relationship: The relationship to load
        limit: Maximum number of related records

    Returns:
        List of related record dictionaries
    """
    from sqlalchemy import select

    try:
        related_model = relationship.related_model

        if relationship.relationship_type == RelationshipType.BELONGS_TO:
            # Load the single related parent record
            mapper = inspect(related_model)
            pk_col = mapper.primary_key[0]

            # Get the FK value from the current record
            parent_mapper = inspect(model)
            fk_col = relationship.foreign_key

            stmt = select(model).where(parent_mapper.primary_key[0] == pk_value)
            result = await db.execute(stmt)
            parent_record = result.scalar_one_or_none()

            if parent_record and fk_col:
                fk_value = getattr(parent_record, fk_col)
                stmt = select(related_model).where(pk_col == fk_value)
                result = await db.execute(stmt)
                related = result.scalar_one_or_none()
                if related:
                    return [_record_to_dict(related)]
            return []

        elif relationship.relationship_type in [RelationshipType.HAS_ONE, RelationshipType.HAS_MANY]:
            # Load child record(s) that have FK to this record
            fk_col = getattr(related_model, relationship.foreign_key)
            stmt = select(related_model).where(fk_col == pk_value).limit(limit)
            result = await db.execute(stmt)
            records = result.scalars().all()
            return [_record_to_dict(r) for r in records]

    except Exception as e:
        logger.error(f"Error loading related data: {e}")

    return []


def _record_to_dict(record: Any) -> Dict[str, Any]:
    """Convert a SQLAlchemy record to a dictionary."""
    try:
        mapper = inspect(type(record))
        return {c.name: getattr(record, c.name) for c in mapper.columns}
    except:
        return {}


def get_relationship_summary(
    record: Dict[str, Any],
    relationship: RelationshipInfo,
    related_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Get a summary of relationship data for display in list view.

    Returns dict with:
    - count: Number of related records
    - display_value: String representation for display
    - items: First few items for preview
    """
    count = len(related_data)

    if relationship.relationship_type == RelationshipType.BELONGS_TO:
        if related_data:
            item = related_data[0]
            display = item.get(relationship.display_field, item.get('id', '-'))
            return {
                "count": 1,
                "display_value": str(display),
                "items": related_data[:1],
            }
        return {"count": 0, "display_value": "-", "items": []}

    elif relationship.relationship_type == RelationshipType.HAS_ONE:
        if related_data:
            item = related_data[0]
            display = item.get(relationship.display_field, item.get('id', '-'))
            return {
                "count": 1,
                "display_value": str(display),
                "items": related_data[:1],
            }
        return {"count": 0, "display_value": "-", "items": []}

    else:  # HAS_MANY
        if related_data:
            previews = [str(item.get(relationship.display_field, item.get('id', '')))
                       for item in related_data[:3]]
            display = f"{count} items"
            return {
                "count": count,
                "display_value": display,
                "items": related_data[:5],
                "preview": ", ".join(previews) + ("..." if count > 3 else ""),
            }
        return {"count": 0, "display_value": "0 items", "items": [], "preview": ""}
