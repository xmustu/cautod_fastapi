"""Redis helpers for StreamingResponse async generators.

`app.state.redis` is created during app lifespan and can be bound to a different
asyncio loop than the one running the streaming generator, which triggers
``Future attached to a different loop`` when awaiting redis in the stream.
Geometry streams therefore use a short-lived client created on the current loop.
"""

from __future__ import annotations

import redis.asyncio as redis_async

from config import settings


def create_streaming_redis():
    kwargs = dict(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True,
        encoding="utf-8",
    )
    if getattr(settings, "REDIS_PASSWORD", None):
        kwargs["password"] = settings.REDIS_PASSWORD
    return redis_async.Redis(**kwargs)


async def aclose_streaming_redis(client) -> None:
    if client is None:
        return
    try:
        await client.aclose()
        await client.connection_pool.disconnect()
    except Exception:
        pass
