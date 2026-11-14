"""Serve ignored personal assets only in DEBUG and only to loopback peers/hosts."""
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.http import Http404, HttpResponse
from django.template import Context, Engine
from django.views.decorators.http import require_GET


def _loopback(value):
    try:
        address = ipaddress.ip_address(value)
        mapped = getattr(address, "ipv4_mapped", None)
        return address.is_loopback or (mapped is not None and mapped.is_loopback)
    except ValueError:
        return False


@require_GET
def dev_test(request, asset="index.html"):
    host = urlsplit("//" + request.get_host()).hostname or ""
    if (not settings.DEBUG or not _loopback(request.META.get("REMOTE_ADDR", "")) or
            not (host.lower() == "localhost" or _loopback(host))):
        raise Http404
    types = {"index.html": "text/html; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
             "app.css": "text/css; charset=utf-8"}
    if asset not in types:
        raise Http404
    root = (Path(settings.BASE_DIR) / "local_dev").resolve()
    path = (root / asset).resolve()
    if path.parent != root or not path.is_file():
        raise Http404
    if asset == "index.html":
        template = Engine.get_default().from_string(path.read_text(encoding="utf-8"))
        body = template.render(Context({"database_name": settings.DATABASES["default"]["NAME"]}))
    else:
        body = path.read_bytes()
    response = HttpResponse(body, content_type=types[asset])
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Frame-Options"] = "DENY"
    response["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    return response
