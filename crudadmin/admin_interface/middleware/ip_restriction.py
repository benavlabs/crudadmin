import logging
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Optional, Union

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


class IPRestrictionMiddleware:
    """Refuse requests from clients outside the allowed addresses and networks.

    Every request is checked: the middleware is installed on the admin app, so it
    only ever sees admin requests, whatever the mount path. Other scopes, such as
    lifespan, pass through.

    Args:
        app: The admin app.
        allowed_ips: Individual addresses allowed in. Invalid ones are logged and
            skipped.
        allowed_networks: Networks in CIDR notation allowed in. Invalid ones are
            logged and skipped.
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_ips: Optional[list[str]] = None,
        allowed_networks: Optional[list[str]] = None,
    ) -> None:
        self.app = app
        self.allowed_ips: set[str] = set()
        self.allowed_networks: set[Union[IPv4Network, IPv6Network]] = set()

        for ip in allowed_ips or []:
            try:
                self.allowed_ips.add(str(ip_address(ip)))
            except ValueError:
                logger.error("Invalid IP address provided: %s", ip)

        for network in allowed_networks or []:
            try:
                self.allowed_networks.add(ip_network(network))
            except ValueError:
                logger.error("Invalid IP network provided: %s", network)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        refusal = self._refusal(scope.get("client"))
        if refusal is not None:
            await refusal(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def _refusal(self, client: Optional[tuple[str, int]]) -> Optional[JSONResponse]:
        """The response refusing this client, or None when it is allowed in."""
        if client is None:
            logger.warning("Request client is None. Unable to determine client IP.")
            return JSONResponse(
                status_code=400, content={"detail": "Unable to determine client IP."}
            )
        client_ip = client[0]
        try:
            ip = ip_address(client_ip)
        except ValueError:
            logger.error("Invalid IP address encountered: %s", client_ip)
            return JSONResponse(
                status_code=400, content={"detail": "Invalid IP address."}
            )

        if str(ip) in self.allowed_ips or any(
            ip in network for network in self.allowed_networks
        ):
            return None

        logger.warning("Access denied for IP: %s", client_ip)
        return JSONResponse(
            status_code=403, content={"detail": "Access denied: IP not allowed."}
        )
