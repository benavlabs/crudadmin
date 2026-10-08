from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class AdminPaths:
    """Every URL the admin builds, derived once from its mount path.

    ``prefix`` is ``""`` for an admin mounted at the root and ``"/admin"`` (say)
    otherwise; all other URLs are built from it, so no code concatenates the
    prefix by hand.

    Example:
        ```python
        paths = AdminPaths.for_mount_segment("admin")
        assert paths.login == "/admin/login"
        assert paths.model("User") == "/admin/User/"
        ```
    """

    prefix: str

    @classmethod
    def for_mount_segment(cls, segment: str) -> "AdminPaths":
        """Paths for a mount path already stripped of slashes (``""`` for the root)."""
        return cls(prefix=f"/{segment}" if segment else "")

    @property
    def home(self) -> str:
        return f"{self.prefix}/"

    @property
    def login(self) -> str:
        return f"{self.prefix}/login"

    @property
    def logout(self) -> str:
        return f"{self.prefix}/logout"

    @property
    def static(self) -> str:
        return f"{self.prefix}/static/"

    @property
    def cookie_path(self) -> str:
        return f"{self.prefix}/"

    def sudo(self, next_path: str) -> str:
        return f"{self.prefix}/sudo?next={quote(next_path, safe='/')}"

    def model(self, model_name: str) -> str:
        return f"{self.prefix}/{model_name}/"

    def login_with_error(self, error_code: str) -> str:
        return f"{self.login}?error={error_code}"

    def is_public(self, request_path: str) -> bool:
        """Whether a request path is served without a login: the login page and static files."""
        return request_path.rstrip("/") == self.login or request_path.startswith(
            self.static
        )
