"""Turn a typed address into the one form we store and poll."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class UrlError(ValueError):
    """The text is not an address this monitor can request."""


def normalize_url(value: str) -> str:
    """Accept http, https, www, and localhost, including a port.

    A slash that is the whole path is removed. A slash after a page path stays.
    Scheme and host are lower case. The fragment is dropped.
    """
    text = value.strip()
    if not text:
        raise UrlError("URL is required.")
    if "://" not in text:
        lowered = text.lower()
        if lowered.startswith("www.") or _is_localhost(lowered):
            text = "http://" + text
        else:
            raise UrlError("URL must start with http:// or https://, or use www or localhost.")
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise UrlError("URL port is not valid.") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise UrlError("URL must use http or https.")
    if parts.username is not None or parts.password is not None:
        raise UrlError("URL must not include a username or password.")
    host = (parts.hostname or "").lower()
    if not host:
        raise UrlError("URL must include a host.")
    if not _valid_host(host):
        raise UrlError("URL host must be a domain name or localhost.")
    if port is not None and (port < 1 or port > 65535):
        raise UrlError("URL port is not valid.")
    path = "" if parts.path in {"", "/"} else parts.path
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def _is_localhost(lowered: str) -> bool:
    return (
        lowered == "localhost"
        or lowered.startswith("localhost:")
        or lowered.startswith("localhost/")
    )


def _valid_host(host: str) -> bool:
    if host == "localhost":
        return True
    if _valid_ipv4(host):
        return True
    labels = host.split(".")
    if len(labels) < 2 or len(labels[-1]) < 2:
        return False
    return all(_LABEL.fullmatch(label) for label in labels)


def _valid_ipv4(host: str) -> bool:
    pieces = host.split(".")
    if len(pieces) != 4:
        return False
    for piece in pieces:
        if not piece.isdigit() or (len(piece) > 1 and piece.startswith("0")):
            return False
        number = int(piece)
        if number > 255:
            return False
    return True
