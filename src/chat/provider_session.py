"""Provider session helpers for active Lumi client state."""

from __future__ import annotations

import time
from typing import Any


def set_active_provider(
    provider: str,
    *,
    make_client,
) -> tuple[Any, str | None, float | None]:
    if provider == "vertex":
        return None, provider, 0
    client = make_client(provider)
    return client, provider, None


def resolve_active_client(
    *,
    provider: str,
    active_client,
    active_client_provider: str | None,
    active_client_expires_at: float | None,
    make_client,
    make_vertex_client,
) -> tuple[Any, str | None, float | None]:
    if provider == "vertex":
        refresh_needed = (
            active_client is None
            or active_client_provider != provider
            or active_client_expires_at is None
            or time.time() >= (active_client_expires_at - 60)
        )
        if refresh_needed:
            client, expires_at = make_vertex_client()
            return client, provider, expires_at
        return active_client, active_client_provider, active_client_expires_at

    if active_client is None or active_client_provider != provider:
        return make_client(provider), provider, None
    return active_client, active_client_provider, None
