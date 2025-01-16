from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware


class AdminAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, admin_instance: 'CRUDAdmin'):
        super().__init__(app)
        self.admin_instance = admin_instance

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(f"/{self.admin_instance.mount_path}/"):
            is_login_path = request.url.path.endswith("/login")
            is_static_path = "/static/" in request.url.path
            
            if not (is_login_path or is_static_path):
                db = self.admin_instance.db_config.admin_session
                try:
                    access_token = request.cookies.get("access_token")
                    
                    if not access_token:
                        return RedirectResponse(
                            url=f"/{self.admin_instance.mount_path}/login?error=Please+log+in+to+access+this+page",
                            status_code=303
                        )
                    
                    token = access_token.split(' ')[1] if access_token.startswith('Bearer ') else access_token
                    
                    try:
                        token_data = await self.admin_instance.admin_authentication.verify_token(token, db)
                        if not token_data:
                            return RedirectResponse(
                                url=f"/{self.admin_instance.mount_path}/login?error=Session+expired",
                                status_code=303
                            )

                        if "@" in token_data.username_or_email:
                            user = await self.admin_instance.db_config.crud_users.get(
                                db=db, email=token_data.username_or_email
                            )
                        else:
                            user = await self.admin_instance.db_config.crud_users.get(
                                db=db, username=token_data.username_or_email
                            )

                        if not user:
                            return RedirectResponse(
                                url=f"/{self.admin_instance.mount_path}/login?error=User+not+found",
                                status_code=303
                            )
                        
                        response = await call_next(request)
                        return response
                        
                    except Exception as e:
                        if request.url.path.endswith('/crud') or '/crud/' in request.url.path:
                            raise
                        return RedirectResponse(
                            url=f"/{self.admin_instance.mount_path}/login?error=Authentication+error",
                            status_code=303
                        )
                    
                finally:
                    await db.commit()

        return await call_next(request)
