"""
验证 geometry → solidworks_agent 路径在 HTTP 客户端层的并发行为。

说明（与端到端真实环境一致）：
- cautod_fastapi 侧：每个任务独立调用 AgentServiceClient.chat_stream，无进程内串行锁。
- solidworks_agent 侧：run_solidworks_pipeline 使用 SOLIDWORKS_CALL_LOCK，多会话仍会排队访问 SolidWorks。
- FastAPI 在收到 pipeline_result 后，_export_slddoc_to_stl 使用 _sw_export_lock，STL 导出也会互斥。

本测试仅证明「对 agent 的 HTTP 流式请求」在客户端可并发发起（mock 网络延迟）。
"""

from __future__ import annotations

import asyncio
import sys
import time
import types
from unittest.mock import patch

import pytest

# 避免在无 .env / 无 pydantic-email 等环境下导入完整 config 失败
if "config" not in sys.modules:
    _fake_settings = types.SimpleNamespace(
        AGENT_SERVICE_BASE_URL="http://127.0.0.1:8500",
        AGENT_SERVICE_CHAT_PATH="/api/chat-sse",
        AGENT_SERVICE_RECOMMEND_PATH="/api/optimize/recommend-algorithms",
        AGENT_SERVICE_TIMEOUT=60.0,
        AGENT_SERVICE_RETRY=0,
    )
    _cfg = types.ModuleType("config")
    _cfg.settings = _fake_settings
    sys.modules["config"] = _cfg

from apps.providers.agent_client import AgentServiceClient


class _FakeStreamResponse:
    def __init__(self, per_request_delay: float) -> None:
        self._delay = per_request_delay

    async def __aenter__(self) -> _FakeStreamResponse:
        return self

    async def __aexit__(self, *args) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    @property
    def headers(self) -> dict[str, str]:
        return {}

    async def aiter_lines(self):
        await asyncio.sleep(self._delay)
        yield 'data: {"type": "done"}'


class _FakeHttpxAsyncClient:
    def __init__(self, *args, delay: float = 0.2, **kwargs) -> None:
        self._delay = delay

    async def __aenter__(self) -> _FakeHttpxAsyncClient:
        return self

    async def __aexit__(self, *args) -> None:
        return None

    def stream(self, method: str, url: str, **kwargs):
        return _FakeStreamResponse(self._delay)


@pytest.mark.asyncio
async def test_agent_chat_stream_http_layer_runs_in_parallel():
    """N 路并发 chat_stream 的总耗时应明显小于 N×单次延迟（证明非串行 await）。"""
    n = 5
    per_delay = 0.12

    class _ClientFactory:
        def __call__(self, *args, **kwargs):
            return _FakeHttpxAsyncClient(delay=per_delay)

    with patch("apps.providers.agent_client.httpx.AsyncClient", _ClientFactory()):
        t0 = time.perf_counter()

        async def one_stream(idx: int):
            c = AgentServiceClient()
            chunks = []
            async for payload in c.chat_stream(message=f"msg-{idx}", session_id=f"sess-{idx}"):
                chunks.append(payload)
            return chunks

        results = await asyncio.gather(*[one_stream(i) for i in range(n)])
        elapsed = time.perf_counter() - t0

    assert len(results) == n
    assert all(r and r[-1].get("type") == "done" for r in results)
    # 若完全串行，耗时约 n * per_delay；并发应接近单次延迟（留余量给事件循环）
    assert elapsed < per_delay * (n - 1), (
        f"期望并发：elapsed={elapsed:.3f}s 应远小于串行下界 {(n - 1) * per_delay:.3f}s"
    )
