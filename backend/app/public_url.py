from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Request

from .config import get_settings


@dataclass(frozen=True)
class PublicEndpoint:
    base_url: str
    host: str
    authority: str
    port: int
    security: str


def _first_header(value: str | None) -> str:
    return (value or "").split(",", 1)[0].strip()


def public_base_url(request: Request) -> str:
    settings = get_settings()
    if settings.public_url and settings.public_url.lower() != "auto":
        return public_endpoint(settings.public_url).base_url

    scheme = request.url.scheme
    authority = request.headers.get("host", request.url.netloc)
    if settings.trust_proxy_headers:
        scheme = _first_header(request.headers.get("x-forwarded-proto")) or scheme
        authority = _first_header(request.headers.get("x-forwarded-host")) or authority

    return public_endpoint(f"{scheme}://{authority}").base_url


def public_endpoint(base_url: str) -> PublicEndpoint:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Public URL must be an absolute HTTP(S) URL")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    default_port = 443 if parsed.scheme == "https" else 80
    host = parsed.hostname
    display_host = f"[{host}]" if ":" in host else host
    authority = display_host if port == default_port else f"{display_host}:{port}"
    return PublicEndpoint(
        base_url=f"{parsed.scheme}://{authority}",
        host=host,
        authority=authority,
        port=port,
        security="tls" if parsed.scheme == "https" else "none",
    )
