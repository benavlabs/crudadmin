from typing import List, Optional
from ipaddress import ip_address, ip_network
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse


class IPRestrictionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        allowed_ips: Optional[List[str]] = None,
        allowed_networks: Optional[List[str]] = None,
    ):
        super().__init__(app)
        self.allowed_ips = set()
        self.allowed_networks = set()

        if allowed_ips:
            for ip in allowed_ips:
                try:
                    self.allowed_ips.add(str(ip_address(ip)))
                except ValueError:
                    pass

        if allowed_networks:
            for network in allowed_networks:
                try:
                    self.allowed_networks.add(ip_network(network))
                except ValueError:
                    pass

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host

        if not request.url.path.startswith("/admin"):
            return await call_next(request)

        try:
            ip = ip_address(client_ip)

            if str(ip) in self.allowed_ips:
                return await call_next(request)

            for network in self.allowed_networks:
                if ip in network:
                    return await call_next(request)

            return JSONResponse(
                status_code=403, content={"detail": "Access denied: IP not allowed"}
            )

        except ValueError:
            return JSONResponse(
                status_code=400, content={"detail": "Invalid IP address"}
            )
