"""Loopback-address test shared by the provider registry and providers.

Kept in its own module so a concrete provider can use it without importing
the registry (which imports every provider).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


def is_loopback_url(url: str) -> bool:
    """True if ``url`` points at this machine (localhost or a loopback IP)."""
    try:
        host = urlparse(url).hostname
    except ValueError:
        return False
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
