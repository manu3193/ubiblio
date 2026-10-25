from fastapi.templating import Jinja2Templates
from rich import print
from rich.console import Console

from ..vars import COOKIE_SECURE, SECRET_KEY, TOKEN_TTL, LANGUAGE

console = Console()


class Settings:
    SECRET_KEY = SECRET_KEY
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = TOKEN_TTL
    COOKIE_NAME = "access_token"
    COOKIE_SECURE = COOKIE_SECURE


settings = Settings()

language_templates = "templates/" + LANGUAGE
print(language_templates)
templates = Jinja2Templates(directory=language_templates)
_render_template = templates.TemplateResponse


def _render_with_csrf(request, name, context=None, **kwargs):
    context = {} if context is None else dict(context)
    context.setdefault("csrf_token", getattr(request.state, "csrf_token", ""))
    return _render_template(request, name, context, **kwargs)


templates.TemplateResponse = _render_with_csrf


def current_theme():
    from .. import crud
    return crud.library_theme()


templates.env.globals["current_theme"] = current_theme
