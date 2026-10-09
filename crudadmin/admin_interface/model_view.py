from collections.abc import AsyncGenerator, Callable
from dataclasses import replace
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Type,
    TypeVar,
    Union,
)
from uuid import UUID

from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from ..core.db import (
    DatabaseConfig,
    convert_id_to_pk_type,
    get_primary_key_name,
)
from ..event.recorder import AdminEvents
from .paths import AdminPaths
from .relationships import (
    RelationshipInfo,
    RelationshipType,
    detect_relationships,
    load_relationship_options,
    resolve_display_field,
)
from .typing import EndpointCallable
from .views.create import create_endpoint, create_page
from .views.delete import BulkDeleteRequest, bulk_delete_endpoint
from .views.forms import PasswordTransformer
from .views.listing import list_page
from .views.related_records import related_data_endpoint, relationship_options_endpoint
from .views.update import update_endpoint, update_page

__all__ = ["BulkDeleteRequest", "ModelView", "PasswordTransformer"]

CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
UpdateSchemaInternalType = TypeVar("UpdateSchemaInternalType", bound=BaseModel)
DeleteSchemaType = TypeVar("DeleteSchemaType", bound=BaseModel)
SelectSchemaType = TypeVar("SelectSchemaType", bound=BaseModel)


class ModelView:
    r"""
    View class for managing CRUD operations and UI for database models in FastAPI admin interface.

    Features:
        - Automatic form generation from Pydantic schemas
        - List view with pagination, sorting, and filtering
        - Create/update forms with validation
        - Bulk delete operations
        - Event logging integration
        - HTMX-powered dynamic updates

    Args:
        database_config: DatabaseConfig instance for DB connections
        templates: Jinja2Templates instance for rendering views
        model: SQLAlchemy model class to manage
        allowed_actions: Set of allowed operations ('view', 'create', 'update', 'delete')
        create_schema: Pydantic schema for create operations
        update_schema: Pydantic schema for update operations
        update_internal_schema: Optional internal schema for special update cases
        delete_schema: Optional schema for delete operations
        select_schema: Optional schema for select operations
        admin_model: Whether this is an admin-specific model
        admin_site: Reference to parent AdminSite instance
        event_integration: Optional event logging integration
        password_transformer: Optional password transformer for AdminUser model

    Raises:
        ValueError: If schemas don't match model structure
        TypeError: If model is not a SQLAlchemy model
        RuntimeError: If required dependencies are missing

    Notes:
        - Forms are auto-generated based on Pydantic schema definitions
        - List views support server-side pagination and filtering
        - Changes are tracked if event logging is enabled
        - HTMX is used for dynamic content updates
        - Templates can be customized by overriding defaults

    URLs Generated:
        **List View:**
            GET /{model_name}/ - Main list view with pagination
            GET /{model_name}/get_model_list - HTMX-powered list content

        **Create:**
            GET /{model_name}/create_page - Create form
            POST /{model_name}/form_create - Handle create submission

        **Update:**
            GET /{model_name}/update/{id} - Update form for specific record
            POST /{model_name}/form_update/{id} - Handle update submission

        **Delete:**
            DELETE /{model_name}/bulk-delete - Bulk delete selected records

        **API Endpoints:**
            All CRUD operations also exposed as REST API endpoints under /crud/

    Example:
        Basic model view setup:
        ```python
        from pydantic import BaseModel, Field
        from sqlalchemy import Column, Integer, String
        from sqlalchemy.ext.declarative import DeclarativeBase

        # Define model
        class User(DeclarativeBase):
            __tablename__ = "users"
            id = Column(Integer, primary_key=True)
            username = Column(String, unique=True)
            email = Column(String)
            role = Column(String)

        # Define schemas
        class UserCreate(BaseModel):
            username: str = Field(..., min_length=3)
            email: str = Field(..., pattern=r"[^@]+@[^@]+\.[^@]+")
            role: str = Field(default="user")

        class UserUpdate(BaseModel):
            email: Optional[str] = Field(None, pattern=r"[^@]+@[^@]+\.[^@]+")
            role: Optional[str] = None

        # Create view
        user_view = ModelView(
            database_config=db_config,
            templates=templates,
            model=User,
            create_schema=UserCreate,
            update_schema=UserUpdate,
            allowed_actions={"view", "create", "update"}
        )
        ```

        Custom form validation:
        ```python
        from datetime import datetime
        from decimal import Decimal
        from typing import Optional
        from pydantic import BaseModel, Field, validator

        class OrderCreate(BaseModel):
            customer_id: int
            total: Decimal = Field(..., ge=0)
            status: str = Field(default="pending")
            notes: Optional[str] = None

            @validator("total")
            def validate_total(cls, v):
                if v > 1000000:
                    raise ValueError("Order total cannot exceed 1,000,000")
                return v

            @validator("status")
            def validate_status(cls, v):
                allowed = {"pending", "paid", "shipped", "cancelled"}
                if v not in allowed:
                    raise ValueError(f"Status must be one of: {allowed}")
                return v

        class OrderUpdate(BaseModel):
            status: Optional[str] = None
            notes: Optional[str] = None

            @validator("status")
            def validate_status(cls, v):
                if v is not None:
                    allowed = {"pending", "paid", "shipped", "cancelled"}
                    if v not in allowed:
                        raise ValueError(f"Status must be one of: {allowed}")
                return v

        order_view = ModelView(
            database_config=db_config,
            templates=templates,
            model=Order,
            create_schema=OrderCreate,
            update_schema=OrderUpdate,
            allowed_actions={"view", "create", "update"}
        )
        ```

        Event logging integration:
        ```python
        from typing import Optional
        from datetime import datetime
        from pydantic import BaseModel, Field

        class ProductCreate(BaseModel):
            name: str
            price: float = Field(..., gt=0)
            stock: int = Field(..., ge=0)

        class ProductUpdate(BaseModel):
            name: Optional[str] = None
            price: Optional[float] = Field(None, gt=0)
            stock: Optional[int] = Field(None, ge=0)

        # With event logging
        product_view = ModelView(
            database_config=db_config,
            templates=templates,
            model=Product,
            create_schema=ProductCreate,
            update_schema=ProductUpdate,
            event_integration=event_logger,  # Enable logging
            allowed_actions={"view", "create", "update", "delete"}
        )

        # Events logged:
        # - Record creation with user info
        # - Updates with change details
        # - Deletions with record info
        # - View access for audit trails
        ```

        Custom templates:
        ```python
        templates = Jinja2Templates(directory="custom_templates")

        # Override default templates
        custom_templates = {
            "list": "custom/model/list.html",
            "create": "custom/model/create.html",
            "update": "custom/model/update.html"
        }

        view = ModelView(
            database_config=db_config,
            templates=templates,  # Custom templates
            model=User,
            create_schema=UserCreate,
            update_schema=UserUpdate,
            allowed_actions={"view", "create", "update"}
        )
        ```

        Restricted actions:
        ```python
        # Read-only view
        readonly_view = ModelView(
            database_config=db_config,
            templates=templates,
            model=AuditLog,
            create_schema=AuditLogSchema,
            update_schema=AuditLogSchema,
            allowed_actions={"view"}  # View only
        )

        # No delete view
        no_delete_view = ModelView(
            database_config=db_config,
            templates=templates,
            model=Customer,
            create_schema=CustomerCreate,
            update_schema=CustomerUpdate,
            allowed_actions={"view", "create", "update"}  # No delete
        )
        ```
    """

    def __init__(
        self,
        database_config: DatabaseConfig,
        templates: Jinja2Templates,
        model: Type[DeclarativeBase],
        allowed_actions: Set[str],
        create_schema: Type[CreateSchemaType],
        update_schema: Type[UpdateSchemaType],
        update_internal_schema: Optional[Type[UpdateSchemaInternalType]] = None,
        delete_schema: Optional[Type[DeleteSchemaType]] = None,
        select_schema: Optional[Type[SelectSchemaType]] = None,
        admin_model: bool = False,
        admin_site: Optional[Any] = None,
        event_integration: Optional[Any] = None,
        password_transformer: Optional[PasswordTransformer] = None,
        write_dependencies: Optional[List[Any]] = None,
    ) -> None:
        self.db_config = database_config
        self.write_dependencies: List[Any] = list(write_dependencies or [])
        self.templates = templates
        self.model = model
        self.model_key = model.__name__
        self.primary_key_name = get_primary_key_name(model)
        self.router = APIRouter()
        self.admin_model = admin_model
        self.admin_site = admin_site
        self.allowed_actions = allowed_actions
        self.event_integration = event_integration
        self.events = AdminEvents(event_integration)
        self.password_transformer = password_transformer

        get_session: Callable[[], AsyncGenerator[AsyncSession, None]]
        if self._model_is_admin_model(model):
            get_session = self.db_config.get_admin_db
        else:
            get_session = self.db_config.session
        self.session = get_session

        self.create_schema = create_schema
        self.update_schema = update_schema
        self.update_internal_schema = update_internal_schema
        self.delete_schema = delete_schema
        self.select_schema = select_schema

        if self.model.__name__ == "AdminUser" and password_transformer is None:
            from crudauth import get_password_hash

            self.password_transformer = PasswordTransformer(
                password_field="password",
                hashed_field="hashed_password",
                hash_function=get_password_hash,
                required_fields=["username"],
            )

        self.crud: FastCRUD[Any, Any, Any, Any, Any, Any] = FastCRUD(self.model)
        self.relationships: Dict[str, RelationshipInfo] = detect_relationships(
            self.model
        )

        self.setup_routes()

    def get_url_prefix(self) -> str:
        """Get the URL prefix for admin routes, handling root mount path correctly."""
        return self._paths.prefix

    @property
    def _paths(self) -> AdminPaths:
        if self.admin_site is not None:
            site_paths: AdminPaths = self.admin_site.paths
            return site_paths
        return AdminPaths(prefix="")

    def _model_list_url(self) -> str:
        return self._paths.model(self.model_key)

    async def _snapshot(
        self, db: AsyncSession, record_id: Any
    ) -> Optional[Dict[str, Any]]:
        """The whole record for the event log, or None when events aren't recorded.

        Every column is read, so a changed password still shows as a change; the
        event log redacts its value.
        """
        if not self.events.enabled:
            return None
        record = await self.crud.get(db=db, **self._pk_filter(record_id))
        return dict(record) if record else None

    def _forget_record_count(self) -> None:
        """Make the dashboard recount this model after the admin added or deleted records."""
        if self.admin_site is not None:
            self.admin_site.record_counts.forget(self.model_key)

    def _model_is_admin_model(self, model: Type[DeclarativeBase]) -> bool:
        """Check if a model is considered an admin model."""
        return self.admin_model or self.model_key.lower() in {"adminuser", "admin_user"}

    def _convert_id_to_pk_type(
        self, id_value: Optional[Union[int, str]]
    ) -> Union[int, str, float, UUID, None]:
        """Convert the ID value to the appropriate type based on the model's primary key type."""
        if id_value is None:
            return None

        return convert_id_to_pk_type(id_value, self.db_config, self.model)

    def _pk_filter(self, pk_value: Any) -> Dict[str, Any]:
        """Build the primary-key filter kwargs for FastCRUD get/update calls.

        Uses the model's actual primary-key column name so models whose key is
        not ``id`` work correctly.
        """
        return {self.primary_key_name: pk_value}

    def _with_resolved_display_field(
        self, relationship: RelationshipInfo
    ) -> RelationshipInfo:
        """Return a copy of the relationship with its label field resolved.

        The label uses the ``display_field`` configured on the related model's
        admin view, falling back to the related model's primary key. Resolution
        happens at request time so it is independent of ``add_view`` ordering.
        """
        configured: Optional[str] = None
        if self.admin_site is not None:
            related_config = self.admin_site.models.get(relationship.related_model_name)
            if related_config is not None:
                configured = related_config.get("display_field")

        display_field = resolve_display_field(relationship.related_model, configured)
        if display_field == relationship.display_field:
            return relationship
        return replace(relationship, display_field=display_field)

    async def _apply_relationship_form_fields(
        self, form_fields: List[Dict[str, Any]], db: AsyncSession
    ) -> None:
        """Turn foreign-key form fields into relationship dropdowns.

        For each ``BelongsTo`` relationship, the form field matching its foreign
        key column is marked as a ``relationship_select`` and populated with the
        related records (label resolved via the related model's ``display_field``)
        so the user picks from existing rows instead of typing a raw id.
        """
        fk_relationships = {
            rel.foreign_key: rel
            for rel in self.relationships.values()
            if rel.relationship_type == RelationshipType.BELONGS_TO and rel.foreign_key
        }
        if not fk_relationships:
            return

        for field in form_fields:
            relationship = fk_relationships.get(field["name"])
            if relationship is None:
                continue
            resolved = self._with_resolved_display_field(relationship)
            field["type"] = "relationship_select"
            field["related_model_name"] = resolved.related_model_name
            field["options"] = await load_relationship_options(db, resolved)

    def setup_routes(self) -> None:
        """
        Configure FastAPI routes based on allowed actions.

        Sets up the following routes if allowed:
        - Create: /form_create (POST), /create_page (GET)
        - View: / (GET), /get_model_list (GET)
        - Delete: /bulk-delete (DELETE)
        - Update: /update/{id} (GET), /form_update/{id} (POST)

        Routes are configured based on the allowed_actions set provided during initialization.
        All routes use appropriate templates and include required dependencies. Every route
        declares an authentication dependency in addition to the admin auth middleware, so a
        request that reaches an endpoint without a valid session is rejected there as well.

        Example:
            ```python
            # Configure with specific actions
            view = ModelView(
                allowed_actions={"view", "create", "update"},
                ...
            )
            view.setup_routes()  # Only creates view/create/update routes
            ```
        """
        write_dependencies = self.write_dependencies

        if "create" in self.allowed_actions:
            self.router.add_api_route(
                "/form_create",
                self.form_create_endpoint(template="admin/model/create.html"),
                methods=["POST"],
                include_in_schema=False,
                dependencies=self.write_dependencies,
                response_model=None,
            )
            self.router.add_api_route(
                "/create_page",
                self.get_model_create_page(template="admin/model/create.html"),
                methods=["GET"],
                include_in_schema=False,
                dependencies=write_dependencies,
                response_model=None,
            )

        if "view" in self.allowed_actions:
            self.router.add_api_route(
                "/",
                self.get_model_admin_page(),
                methods=["GET"],
                include_in_schema=False,
                response_model=None,
            )
            self.router.add_api_route(
                "/get_model_list",
                self.get_model_admin_page(
                    template="admin/model/components/list_content.html"
                ),
                methods=["GET"],
                include_in_schema=False,
                response_model=None,
            )

        if "delete" in self.allowed_actions:
            self.router.add_api_route(
                "/bulk-delete",
                self.bulk_delete_endpoint(),
                methods=["DELETE"],
                include_in_schema=False,
                dependencies=self.write_dependencies,
                response_model=None,
            )

        if "update" in self.allowed_actions:
            self.router.add_api_route(
                "/update/{id}",
                self.get_model_update_page(template="admin/model/update.html"),
                methods=["GET"],
                include_in_schema=False,
                dependencies=write_dependencies,
                response_model=None,
            )
            self.router.add_api_route(
                "/form_update/{id}",
                self.form_update_endpoint(),
                methods=["POST"],
                include_in_schema=False,
                dependencies=self.write_dependencies,
                response_model=None,
            )

        if self.relationships:
            self.router.add_api_route(
                "/related/{id}/{relationship_name}",
                self.get_related_data_endpoint(),
                methods=["GET"],
                include_in_schema=False,
                response_model=None,
            )
            self.router.add_api_route(
                "/relationship-options/{relationship_name}",
                self.get_relationship_options_endpoint(),
                methods=["GET"],
                include_in_schema=False,
                response_model=None,
            )

    def form_create_endpoint(self, template: str) -> EndpointCallable:
        """The endpoint that creates a record from the submitted form."""
        return create_endpoint(self, template)

    def bulk_delete_endpoint(self) -> EndpointCallable:
        """The endpoint that deletes the records whose ids are posted as JSON."""
        return bulk_delete_endpoint(self)

    def get_model_admin_page(
        self, template: str = "admin/model/list.html"
    ) -> EndpointCallable:
        """The endpoint that lists the model's records, paginated, sorted and searched."""
        return list_page(self, template)

    def get_model_create_page(
        self, template: str = "admin/model/create.html"
    ) -> EndpointCallable:
        """The endpoint that shows a blank form for a new record."""
        return create_page(self, template)

    def get_model_update_page(self, template: str) -> EndpointCallable:
        """The endpoint that shows the form filled with a record to update."""
        return update_page(self, template)

    def form_update_endpoint(self) -> EndpointCallable:
        """The endpoint that updates a record from the submitted form."""
        return update_endpoint(self)

    def get_related_data_endpoint(self) -> EndpointCallable:
        """The endpoint that shows a record's related records."""
        return related_data_endpoint(self)

    def get_relationship_options_endpoint(self) -> EndpointCallable:
        """The endpoint that lists the options of a relationship dropdown."""
        return relationship_options_endpoint(self)
