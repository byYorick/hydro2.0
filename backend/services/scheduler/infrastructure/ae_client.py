from __future__ import annotations

from typing import Any, Dict, Optional

import httpx


async def post_json(
    *,
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, json=payload, headers=headers)


async def get_json(
    *,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 5.0,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.get(url, headers=headers)
