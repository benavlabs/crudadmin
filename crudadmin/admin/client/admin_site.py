from datetime import timedelta

from fastapi import Request, APIRouter, Depends, Response
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio.session import AsyncSession

from ...authentication.security import SecurityUtils
from ...authentication.admin_auth import AdminAuthentication
from ...db.database_config import DatabaseConfig

router = APIRouter(tags=["admin"])


class AdminSite:
    def __init__(
        self,
        database_config: DatabaseConfig,
        templates_directory: str,
        models: dict,
        security_utils: SecurityUtils,
        admin_authentication: AdminAuthentication,
        theme: str = "dark-theme",
    ) -> None:
        self.db_config = database_config
        self.router = APIRouter(prefix="/admin")
        self.templates = Jinja2Templates(directory=templates_directory)
        self.models = models
        self.security_utils = security_utils
        self.admin_authentication = admin_authentication
        self.theme = theme

    def setup_routes(self):
        self.router.add_api_route(
            "/login", self.login_page(), methods=["POST"], include_in_schema=False
        )
        self.router.add_api_route(
            "/logout", self.logout_endpoint, methods=["get"], include_in_schema=False
        )
        self.router.add_api_route(
            "/login", self.admin_login_page, methods=["GET"], include_in_schema=False
        )
        self.router.add_api_route(
            "/dashboard-content",
            self.dashboard_content,
            methods=["GET"],
            include_in_schema=False,
        )
        self.router.add_api_route(
            "/", self.dashboard_page, methods=["GET"], include_in_schema=False
        )

        for model_key, auth_model_key in self.admin_authentication.auth_models.items():
            self.router.add_api_route(
                f"/{auth_model_key}",
                self.admin_auth_model_page(model_key),
                methods=["GET"],
                include_in_schema=False,
            )

    def login_page(self):
        async def login_page_inner(
            request: Request,
            response: Response,
            form_data: OAuth2PasswordRequestForm = Depends(),
            db: AsyncSession = Depends(self.db_config.session),
        ):
            user = await self.security_utils.authenticate_user(
                form_data.username, form_data.password, db=db
            )
            if not user:
                return self.templates.TemplateResponse(
                    "login_page.html",
                    {
                        "request": request,
                        "error": "Invalid credentials. Please try again.",
                    },
                )

            access_token_expires = timedelta(
                minutes=self.security_utils.ACCESS_TOKEN_EXPIRE_MINUTES
            )
            access_token = await self.security_utils.create_access_token(
                data={"sub": user["username"]}, expires_delta=access_token_expires
            )

            refresh_token_expires = timedelta(
                days=self.security_utils.REFRESH_TOKEN_EXPIRE_DAYS
            )
            refresh_token = await self.security_utils.create_refresh_token(
                data={"sub": user["username"]}, expires_delta=refresh_token_expires
            )

            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=False,
                samesite="Lax",
                max_age=int(refresh_token_expires.total_seconds()),
            )

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "redirect": "/admin/",
            }

        return login_page_inner

    async def logout_endpoint(self, response: Response):
        response.delete_cookie(key="refresh_token")
        await self.admin_authentication.blacklist_token()
        return RedirectResponse(url="/admin/login")

    async def admin_login_page(self, request: Request):
        return self.templates.TemplateResponse("login_page.html", {"request": request})

    async def dashboard_content(self, request: Request):
        return self.templates.TemplateResponse(
            "dashboard_content.html",
            {
                "request": request,
                "table_names": self.models.keys(),
                "auth_table_names": self.admin_authentication.auth_models.keys(),
            },
        )

    async def dashboard_page(self, request: Request):
        return self.templates.TemplateResponse(
            "dashboard_page.html", {"request": request}
        )

    def admin_auth_model_page(self, model_key: str):
        async def admin_auth_model_page_inner(
                request: Request,
                db: AsyncSession = Depends(self.db_config.session)
        ):
            auth_model = self.admin_authentication.auth_models[model_key]
            table_columns = [column.key for column in auth_model["model"].__table__.columns]

            page = int(request.query_params.get("page", 1))
            limit = int(request.query_params.get("rows-per-page-select", 10))
            offset = (page - 1) * limit

            items = await auth_model["crud"].get_multi(db=db, offset=offset, limit=limit)
            total_items = items["total_count"]
            total_pages = (total_items + limit - 1) // limit

            return self.templates.TemplateResponse(
                "admin_model_page.html",
                {
                    "request": request,
                    "model_items": items["data"],
                    "model_name": model_key,
                    "table_columns": table_columns,
                    "current_page": page,
                    "rows_per_page": limit,
                    "total_items": total_items,
                    "total_pages": total_pages,
                },
            )
        
        return admin_auth_model_page_inner
