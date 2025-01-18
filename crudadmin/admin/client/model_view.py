from typing import TypeVar, Type, List
import datetime
from datetime import timezone

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import inspect
from fastcrud import FastCRUD, EndpointCreator

from ...db.database_config import DatabaseConfig
from ..helper import _get_form_fields_from_schema

ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
UpdateSchemaInternalType = TypeVar("UpdateSchemaInternalType", bound=BaseModel)
DeleteSchemaType = TypeVar("DeleteSchemaType", bound=BaseModel)
SelectSchemaType = TypeVar("SelectSchemaType", bound=BaseModel)


class BulkDeleteRequest(BaseModel):
    ids: List[int]


class ModelView:
    def __init__(
        self,
        database_config: DatabaseConfig,
        templates: Jinja2Templates,
        model: DeclarativeBase,
        create_schema: Type[CreateSchemaType],
        update_schema: Type[UpdateSchemaType],
        update_internal_schema: Type[UpdateSchemaInternalType] | None = None,
        delete_schema: Type[DeleteSchemaType] | None = None,
        select_schema: Type[SelectSchemaType] | None = None,
        admin_model: bool = False,
        admin_site = None,
    ) -> None:
        self.db_config = database_config
        if self._model_is_admin_model(model):
            self.session = self.db_config.get_admin_db
        else:
            self.session = database_config.session
        self.templates = templates
        self.model = model
        self.model_key = model.__name__
        self.router = APIRouter()
        self.create_schema = create_schema
        self.update_schema = update_schema
        self.update_internal_schema = update_internal_schema
        self.delete_schema = delete_schema
        self.admin_model = admin_model
        self.admin_site = admin_site

        CRUDModel = FastCRUD[
            model, create_schema, update_schema, update_internal_schema, delete_schema, select_schema
        ]
        self.crud = CRUDModel(model)

        self.endpoints_template = EndpointCreator(
            session=self.session,
            model=model,
            crud=self.crud,
            create_schema=create_schema,
            update_schema=update_schema,
            delete_schema=delete_schema,
        )
        self.endpoints_template.add_routes_to_router()
        self.router.include_router(self.endpoints_template.router, prefix="/crud")

        self.setup_routes()

    def setup_routes(self):
        self.router.add_api_route(
            "/form_create", 
            self.form_create_endpoint(template="admin/model/create.html"),
            methods=["POST"], 
            include_in_schema=False
        )
        self.router.add_api_route(
            "/", self.get_model_admin_page(), methods=["GET"], include_in_schema=False
        )
        self.router.add_api_route(
            "/create_page", 
            self.get_model_create_page(template="admin/model/create.html"), 
            methods=["GET"], 
            include_in_schema=False
        )
        self.router.add_api_route(
            "/get_model_list",
            self.get_model_admin_page(template="admin/model/components/list_content.html"),
            methods=["GET"],
            include_in_schema=False,
        )
        
        self.router.add_api_route(
            "/bulk-delete",
            self.bulk_delete_endpoint(),
            methods=["DELETE"],
            include_in_schema=False,
        )
        
        self.router.add_api_route(
            "/update/{id}",
            self.get_model_update_page(template="admin/model/update.html"),
            methods=["GET"],
            include_in_schema=False,
        )
        self.router.add_api_route(
            "/form_update/{id}",
            self.form_update_endpoint(),
            methods=["POST"],
            include_in_schema=False,
        )

    def _model_is_admin_model(self, model: DeclarativeBase) -> bool:
        """Determine if a model is an admin model."""
        admin_models = {
            self.db_config.AdminUser.__name__,
            self.db_config.AdminTokenBlacklist.__name__,
            self.db_config.AdminSession.__name__,
        }
        return model.__name__ in admin_models

    def form_create_endpoint(self, template: str):
        async def form_create_endpoint_inner(
            request: Request,
            db: AsyncSession = Depends(self.session)
        ):
            form_fields = _get_form_fields_from_schema(self.create_schema)
            error_message = None
            field_errors = {}
            field_values = {}

            try:
                if request.method == "POST":
                    form_data_raw = await request.form()
                    form_data = {}

                    for field in form_fields:
                        key = field["name"]
                        raw_value = form_data_raw.getlist(key)
                        if len(raw_value) == 1:
                            value = raw_value[0]
                            form_data[key] = value if value else field.get("default", None)
                            field_values[key] = value
                        elif len(raw_value) > 1:
                            form_data[key] = raw_value
                            field_values[key] = raw_value
                        else:
                            form_data[key] = field.get("default", None)

                    try:
                        if self.model.__name__ == "AdminUser":
                            item_data = self.create_schema(**form_data)
                            
                            hashed_password = self.admin_site.security_utils.get_password_hash(
                                item_data.password
                            )
                            
                            from ...schemas.admin_user import AdminUserCreateInternal
                            internal_data = AdminUserCreateInternal(
                                username=item_data.username,
                                hashed_password=hashed_password
                            )
                            result = await self.crud.create(db=db, object=internal_data)
                        else:
                            item_data = self.create_schema(**form_data)
                            result = await self.crud.create(db=db, object=item_data)

                        if result:
                            if "HX-Request" in request.headers:
                                return RedirectResponse(
                                    url=f"/{self.admin_site.mount_path}/{self.model.__name__}/",
                                    headers={"HX-Redirect": f"/{self.admin_site.mount_path}/{self.model.__name__}/"}
                                )
                            return RedirectResponse(
                                url=f"/{self.admin_site.mount_path}/{self.model.__name__}/",
                                status_code=303
                            )

                    except ValidationError as e:
                        field_errors = {error["loc"][0]: error["msg"] for error in e.errors()}
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
                template,
                context,
                status_code=422 if error_message else 200
            )

        return form_create_endpoint_inner
    
    def bulk_delete_endpoint(self):
        async def bulk_delete_endpoint_inner(
            request: Request,
            db: AsyncSession = Depends(self.session)
        ):
            try:
                body = await request.json()
                
                page = int(request.query_params.get('page', '1'))
                rows_per_page = int(request.query_params.get('rows-per-page-select', '10'))
                
                ids = body.get('ids', [])
                if not ids:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": [{"message": "No IDs provided for deletion"}]}
                    )

                inspector = inspect(self.model)
                primary_key = inspector.primary_key[0]
                pk_name = primary_key.name
                pk_type = primary_key.type.python_type

                valid_ids = []
                for id_value in ids:
                    try:
                        if pk_type == int:
                            validated_id = int(id_value)
                        elif pk_type == str:
                            validated_id = str(id_value)
                        elif pk_type == float:
                            validated_id = float(id_value)
                        else:
                            validated_id = id_value
                        valid_ids.append(validated_id)
                    except (ValueError, TypeError):
                        return JSONResponse(
                            status_code=422,
                            content={"detail": [{"message": f"Invalid ID value: {id_value}"}]}
                        )

                try:
                    for id_value in valid_ids:
                        await self.crud.delete(db=db, **{pk_name: id_value})
                    await db.commit()
                except Exception as e:
                    await db.rollback()
                    return JSONResponse(
                        status_code=400,
                        content={"detail": [{"message": f"Error during deletion: {str(e)}"}]}
                    )

                total_count = await self.crud.count(db=db)
                max_page = (total_count + rows_per_page - 1) // rows_per_page
                adjusted_page = min(page, max(1, max_page))

                filter_criteria = {}
                items = await self.crud.get_multi(
                    db=db,
                    offset=(adjusted_page - 1) * rows_per_page,
                    limit=rows_per_page,
                    **filter_criteria
                )

                table_columns = [column.key for column in self.model.__table__.columns]
                primary_key_info = self.db_config.get_primary_key_info(self.model)

                context = {
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
                    "admin/model/components/list_content.html",
                    context
                )

            except ValueError as e:
                return JSONResponse(
                    status_code=422,
                    content={"detail": [{"message": str(e)}]}
                )
            except Exception as e:
                return JSONResponse(
                    status_code=422,
                    content={"detail": [{"message": f"Error processing request: {str(e)}"}]}
                )

        return bulk_delete_endpoint_inner

    def get_model_admin_page(self, template: str = "admin/model/list.html"):
        async def get_model_admin_page_inner(
            request: Request, 
            db: AsyncSession = Depends(self.session)
        ):
            if template == "admin/model/list.html" and not request.url.path.endswith('/'):
                redirect_url = request.url.path + '/'
                if request.url.query:
                    redirect_url += '?' + request.url.query
                return RedirectResponse(redirect_url, status_code=307)

            try:
                page = max(1, int(request.query_params.get("page", 1)))
                rows_per_page = int(request.query_params.get("rows-per-page-select", 10))
            except ValueError:
                page = 1
                rows_per_page = 10

            sort_column = request.query_params.get("sort_by")
            sort_order = request.query_params.get("sort_order", "asc")

            sort_columns = [sort_column] if sort_column and sort_column != "None" else None
            sort_orders = [sort_order] if sort_column and sort_column != "None" else None

            search_column = request.query_params.get("column-to-search")
            search_value = request.query_params.get("search-input", "").strip()

            filter_criteria = {}
            if search_column and search_value:
                column = self.model.__table__.columns.get(search_column)
                if column is not None:
                    python_type = column.type.python_type
                    if python_type in (int, float):
                        try:
                            if python_type == int:
                                filter_criteria[search_column] = int(search_value)
                            else:
                                filter_criteria[search_column] = float(search_value)
                        except ValueError:
                            pass
                    elif python_type == bool:
                        lower_search = search_value.lower()
                        if lower_search in ('true', 'yes', '1', 't', 'y'):
                            filter_criteria[search_column] = True
                        elif lower_search in ('false', 'no', '0', 'f', 'n'):
                            filter_criteria[search_column] = False
                    elif python_type == str:
                        filter_criteria[f"{search_column}__ilike"] = f"%{search_value}%"

            try:
                total_items = await self.crud.count(db=db, **filter_criteria)

                max_page = max(1, (total_items + rows_per_page - 1) // rows_per_page)
                page = min(page, max_page)

                offset = (page - 1) * rows_per_page

                items = await self.crud.get_multi(
                    db=db, 
                    offset=offset,
                    limit=rows_per_page,
                    sort_columns=sort_columns,
                    sort_orders=sort_orders,
                    **filter_criteria
                )
            except Exception as e:
                items = {"data": [], "total_count": 0}
                total_items = 0
                page = 1

            table_columns = [column.key for column in self.model.__table__.columns]
            primary_key_info = self.db_config.get_primary_key_info(self.model)

            context = {
                "request": request,
                "model_items": items["data"],
                "model_name": self.model_key,
                "table_columns": table_columns,
                "total_items": total_items,
                "current_page": page,
                "rows_per_page": rows_per_page,
                "selected_column": search_column,
                "primary_key_info": primary_key_info,
                "mount_path": self.admin_site.mount_path,
                "sort_column": sort_column,
                "sort_order": sort_order,
            }

            if "HX-Request" in request.headers:
                return self.templates.TemplateResponse(
                    "admin/model/components/list_content.html",
                    context
                )

            context.update(await self.admin_site.get_base_context(db))
            context["include_sidebar_and_header"] = True
            return self.templates.TemplateResponse(template, context)

        return get_model_admin_page_inner
    
    def get_model_create_page(self, template: str = "admin/model/create.html"):
        async def model_create_page(request: Request):
            form_fields = _get_form_fields_from_schema(self.create_schema)
            return self.templates.TemplateResponse(
                template,
                {
                    "request": request,
                    "model_name": self.model_key,
                    "form_fields": form_fields,
                    "mount_path": self.admin_site.mount_path,
                },
            )
        return model_create_page
    
    def get_model_update_page(self, template: str):
        async def get_model_update_page_inner(
            request: Request,
            id: int,
            db: AsyncSession = Depends(self.session)
        ):
            item = await self.crud.get(db=db, id=id)
            if not item:
                return JSONResponse(
                    status_code=404,
                    content={"message": f"Item with id {id} not found"}
                )
            
            form_fields = _get_form_fields_from_schema(self.update_schema)
            
            for field in form_fields:
                field_name = field["name"]
                if field_name in item:
                    field["value"] = item[field_name]
            
            return self.templates.TemplateResponse(
                template,
                {
                    "request": request,
                    "model_name": self.model_key,
                    "form_fields": form_fields,
                    "mount_path": self.admin_site.mount_path,
                    "id": id
                },
            )
        
        return get_model_update_page_inner
    
    def form_update_endpoint(self):
        async def form_update_endpoint_inner(
            request: Request,
            id: int,
            db: AsyncSession = Depends(self.session)
        ):
            item = await self.crud.get(db=db, id=id)
            if not item:
                return JSONResponse(
                    status_code=404,
                    content={"message": f"Item with id {id} not found"}
                )
            
            form_fields = _get_form_fields_from_schema(self.update_schema)
            error_message = None
            field_errors = {}
            field_values = {}
            
            try:
                form_data = await request.form()
                update_data = {}
                has_updates = False
                
                for key, value in form_data.items():
                    if value and value.strip():
                        update_data[key] = value.strip()
                        field_values[key] = value.strip()
                        has_updates = True

                if not has_updates:
                    error_message = "No changes were provided for update"
                else:
                    if hasattr(self.update_internal_schema, "updated_at"):
                        update_data["updated_at"] = datetime.now(timezone.utc)
                    
                    try:
                        if self.model.__name__ == "AdminUser":
                            update_schema_instance = self.update_schema(**update_data)
                            internal_update_data = {"updated_at": datetime.now(timezone.utc)}
                            
                            if update_schema_instance.username is not None:
                                internal_update_data["username"] = update_schema_instance.username
                                
                            if update_schema_instance.password is not None:
                                internal_update_data["hashed_password"] = self.admin_site.security_utils.get_password_hash(
                                    update_schema_instance.password
                                )
                            
                            from ...schemas.admin_user import AdminUserUpdateInternal
                            internal_update_schema = AdminUserUpdateInternal(**internal_update_data)
                            await self.crud.update(db=db, id=id, object=internal_update_schema)
                        else:
                            update_schema_instance = self.update_schema(**update_data)
                            await self.crud.update(
                                db=db,
                                id=id,
                                object=update_schema_instance
                            )
                        
                        return RedirectResponse(
                            url=f"/{self.admin_site.mount_path}/{self.model.__name__}/",
                            status_code=303
                        )
                        
                    except ValidationError as e:
                        field_errors = {error["loc"][0]: error["msg"] for error in e.errors()}
                        error_message = "Please correct the errors below."
                    except Exception as e:
                        error_message = str(e)
                
            except Exception as e:
                error_message = str(e)

            for field in form_fields:
                field_name = field["name"]
                if field_name not in field_values:
                    if field_name in item:
                        field_values[field_name] = item[field_name]
            
            context = {
                "request": request,
                "model_name": self.model_key,
                "form_fields": form_fields,
                "error": error_message,
                "field_errors": field_errors,
                "field_values": field_values,
                "mount_path": self.admin_site.mount_path,
                "id": id,
                "include_sidebar_and_header": False
            }
            
            return self.templates.TemplateResponse(
                "admin/model/update.html",
                context,
                status_code=400 if error_message else 200
            )
        
        return form_update_endpoint_inner

    def table_body_content(self):
        async def table_body_content_inner(
            request: Request, db: AsyncSession = Depends(self.session)
        ):
            page = int(request.query_params.get("page", 1))
            limit = int(request.query_params.get("rows-per-page-select", 10))
            offset = (page - 1) * limit

            search_column = request.query_params.get("column-to-search")
            search_value = request.query_params.get("search", "")

            if search_column and search_value:
                filter_criteria = {f"{search_column}__ilike": f"%{search_value}%"}
                items = await self.crud.get_multi(db=db, offset=offset, limit=limit, **filter_criteria)
            else:
                items = await self.crud.get_multi(db=db, offset=offset, limit=limit)

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

        return table_body_content_inner
