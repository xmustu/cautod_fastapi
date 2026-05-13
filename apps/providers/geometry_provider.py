from __future__ import annotations

import json
from typing import Optional

from apps.geometry import geometry_stream_generator as dify_geometry_stream_generator
from apps.providers.agent_provider import geometry_agent_stream_generator
from config import settings


def resolve_geometry_provider(request_provider: Optional[str]) -> str:
    selected = (request_provider or settings.GEOMETRY_PROVIDER_DEFAULT or "dify").strip().lower()
    if selected not in {"dify", "agent"}:
        selected = settings.GEOMETRY_PROVIDER_DEFAULT.strip().lower()
    if selected not in {"dify", "agent"}:
        selected = "dify"
    return selected


async def geometry_stream_by_provider(
    http_request,
    request,
    current_user,
    redis_client,
    combinde_query: str,
    task,
):
    provider = resolve_geometry_provider(getattr(request, "provider", None))
    print(
        json.dumps(
            {
                "event": "geometry_provider_selected",
                "task_id": str(request.task_id),
                "provider": provider,
                "request_provider": getattr(request, "provider", None),
            },
            ensure_ascii=False,
        )
    )

    if provider == "agent":
        try:
            async for chunk in geometry_agent_stream_generator(
                http_request,
                request,
                current_user,
                redis_client,
                combinde_query,
                task,
            ):
                yield chunk
            return
        except Exception as exc:
            fallback_enabled = bool(settings.AGENT_FALLBACK_TO_DIFY)
            print(
                json.dumps(
                    {
                        "event": "geometry_provider_fallback",
                        "task_id": str(request.task_id),
                        "from": "agent",
                        "to": "dify",
                        "fallback_enabled": fallback_enabled,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            if not fallback_enabled:
                raise

    async for chunk in dify_geometry_stream_generator(
        http_request,
        request,
        current_user,
        redis_client,
        combinde_query,
        task,
    ):
        yield chunk

