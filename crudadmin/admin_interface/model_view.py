from typing import (
    TypeVar,
    Type,
    List,
    Optional,
    Any,
    Callable,
    Dict,
    Set,
    cast,
    Coroutine,
    AsyncGenerator,
    Union,
)
import datetime
from datetime import timezone

from fastapi import APIRouter, Request, Depends, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect
from fastcrud import FastCRUD, EndpointCreator

from ..core.db import DatabaseConfig
from ..event import log_admin_action, EventType
from .helper import _get_form_fields_from_schema

EndpointCallable = Callable[..., Coroutine[Any, Any, Response]]

ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
UpdateSchemaInternalType = TypeVar("UpdateSchemaInternalType", bound=BaseModel)
DeleteSchemaType = TypeVar("DeleteSchemaType", bound=BaseModel)
SelectSchemaType = TypeVar("SelectSchemaType", bound=BaseModel)


class BulkDeleteRequest(BaseModel):
    """Request model for bulk delete operations containing IDs to delete."""

    ids: List[int]


class ModelView:
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
    ) -> None:
        self.db_config = database_config
        self.templates = templates
        self.model = model
        self.model_key = model.__name__
        self.router = APIRouter()

        get_session: Callable[[], AsyncGenerator[AsyncSession, None]]
        if self._model_is_admin_model(model):
            get_session = self.db_config.get_admin_db
        else:
            get_session = cast(
                Callable[[], AsyncGenerator[AsyncSession, None]], self.db_config.session
            )
        self.session = get_session

        self.create_schema = create_schema
        self.update_schema = update_schema
        self.update_internal_schema = update_internal_schema
        self.delete_schema = delete_schema
        self.select_schema = select_schema

        self.admin_model = admin_model
        self.admin_site = admin_site
        self.allowed_actions = allowed_actions
        self.event_integration = event_integration

        self.user_service = (
            self.admin_site.admin_user_service if self.admin_site else None
        )

        self.crud: FastCRUD[Any, Any, Any, Any, Any, Any] = FastCRUD(self.model)

        self.endpoints_template = EndpointCreator(
            session=self.session,
            model=self.model,
            crud=self.crud,
            create_schema=self.create_schema,
            update_schema=self.update_schema,
            delete_schema=self.delete_schema,
        )
        self.endpoints_template.add_routes_to_router()
        self.router.include_router(self.endpoints_template.router, prefix="/crud")

        self.setup_routes()

    def _model_is_admin_model(self, model: Type[DeclarativeBase]) -> bool:
        """Check if the model is one of the known admin models."""
        admin_models = {
            self.db_config.AdminUser.__name__,
            self.db_config.AdminTokenBlacklist.__name__,
            self.db_config.AdminSession.__name__,
        }
        return model.__name__ in admin_models

    def setup_routes(self) -> None:
        """Configure FastAPI routes based on allowed actions."""
        if "create" in self.allowed_actions:
            self.router.add_api_route(
                "/form_create",
                self.form_create_endpoint(template="admin/model/create.html"),
                methods=["POST"],
                include_in_schema=False,
                response_model=None,
            )
            self.router.add_api_route(
                "/create_page",
                self.get_model_create_page(template="admin/model/create.html"),
                methods=["GET"],
                include_in_schema=False,
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
                response_model=None,
            )

        if "update" in self.allowed_actions:
            self.router.add_api_route(
                "/update/{id}",
                self.get_model_update_page(template="admin/model/update.html"),
                methods=["GET"],
                include_in_schema=False,
                response_model=None,
            )
            self.router.add_api_route(
                "/form_update/{id}",
                self.form_update_endpoint(),
                methods=["POST"],
                include_in_schema=False,
                response_model=None,
            )

    def form_create_endpoint(self, template: str) -> EndpointCallable:
        @log_admin_action(EventType.CREATE, model=self.model)
        async def form_create_endpoint_inner(
            request: Request,
            db: AsyncSession = Depends(self.session),
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
            current_user: dict = Depends(
                cast(Any, self.admin_site).admin_authentication.get_current_user()
            ),
            event_integration=Depends(lambda: self.event_integration),
        ) -> Response:
            """Handle POST form submission to create a model record."""
            assert self.admin_site is not None

            form_fields = _get_form_fields_from_schema(self.create_schema)
            error_message: Optional[str] = None
            field_errors: Dict[str, str] = {}
            field_values: Dict[str, Any] = {}

            try:
                if request.method == "POST":
                    form_data_raw = await request.form()
                    form_data: Dict[str, Any] = {}

                    for field in form_fields:
                        key = field["name"]
                        raw_value = form_data_raw.getlist(key)
                        if len(raw_value) == 1:
                            value = raw_value[0]
                            form_data[key] = value if value else field.get("default")
                            field_values[key] = value
                        elif len(raw_value) > 1:
                            form_data[key] = raw_value
                            field_values[key] = raw_value
                        else:
                            form_data[key] = field.get("default")

                    try:
                        if self.model.__name__ == "AdminUser":
                            if not self.user_service:
                                raise ValueError("No user_service available.")
                            item_data = self.create_schema(**form_data)

                            password = getattr(item_data, "password", None)
                            if password is not None:
                                hashed_password = self.user_service.get_password_hash(
                                    password
                                )
                            else:
                                hashed_password = None

                            username = getattr(item_data, "username", None)
                            if username is None:
                                raise ValueError("AdminUser requires a username.")

                            from ..admin_user.schemas import AdminUserCreateInternal

                            internal_data = AdminUserCreateInternal(
                                username=username,
                                hashed_password=hashed_password or "",
                            )
                            result = await self.crud.create(db=db, object=internal_data)
                        else:
                            item_data = self.create_schema(**form_data)
                            result = await self.crud.create(db=db, object=item_data)
                            await db.commit()

                        if result:
                            request.state.crud_result = result
                            if "HX-Request" in request.headers:
                                return RedirectResponse(
                                    url=f"/{self.admin_site.mount_path}/{self.model.__name__}/",
                                    headers={
                                        "HX-Redirect": f"/{self.admin_site.mount_path}/{self.model.__name__}/"
                                    },
                                )
                            return RedirectResponse(
                                url=f"/{self.admin_site.mount_path}/{self.model.__name__}/",
                                status_code=303,
                            )

                    except ValidationError as e:
                        field_errors = {
                            str(err["loc"][0]): err["msg"] for err in e.errors()
                        }
                        error_message = "Please correct the errors below."
                    except Exception as e:
                        error_message = str(e)

            except Exception as e:
                error_message = str(e)

            context = {
                "request": request,
                "model_name": self.model_key,
                "form_fields": form_fields,
                "error": error_message,
                "field_errors": field_errors,
                "field_values": field_values,
                "mount_path": self.admin_site.mount_path,
            }

            return self.templates.TemplateResponse(
                template, context, status_code=422 if error_message else 200
            )

        return cast(EndpointCallable, form_create_endpoint_inner)

    def bulk_delete_endpoint(self) -> EndpointCallable:
        @log_admin_action(EventType.DELETE, model=self.model)
        async def bulk_delete_endpoint_inner(
            request: Request,
            db: AsyncSession = Depends(self.session),
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
            current_user: dict = Depends(
                cast(Any, self.admin_site).admin_authentication.get_current_user()
            ),
            event_integration=Depends(lambda: self.event_integration),
        ) -> Response:
            """Handle bulk deletion of model instances using JSON list of IDs."""
            assert self.admin_site is not None
            try:
                body = await request.json()

                page_str = request.query_params.get("page", "1")
                rows_str = request.query_params.get("rows-per-page-select", "10")
                page = int(page_str)
                rows_per_page = int(rows_str)

                ids = body.get("ids", [])
                if not ids:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": [{"message": "No IDs provided for deletion"}]
                        },
                    )

                inspector = inspect(self.model)
                primary_key = inspector.primary_key[0]
                pk_name = primary_key.name
                pk_type = primary_key.type.python_type

                valid_ids: List[Union[int, str, float]] = []
                for id_value in ids:
                    try:
                        if pk_type == int:
                            valid_ids.append(int(id_value))
                        elif pk_type == str:
                            valid_ids.append(str(id_value))
                        elif pk_type == float:
                            valid_ids.append(float(id_value))
                        else:
                            valid_ids.append(id_value)
                    except (ValueError, TypeError):
                        return JSONResponse(
                            status_code=422,
                            content={
                                "detail": [{"message": f"Invalid ID value: {id_value}"}]
                            },
                        )

                filter_criteria: Dict[str, List[Union[int, str, float]]] = {
                    f"{pk_name}__in": valid_ids
                }
                records_to_delete = await self.crud.get_multi(
                    db=db, limit=len(valid_ids), **cast(Any, filter_criteria)
                )

                request.state.deleted_records = records_to_delete.get("data", [])

                try:
                    for id_value in valid_ids:
                        await self.crud.delete(db=db, **{pk_name: id_value})
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "detail": [{"message": f"Error during deletion: {str(e)}"}]
                        },
                    )

                total_count = await self.crud.count(db=db)
                max_page = (total_count + rows_per_page - 1) // rows_per_page
                adjusted_page = min(page, max(1, max_page))

                items_result = await self.crud.get_multi(
                    db=db,
                    offset=(adjusted_page - 1) * rows_per_page,
                    limit=rows_per_page,
                )

                items: Dict[str, Any] = {
                    "data": items_result.get("data", []),
                    "total_count": items_result.get("total_count", 0),
                }

                table_columns = [column.key for column in self.model.__table__.columns]
                primary_key_info = self.db_config.get_primary_key_info(self.model)

                context: Dict[str, Any] = {
                    "request": request,
                    "model_items": items["data"],
                    "model_name": self.model_key,
                    "table_columns": table_columns,
                    "total_items": items["total_count"],
                    "current_page": adjusted_page,
                    "rows_per_page": rows_per_page,
                    "primary_key_info": primary_key_info,
                    "mount_path": self.admin_site.mount_path,
                }

                return self.templates.TemplateResponse(
                    "admin/model/components/list_content.html", context
                )

            except ValueError as e:
                return JSONResponse(
                    status_code=422, content={"detail": [{"message": str(e)}]}
                )
            except Exception as e:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": [{"message": f"Error processing request: {str(e)}"}]
                    },
                )

        return cast(EndpointCallable, bulk_delete_endpoint_inner)

    def get_model_admin_page(
        self, template: str = "admin/model/list.html"
    ) -> EndpointCallable:
        async def get_model_admin_page_inner(
            request: Request, db: AsyncSession = Depends(self.session)
        ) -> Response:
            """Display the model list page, allowing pagination, sorting, and searching."""
            if template == "admin/model/list.html" and not request.url.path.endswith(
                "/"
            ):
                redirect_url = request.url.path + "/"
                if request.url.query:
                    redirect_url += "?" + request.url.query
                return RedirectResponse(redirect_url, status_code=307)

            try:
                page = max(1, int(request.query_params.get("page", "1")))
                rows_per_page = int(
                    request.query_params.get("rows-per-page-select", "10")
                )
            except ValueError:
                page = 1
                rows_per_page = 10

            sort_column = request.query_params.get("sort_by")
            sort_order = request.query_params.get("sort_order", "asc")

            sort_columns = (
                [sort_column] if sort_column and sort_column != "None" else None
            )
            sort_orders = [sort_order] if sort_order and sort_order != "None" else None

            search_column = request.query_params.get("column-to-search")
            search_value = request.query_params.get("search-input", "").strip()

            filter_criteria: Dict[str, Any] = {}
            if search_column and search_value:
                column = self.model.__table__.columns.get(search_column)
                if column is not None:
                    python_type = column.type.python_type
                    try:
                        if python_type == int:
                            filter_criteria[search_column] = int(search_value)
                        elif python_type == float:
                            filter_criteria[search_column] = float(search_value)
                        elif python_type == bool:
                            lower_search = search_value.lower()
                            if lower_search in ("true", "yes", "1", "t", "y"):
                                filter_criteria[search_column] = True
                            elif lower_search in ("false", "no", "0", "f", "n"):
                                filter_criteria[search_column] = False
                        elif python_type == str:
                            filter_criteria[
                                f"{search_column}__ilike"
                            ] = f"%{search_value}%"
                    except (ValueError, TypeError):
                        pass

            try:
                total_items = await self.crud.count(db=db, **cast(Any, filter_criteria))
                max_page = max(1, (total_items + rows_per_page - 1) // rows_per_page)
                page = min(page, max_page)
                offset = (page - 1) * rows_per_page

                items_result = await self.crud.get_multi(
                    db=db,
                    offset=offset,
                    limit=rows_per_page,
                    sort_columns=sort_columns,
                    sort_orders=sort_orders,
                    **cast(Any, filter_criteria),
                )

                items: Dict[str, Any] = {
                    "data": items_result.get("data", []),
                    "total_count": items_result.get("total_count", 0),
                }

            except Exception:
                items = {"data": [], "total_count": 0}
                total_items = 0
                page = 1

            table_columns = [column.key for column in self.model.__table__.columns]
            primary_key_info = self.db_config.get_primary_key_info(self.model)

            context: Dict[str, Any] = {
                "request": request,
                "model_items": items["data"],
                "model_name": self.model_key,
                "table_columns": table_columns,
                "total_items": items["total_count"],
                "current_page": page,
                "rows_per_page": rows_per_page,
                "selected_column": search_column,
                "primary_key_info": primary_key_info,
                "mount_path": self.admin_site.mount_path if self.admin_site else "",
                "sort_column": sort_column,
                "sort_order": sort_order,
                "allowed_actions": self.allowed_actions,
            }

            if "HX-Request" in request.headers:
                return self.templates.TemplateResponse(
                    "admin/model/components/list_content.html", context
                )

            if self.admin_site is not None:
                base_context = await self.admin_site.get_base_context(db)
                context.update(base_context)
                context["include_sidebar_and_header"] = True

            return self.templates.TemplateResponse(template, context)

        return cast(EndpointCallable, get_model_admin_page_inner)

    def get_model_create_page(
        self, template: str = "admin/model/create.html"
    ) -> EndpointCallable:
        async def model_create_page(request: Request) -> Response:
            """Show a blank form for creating a new record."""
            form_fields = _get_form_fields_from_schema(self.create_schema)
            mount_path = self.admin_site.mount_path if self.admin_site else ""
            return self.templates.TemplateResponse(
                template,
                {
                    "request": request,
                    "model_name": self.model_key,
                    "form_fields": form_fields,
                    "mount_path": mount_path,
                },
            )

        return cast(EndpointCallable, model_create_page)

    def get_model_update_page(self, template: str) -> EndpointCallable:
        async def get_model_update_page_inner(
            request: Request,
            id: int,
            db: AsyncSession = Depends(self.session),
        ) -> Response:
            """Show a form to update an existing record by `id`."""
            item = await self.crud.get(db=db, id=id)
            if not item:
                return JSONResponse(
                    status_code=404, content={"message": f"Item with id {id} not found"}
                )

            form_fields = _get_form_fields_from_schema(self.update_schema)
            for field in form_fields:
                field_name = field["name"]
                if field_name in item:
                    field["value"] = item[field_name]

            mount_path = self.admin_site.mount_path if self.admin_site else ""
            return self.templates.TemplateResponse(
                template,
                {
                    "request": request,
                    "model_name": self.model_key,
                    "form_fields": form_fields,
                    "mount_path": mount_path,
                    "id": id,
                },
            )

        return cast(EndpointCallable, get_model_update_page_inner)

    def form_update_endpoint(self) -> EndpointCallable:
        @log_admin_action(EventType.UPDATE, model=self.model)
        async def form_update_endpoint_inner(
            request: Request,
            db: AsyncSession = Depends(self.session),
            admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
            current_user: dict = Depends(
                cast(Any, self.admin_site).admin_authentication.get_current_user()
            ),
            event_integration=Depends(lambda: self.event_integration),
            id: Optional[int] = None,
        ) -> Response:
            """Handle POST form submission to update an existing record."""
            assert self.admin_site is not None

            if id is None:
                return JSONResponse(
                    status_code=422, content={"message": "No id parameter provided"}
                )

            item = await self.crud.get(db=db, id=id)
            if not item:
                return JSONResponse(
                    status_code=404, content={"message": f"Item with id {id} not found"}
                )

            form_fields = _get_form_fields_from_schema(self.update_schema)
            error_message: Optional[str] = None
            field_errors: Dict[str, str] = {}
            field_values: Dict[str, Any] = {}

            try:
                form_data = await request.form()
                update_data: Dict[str, Any] = {}
                has_updates = False

                for key, raw_val in form_data.items():
                    if isinstance(raw_val, UploadFile):
                        field_values[key] = raw_val
                        update_data[key] = raw_val
                        has_updates = True
                    elif isinstance(raw_val, str):
                        val_str = raw_val.strip()
                        if val_str:
                            update_data[key] = val_str
                            field_values[key] = val_str
                            has_updates = True

                if not has_updates:
                    error_message = "No changes were provided for update"
                else:
                    if self.update_internal_schema is not None and hasattr(
                        self.update_internal_schema, "__fields__"
                    ):
                        fields_dict = cast(
                            Dict[str, Any], self.update_internal_schema.__fields__
                        )
                        if "updated_at" in fields_dict:
                            update_data["updated_at"] = datetime.datetime.now(
                                timezone.utc
                            )

                    try:
                        if self.model.__name__ == "AdminUser":
                            if not self.user_service:
                                raise ValueError("No user_service available.")

                            update_schema_instance = self.update_schema(**update_data)

                            internal_update_data: Dict[str, Any] = {
                                "updated_at": datetime.datetime.now(timezone.utc)
                            }
                            username = getattr(update_schema_instance, "username", None)
                            if username is not None:
                                internal_update_data["username"] = username

                            password = getattr(update_schema_instance, "password", None)
                            if password is not None:
                                internal_update_data[
                                    "hashed_password"
                                ] = self.user_service.get_password_hash(password)

                            from ..admin_user.schemas import AdminUserUpdateInternal

                            internal_update_schema = AdminUserUpdateInternal(
                                **internal_update_data
                            )
                            await self.crud.update(
                                db=db, id=id, object=internal_update_schema
                            )
                        else:
                            update_schema_instance = self.update_schema(**update_data)
                            await self.crud.update(
                                db=db, id=id, object=update_schema_instance
                            )

                        return RedirectResponse(
                            url=f"/{self.admin_site.mount_path}/{self.model.__name__}/",
                            status_code=303,
                        )

                    except ValidationError as e:
                        field_errors = {
                            str(err["loc"][0]): err["msg"] for err in e.errors()
                        }
                        error_message = "Please correct the errors below."
                    except Exception as e:
                        error_message = str(e)

            except Exception as e:
                error_message = str(e)

            for field in form_fields:
                field_name = field["name"]
                if field_name not in field_values and field_name in item:
                    field_values[field_name] = item[field_name]

            context: Dict[str, Any] = {
                "request": request,
                "model_name": self.model_key,
                "form_fields": form_fields,
                "error": error_message,
                "field_errors": field_errors,
                "field_values": field_values,
                "mount_path": self.admin_site.mount_path,
                "id": id,
                "include_sidebar_and_header": False,
            }

            return self.templates.TemplateResponse(
                "admin/model/update.html",
                context,
                status_code=400 if error_message else 200,
            )

        return cast(EndpointCallable, form_update_endpoint_inner)

    def table_body_content(self) -> EndpointCallable:
        async def table_body_content_inner(
            request: Request,
            db: AsyncSession = Depends(self.session),
        ) -> Response:
            """Return HTMX partial for table content with pagination/search."""
            page_str = request.query_params.get("page", "1")
            limit_str = request.query_params.get("rows-per-page-select", "10")

            try:
                page = int(page_str)
                limit = int(limit_str)
            except ValueError:
                page = 1
                limit = 10

            offset = (page - 1) * limit
            search_column = request.query_params.get("column-to-search")
            search_value = request.query_params.get("search", "")

            filter_criteria: Dict[str, Any] = {}
            if search_column and search_value:
                filter_criteria[f"{search_column}__ilike"] = f"%{search_value}%"

            items_result = await self.crud.get_multi(
                db=db, offset=offset, limit=limit, **cast(Any, filter_criteria)
            )

            items: Dict[str, Any] = {
                "data": items_result.get("data", []),
                "total_count": items_result.get("total_count", 0),
            }

            total_items = items["total_count"]
            total_pages = (total_items + limit - 1) // limit

            return self.templates.TemplateResponse(
                "model/components/table_content.html",
                {
                    "request": request,
                    "model_items": items["data"],
                    "current_page": page,
                    "rows_per_page": limit,
                    "total_items": total_items,
                    "total_pages": total_pages,
                },
            )

        return cast(EndpointCallable, table_body_content_inner)
