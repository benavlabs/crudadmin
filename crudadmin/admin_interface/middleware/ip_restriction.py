import logging
from ipaddress import ip_address, ip_network
from typing import List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class IPRestrictionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        allowed_ips: Optional[List[str]] = None,
        allowed_networks: Optional[List[str]] = None,
    ) -> None:
        """
        Middleware to restrict access based on client IP addresses and networks.

        Args:
            app (ASGIApp): The FastAPI application instance.
            allowed_ips (Optional[List[str]]): List of allowed individual IP addresses.
            allowed_networks (Optional[List[str]]): List of allowed IP networks in CIDR notation.
        """
        super().__init__(app)
        self.allowed_ips = set()
        self.allowed_networks = set()

        if allowed_ips:
            for ip in allowed_ips:
                try:
                    self.allowed_ips.add(str(ip_address(ip)))
                except ValueError:
                    logger.error(f"Invalid IP address provided: {ip}")
                    pass

        if allowed_networks:
            for network in allowed_networks:
                try:
                    self.allowed_networks.add(ip_network(network))
                except ValueError:
                    logger.error(f"Invalid IP network provided: {network}")
                    pass

    async def dispatch(self, request: Request, call_next):
        """
        Process incoming requests and restrict access based on IP.

        Args:
            request (Request): The incoming HTTP request.
            call_next (Callable): The next ASGI application to call.

        Returns:
            Response: The HTTP response.
        """
        client = request.client
        if client is None:
            logger.warning("Request client is None. Unable to determine client IP.")
            return JSONResponse(
                status_code=400, content={"detail": "Unable to determine client IP."}
            )
        client_ip = client.host

        if not request.url.path.startswith("/admin"):
            return await call_next(request)

        try:
            ip = ip_address(client_ip)

            if str(ip) in self.allowed_ips:
                return await call_next(request)

            for network in self.allowed_networks:
                if ip in network:
                    return await call_next(request)

            logger.warning(f"Access denied for IP: {client_ip}")
            return JSONResponse(
                status_code=403, content={"detail": "Access denied: IP not allowed."}
            )

        except ValueError:
            logger.error(f"Invalid IP address encountered: {client_ip}")
            return JSONResponse(
                status_code=400, content={"detail": "Invalid IP address."}
            )
