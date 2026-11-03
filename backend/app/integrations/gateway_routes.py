"""Resolve legacy logical API paths and explicit deployment prefixes without changing hosts."""

import re
from urllib.parse import unquote, urlsplit, urlunsplit

SERVICES = {"paddle", "custom", "det_rec", "layout", "status"}


class UnavailableService(ValueError):
    """Explicit null prefix means this service is not deployed."""


def safe_path(path):
    decoded = path
    for _ in range(3):
        decoded = unquote(decoded)
    if (
        not path.startswith("/")
        or "//" in decoded
        or "\\" in decoded
        or any(ord(c) < 33 or ord(c) == 127 for c in decoded)
        or any(part in {".", ".."} for part in decoded.split("/"))
        or "%" in decoded
        or len(re.findall(r"/api/v\d+(?=/|$)", decoded)) > 1
        or decoded.split("/").count("paddle") > 1
    ):
        raise ValueError("Invalid Gateway path")
    return path.rstrip("/")


def origin(url):
    parsed = urlsplit(str(url))
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Invalid Gateway origin")
    return (
        parsed.scheme,
        parsed.hostname.lower(),
        parsed.port or (443 if parsed.scheme == "https" else 80),
    )


def resolve_endpoint(base_url, endpoint, prefixes=None, service=None):
    if any(ord(c) < 33 or ord(c) == 127 for c in base_url + endpoint):
        raise ValueError("Invalid characters in Gateway URL")
    base, target = urlsplit(base_url), urlsplit(endpoint)
    origin(base_url)
    if base.query or base.fragment or target.scheme or target.netloc or target.fragment:
        raise ValueError("Gateway endpoints must be same-origin relative paths")
    base_path = safe_path(base.path or "/")
    path = safe_path(target.path)
    prefixes = prefixes or {}
    if set(prefixes) - SERVICES:
        raise ValueError("Unknown Gateway service prefix")
    if service in prefixes and prefixes[service] is None:
        raise UnavailableService("Gateway service is not deployed")
    for prefix in prefixes.values():
        if prefix is None:
            continue
        parts = urlsplit(prefix)
        if parts.scheme or parts.netloc or parts.query or parts.fragment:
            raise ValueError("Gateway prefixes must be relative paths")
        safe_path(prefix)
    explicit = re.match(r"^(.+)/api/v\d+(?:/|$)", path)
    logical = re.match(r"^/api/v\d+(?=/|$)", path)
    if explicit:
        # Existing DB paths may already contain the complete service prefix.
        resolved = path
        override = prefixes.get(service)
        if override and not (
            path == override.rstrip("/") or path.startswith(override.rstrip("/") + "/")
        ):
            raise ValueError("Stored model path conflicts with service prefix")
    elif service in prefixes:
        resolved = prefixes[service].rstrip("/") + (path[logical.end() :] if logical else path)
    else:
        left, right = base_path.split("/"), path.split("/")[1:]
        overlap = 0
        for size in range(1, min(len(left), len(right)) + 1):
            if left[-size:] == right[:size]:
                overlap = size
        resolved = "/".join(left + right[overlap:])
    safe_path(resolved)
    return urlunsplit((base.scheme, base.netloc, resolved, target.query, ""))
