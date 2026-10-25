import os
import secrets
import zipfile
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

from .dependencies.settings import settings

CSRF_COOKIE = "csrf_token"
MUTATING_GET_PREFIXES = (
    "/deleteUser/",
    "/promote/",
    "/demote/",
    "/return/",
    "/returnLoan/",
    "/delete_book/",
    "/deleteEbook/",
    "/deleteImage/",
    "/restoreBackup/",
    "/deleteBackup/",
    "/restoreFileBackup/",
    "/addByCSV/",
    "/deleteVkey/",
    "/updateDB",
    "/updateDBVersion",
)


def is_state_changing_get(path: str) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in MUTATING_GET_PREFIXES)


def contained_file(root: str, name: str) -> str | None:
    """Return a real path inside root, or None when name leaves that directory."""
    if not name or "\x00" in name or os.path.basename(name) != name:
        return None
    root_real = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(root_real, name))
    try:
        if os.path.commonpath([root_real, candidate]) != root_real:
            return None
    except ValueError:
        return None
    return candidate


def archive_stays_inside(archive_path: str, destination: str) -> bool:
    destination_real = os.path.realpath(destination)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                member = info.filename.replace("\\", "/")
                if not member or member.startswith("/") or ".." in Path(member).parts:
                    return False
                target = os.path.realpath(os.path.join(destination_real, member))
                if os.path.commonpath([destination_real, target]) != destination_real:
                    return False
    except (OSError, zipfile.BadZipFile):
        return False
    return True


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        request.state.csrf_token = token
        if not _csrf_ok(request, token):
            return PlainTextResponse("Solicitud rechazada", status_code=403)
        response = await call_next(request)
        if request.cookies.get(CSRF_COOKIE) != token:
            response.set_cookie(
                CSRF_COOKIE,
                token,
                httponly=False,
                samesite="lax",
                secure=settings.COOKIE_SECURE,
                path="/",
            )
        return response


async def _csrf_ok(request, token: str) -> bool:
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        supplied = request.headers.get("x-csrf-token")
        if supplied is None:
            content_type = request.headers.get("content-type", "")
            if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type or content_type == "":
                form = await request.form()
                supplied = form.get("csrf_token")
        return _same_token(supplied, token)
    if request.method == "GET" and is_state_changing_get(request.url.path):
        return _same_token(request.query_params.get("csrf_token"), token)
    return True


def _same_token(supplied, token: str) -> bool:
    if not supplied:
        return False
    candidate = str(supplied)
    if len(candidate) != len(token):
        return False
    return secrets.compare_digest(candidate, token)
