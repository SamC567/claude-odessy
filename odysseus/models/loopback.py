"""Loopback-address test shared by the provider registry and providers.

Kept in its own module so a concrete provider can use it without importing
the registry (which imports every provider).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def is_loopback_url(url: str) -> bool:
    """True if ``url`` points at this machine (localhost or a loopback IP).

    A URL with user information (``user@host``) or a backslash is never
    treated as loopback: ``urlparse`` and the HTTP client (urllib3) disagree
    on where the host of such a URL is. ``http://evil.example\\@127.0.0.1``
    is host ``127.0.0.1`` to ``urlparse`` but ``evil.example`` to urllib3,
    which is where ``requests`` would connect. A local model server needs
    neither, so refusing them only errs towards "not loopback".
    """
    if not isinstance(url, str) or "\\" in url:
        return False
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError:
        return False
    if "@" in parsed.netloc:
        return False
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
