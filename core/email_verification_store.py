import logging
import random
import threading
import time
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_memory_store: dict[str, tuple[str, float]] = {}
_memory_code_store: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()

_REDIS_CLIENT = None


def _get_redis_client():
    global _REDIS_CLIENT

    if _REDIS_CLIENT is not None:
        return _REDIS_CLIENT

    if not settings.REDIS_AVAILABLE:
        return None

    try:
        import redis  # type: ignore

        _REDIS_CLIENT = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            db=settings.REDIS_DB,
            decode_responses=True,
        )
        return _REDIS_CLIENT
    except Exception as exc:  # pragma: no cover - redis 连接失败时降级
        logger.warning("Redis unavailable for email verification codes: %s", exc)
        return None


def generate_verification_code(length: int = 6) -> str:
    upper = 10**length - 1
    code = random.randint(0, upper)
    return f"{code:0{length}d}"


def save_code(email: str, code: str, ttl_seconds: int) -> None:
    redis_client = _get_redis_client()
    if redis_client:
        try:
            redis_client.setex(_build_email_key(email), ttl_seconds, code)
            redis_client.setex(_build_code_key(code), ttl_seconds, email.lower())
            return
        except Exception as exc:  # pragma: no cover - Redis 异常时回退
            logger.warning("Failed to store verification code in Redis: %s", exc)

    expires_at = time.time() + ttl_seconds
    with _lock:
        lowered = email.lower()
        _memory_store[lowered] = (code, expires_at)
        _memory_code_store[code] = (lowered, expires_at)


def verify_code(email: str, code: str) -> bool:
    redis_client = _get_redis_client()
    if redis_client:
        try:
            stored = redis_client.get(_build_email_key(email))
            return stored is not None and stored == code
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read verification code from Redis: %s", exc)

    with _lock:
        entry = _memory_store.get(email.lower())
        if not entry:
            return False
        stored_code, expires_at = entry
        if time.time() > expires_at:
            lowered = email.lower()
            _memory_store.pop(lowered, None)
            if stored_code in _memory_code_store:
                _memory_code_store.pop(stored_code, None)
            return False
        return stored_code == code


def clear_code(email: str) -> None:
    redis_client = _get_redis_client()
    if redis_client:
        try:
            code = redis_client.get(_build_email_key(email))
            redis_client.delete(_build_email_key(email))
            if code:
                redis_client.delete(_build_code_key(code))
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to clear verification code from Redis: %s", exc)

    with _lock:
        lowered = email.lower()
        code = None
        entry = _memory_store.pop(lowered, None)
        if entry:
            code = entry[0]
        if code:
            _memory_code_store.pop(code, None)


def get_email_by_code(code: str) -> Optional[str]:
    redis_client = _get_redis_client()
    if redis_client:
        try:
            email = redis_client.get(_build_code_key(code))
            return email
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read verification code mapping from Redis: %s", exc)

    with _lock:
        entry = _memory_code_store.get(code)
        if not entry:
            return None
        email, expires_at = entry
        if time.time() > expires_at:
            _memory_code_store.pop(code, None)
            _memory_store.pop(email, None)
            return None
        return email


def _build_key(email: str) -> str:
    return _build_email_key(email)


def _build_email_key(email: str) -> str:
    return f"email_verification:email:{email.lower()}"


def _build_code_key(code: str) -> str:
    return f"email_verification:code:{code}"


