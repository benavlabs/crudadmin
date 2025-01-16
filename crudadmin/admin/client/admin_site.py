from datetime import timedelta
from typing import Optional

from fastapi import Request, APIRouter, Depends, Response, Cookie
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio.session import AsyncSession

from ...authentication.security import SecurityUtils
from ...authentication.admin_auth import AdminAuthentication
from ...db.database_config import DatabaseConfig


class AdminSite:
    def __init__(
        self,
        database_config: DatabaseConfig,
        templates_directory: str,
        models: dict,
        security_utils: SecurityUtils,
        admin_authentication: AdminAuthentication,
        mount_path: str,
        theme: str,
    ) -> None:
        self.db_config = database_config
        self.router = APIRouter()
        self.templates = Jinja2Templates(directory=templates_directory)
        self.models = models
        self.security_utils = security_utils
        self.admin_authentication = admin_authentication
        self.mount_path = mount_path
        self.theme = theme

    def setup_routes(self):
        self.router.add_api_route(
            "/login", self.login_page(), methods=["POST"], include_in_schema=False
        )
        self.router.add_api_route(
            "/logout",
            self.logout_endpoint(),
            methods=["get"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user())],
        )
        self.router.add_api_route(
            "/login", self.admin_login_page, methods=["GET"], include_in_schema=False
        )
        self.router.add_api_route(
            "/dashboard-content",
            self.dashboard_content(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user())],
        )
        self.router.add_api_route(
            "/",
            self.dashboard_page(),
            methods=["GET"],
            include_in_schema=False,
            dependencies=[Depends(self.admin_authentication.get_current_user())],
        )

        for model_key, auth_model_key in self.admin_authentication.auth_models.items():
            self.router.add_api_route(
                f"{auth_model_key}/",
                self.admin_auth_model_page(model_key),
                methods=["GET"],
                include_in_schema=False,
                dependencies=[Depends(self.admin_authentication.get_current_user())],
            )

    def login_page(self):
        async def login_page_inner(
            request: Request,
            response: Response,
            form_data: OAuth2PasswordRequestForm = Depends(),
            db: AsyncSession = Depends(self.db_config.get_admin_db),
        ):
            user = await self.security_utils.authenticate_user(
                form_data.username, form_data.password, db=db
            )
            if not user:
                return self.templates.TemplateResponse(
                    "auth/login.html",
                    {
                        "request": request,
                        "error": "Invalid credentials. Please try again.",
                        "mount_path": self.mount_path
                    },
                )

            access_token_expires = timedelta(
                minutes=self.security_utils.ACCESS_TOKEN_EXPIRE_MINUTES
            )
            access_token = await self.security_utils.create_access_token(
                data={"sub": user["username"]}, expires_delta=access_token_expires
            )

            response = RedirectResponse(
                url=f"/{self.mount_path}/",
                status_code=303
            )
            
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                max_age=access_token_expires.total_seconds(),
                path=f"/{self.mount_path}",
                samesite="lax"
            )
            
            return response

        return login_page_inner

    def logout_endpoint(self):
        async def logout_endpoint_inner(
            request: Request,
            response: Response,
            db: AsyncSession = Depends(self.db_config.get_admin_db),
            access_token: Optional[str] = Cookie(None),
            refresh_token: Optional[str] = Cookie(None)
        ):
            """Handle user logout by blacklisting both access and refresh tokens."""
            if access_token:
                token = access_token.replace('Bearer ', '') if access_token.startswith('Bearer ') else access_token
                await self.admin_authentication.blacklist_token(token, db)

            if refresh_token:
                await self.admin_authentication.blacklist_token(refresh_token, db)

            response = RedirectResponse(
                url=f"/{self.mount_path}/login",
                status_code=303
            )
            
            response.delete_cookie(
                key="access_token",
                path=f"/{self.mount_path}"
            )
            response.delete_cookie(
                key="refresh_token",
                path=f"/{self.mount_path}"
            )
            
            return response
    
        return logout_endpoint_inner

    async def admin_login_page(self, request: Request):
        return self.templates.TemplateResponse(
            "auth/login.html", 
            {
                "request": request,
                "mount_path": self.mount_path,
                "theme": self.theme
            }
        )

    def dashboard_content(self):
        async def dashboard_content_inner(request: Request, db: AsyncSession = Depends(self.db_config.session)):
            context = await self.get_base_context(db)
            context.update({
                "request": request,
            })
            return self.templates.TemplateResponse(
                "admin/dashboard/dashboard_content.html",
                context
            )
        
        return dashboard_content_inner
    
    async def get_base_context(self, db: AsyncSession) -> dict:
        """Get common context data needed for base template"""
        auth_model_counts = {}
        for model_name, model_data in self.admin_authentication.auth_models.items():
            crud = model_data["crud"]
            count = await crud.count(self.db_config.admin_session)
            auth_model_counts[model_name] = count

        model_counts = {}
        for model_name, model_data in self.models.items():
            crud = model_data["crud"]
            count = await crud.count(db)
            model_counts[model_name] = count

        return {
            "auth_table_names": self.admin_authentication.auth_models.keys(),
            "table_names": self.models.keys(),
            "auth_model_counts": auth_model_counts,
            "model_counts": model_counts,
            "mount_path": self.mount_path,
        }

    def dashboard_page(self):
        async def dashboard_page_inner(
            request: Request,
            db: AsyncSession = Depends(self.db_config.session)
        ):
            context = await self.get_base_context(db)
            context.update({
                "request": request,
                "include_sidebar_and_header": True
            })
            
            return self.templates.TemplateResponse(
                "admin/dashboard/dashboard.html",
                context
            )
        return dashboard_page_inner

    def admin_auth_model_page(self, model_key: str):
        async def admin_auth_model_page_inner(
                request: Request,
                admin_db: AsyncSession = Depends(self.db_config.get_admin_db),
                db: AsyncSession = Depends(self.db_config.session)
        ):
            auth_model = self.admin_authentication.auth_models[model_key]
            table_columns = [column.key for column in auth_model["model"].__table__.columns]

            page = int(request.query_params.get("page", 1))
            limit = int(request.query_params.get("rows-per-page-select", 10))
            offset = (page - 1) * limit

            items = await auth_model["crud"].get_multi(db=admin_db, offset=offset, limit=limit)
            total_items = items["total_count"]
            total_pages = (total_items + limit - 1) // limit

            context = await self.get_base_context(db)
            context.update({
                "request": request,
                "model_items": items["data"],
                "model_name": model_key,
                "table_columns": table_columns,
                "current_page": page,
                "rows_per_page": limit,
                "total_items": total_items,
                "total_pages": total_pages,
                "include_sidebar_and_header": True
            })

            return self.templates.TemplateResponse(
                "admin/model/list.html",
                context
            )
        
        return admin_auth_model_page_inner
