from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional

from apps.geometry import geometry_stream_generator as dify_geometry_stream_generator
from config import settings

AgentVersion = Literal["v1", "v2", "v3"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENT_SRC_BY_VERSION: dict[AgentVersion, Path] = {
    "v1": _REPO_ROOT / "algorithm" / "solidworks_agent" / "multi_agent_src_v1",
    "v2": _REPO_ROOT / "algorithm" / "solidworks_agent" / "multi_agent_src_v2",
    "v3": _REPO_ROOT / "algorithm" / "solidworks_agent" / "multi_agent_src_v3",
}

# provider 别名 → agent 版本（方案 A：各版本独立 gateway 端口）
_PROVIDER_TO_VERSION: dict[str, AgentVersion] = {
    "agent_v1": "v1",
    "v1": "v1",
    "solidworks_agent_v1": "v1",
    "agent_v2": "v2",
    "v2": "v2",
    "solidworks_agent_v2": "v2",
    "agent_v3": "v3",
    "agent": "v3",
    "v3": "v3",
    "solidworks_agent": "v3",
    "solidworks_agent_v3": "v3",
}
_AGENT_PROVIDER_ALIASES = frozenset(_PROVIDER_TO_VERSION.keys())


def resolve_geometry_provider(request_provider: Optional[str]) -> str:
    selected = (request_provider or settings.GEOMETRY_PROVIDER_DEFAULT or "dify").strip().lower()
    if selected in _AGENT_PROVIDER_ALIASES:
        return "agent"
    if selected not in {"dify", "agent"}:
        selected = settings.GEOMETRY_PROVIDER_DEFAULT.strip().lower()
        if selected in _AGENT_PROVIDER_ALIASES:
            return "agent"
    if selected not in {"dify", "agent"}:
        selected = "dify"
    return selected


def resolve_agent_version(
    request_provider: Optional[str],
    request_version: Optional[str] = None,
) -> AgentVersion:
    """从 provider 或显式 version 字段解析 multi_agent_src 版本。"""
    explicit = (request_version or "").strip().lower()
    if explicit in {"v1", "v2", "v3"}:
        return explicit  # type: ignore[return-value]

    selected = (request_provider or "").strip().lower()
    if selected in _PROVIDER_TO_VERSION:
        return _PROVIDER_TO_VERSION[selected]

    default = (getattr(settings, "SOLIDWORKS_AGENT_VERSION", None) or "v3").strip().lower()
    if default in {"v1", "v2", "v3"}:
        return default  # type: ignore[return-value]
    return "v3"


def resolve_agent_service_base_url(version: AgentVersion) -> str:
    url_by_version = {
        "v1": getattr(settings, "AGENT_SERVICE_BASE_URL_V1", "").strip(),
        "v2": getattr(settings, "AGENT_SERVICE_BASE_URL_V2", "").strip(),
        "v3": getattr(settings, "AGENT_SERVICE_BASE_URL_V3", "").strip(),
    }
    url = url_by_version.get(version) or ""
    if not url:
        url = settings.AGENT_SERVICE_BASE_URL.strip()
    return url.rstrip("/")


def resolve_solidworks_agent_src(version: AgentVersion) -> Path:
    configured = (getattr(settings, "SOLIDWORKS_AGENT_SRC", None) or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _AGENT_SRC_BY_VERSION[version].resolve()


def get_solidworks_agent_binding(version: AgentVersion) -> dict[str, Any]:
    src = resolve_solidworks_agent_src(version)
    port_hint = {"v1": 8501, "v2": 8502, "v3": 8503}[version]
    return {
        "version": version,
        "src_path": str(src),
        "src_exists": src.is_dir(),
        "web_demo_exists": (src / "web_demo.py").is_file(),
        "service_base_url": resolve_agent_service_base_url(version),
        "chat_path": settings.AGENT_SERVICE_CHAT_PATH,
        "gateway_hint": (
            "python -m cautod_solidworks_agent_gateway "
            f'--upstream "{_REPO_ROOT / "algorithm" / "solidworks_agent"}" '
            f"--version {version} --host 127.0.0.1 --port {port_hint}"
        ),
    }


async def geometry_stream_by_provider(
    http_request,
    request,
    current_user,
    redis_client,
    combinde_query: str,
    task,
):
    provider = resolve_geometry_provider(getattr(request, "provider", None))
    agent_version: AgentVersion | None = None
    agent_binding: dict[str, Any] | None = None
    if provider == "agent":
        agent_version = resolve_agent_version(
            getattr(request, "provider", None),
            getattr(request, "version", None),
        )
        agent_binding = get_solidworks_agent_binding(agent_version)

    print(
        json.dumps(
            {
                "event": "geometry_provider_selected",
                "task_id": str(request.task_id),
                "provider": provider,
                "request_provider": getattr(request, "provider", None),
                "request_version": getattr(request, "version", None),
                "agent_version": agent_version,
                "solidworks_agent": agent_binding,
            },
            ensure_ascii=False,
        )
    )

    if provider == "agent":
        # 延迟导入，避免与 agent_provider 循环依赖
        from apps.providers.agent_provider import geometry_agent_stream_generator

        if agent_binding and not agent_binding.get("web_demo_exists"):
            print(
                json.dumps(
                    {
                        "event": "solidworks_agent_src_missing",
                        "task_id": str(request.task_id),
                        "solidworks_agent": agent_binding,
                    },
                    ensure_ascii=False,
                )
            )
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
                        "solidworks_agent": agent_binding,
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
