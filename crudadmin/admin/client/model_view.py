from typing import TypeVar, Type

from httpx import AsyncClient, RequestError
from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError
from fastcrud import FastCRUD, EndpointCreator

from ...db.database_config import DatabaseConfig
from ..helper import _get_form_fields_from_schema

ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
UpdateSchemaInternalType = TypeVar("UpdateSchemaInternalType", bound=BaseModel)
DeleteSchemaType = TypeVar("DeleteSchemaType", bound=BaseModel)
SelectSchemaType = TypeVar("SelectSchemaType", bound=BaseModel)


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
            session=self.db_config.session,
            model=model,
            crud=self.crud,
            create_schema=create_schema,
            update_schema=update_schema,
            delete_schema=delete_schema,
        )
        self.endpoints_template.add_routes_to_router()
        self.router.include_router(self.endpoints_template.router, prefix="/crud")

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
            "/get_table",
            self.table_body_content(),
            methods=["GET"],
            include_in_schema=False,
        )
        self.router.add_api_route(
            "/get_model_list",
            self.get_model_admin_page(template="admin/model/components/list_content.html"),
            methods=["GET"],
            include_in_schema=False,
        )

    def form_create_endpoint(self, template: str):
        async def form_create_endpoint_inner(
            request: Request,
            db: AsyncSession = Depends(self.session)
        ):
            form_fields = _get_form_fields_from_schema(self.create_schema)
            try:
                form_data_raw = await request.form()
                form_data = {}

                for field in form_fields:
                    key = field["name"]
                    raw_value = form_data_raw.getlist(key)
                    if len(raw_value) == 1:
                        value = raw_value[0]
                        form_data[key] = value if value else field.get("default", None)
                    elif len(raw_value) > 1:
                        form_data[key] = raw_value
                    else:
                        form_data[key] = field.get("default", None)

                item_data = self.create_schema(**form_data)
                
                result = await self.crud.create(db=db, object=item_data)

                if result:
                    return RedirectResponse(url=f"/admin/{self.model.__name__}", status_code=303)
                else:
                    error_message = "Failed to create item"
            
            except SQLAlchemyError as e:
                error_message = f"A database error occurred: {e}"

            except Exception as e:
                error_message = f"An unexpected error occurred: {e}"

            return self.templates.TemplateResponse(
                        template,
                        {
                            "request": request,
                            "model_name": self.model_key,
                            "form_fields": form_fields,
                            "error": error_message
                        }
                    )

        return form_create_endpoint_inner

    def get_model_admin_page(self, template: str = "admin/model/list.html"):
        async def get_model_admin_page_inner(
            request: Request, 
            db: AsyncSession = Depends(self.session)
        ):
            page = int(request.query_params.get("page", 1))
            limit = int(request.query_params.get("rows-per-page-select", 10))
            offset = (page - 1) * limit

            items = await self.crud.get_multi(db=db, offset=offset, limit=limit)
            table_columns = [column.key for column in self.model.__table__.columns]

            context = await self.admin_site.get_base_context(db)
            
            context.update({
                "request": request,
                "model_items": items["data"],
                "model_name": self.model_key,
                "table_columns": table_columns,
                "total_items": items["total_count"],
                "current_page": page,
                "rows_per_page": limit,
                "include_sidebar_and_header": True
            })

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
                },
            )
        return model_create_page

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
