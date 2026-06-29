from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, Optional
import json
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


class AgentServiceClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.AGENT_SERVICE_BASE_URL).rstrip("/")
        self.chat_path = settings.AGENT_SERVICE_CHAT_PATH
        self.recommend_path = settings.AGENT_SERVICE_RECOMMEND_PATH
        self.timeout = settings.AGENT_SERVICE_TIMEOUT
        self.retries = max(0, settings.AGENT_SERVICE_RETRY)

    def _chat_stream_timeout(self) -> httpx.Timeout:
        base = float(self.timeout)
        # agent 首 token / 建模阶段可能长时间无输出，read 需单独放宽
        read_timeout = max(base, 600.0)
        return httpx.Timeout(connect=base, read=read_timeout, write=base, pool=base)

    async def chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        headers: Dict[str, str] = {}
        if session_id:
            headers["X-Session-Id"] = session_id

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._chat_stream_timeout()) as client:
                    async with client.stream(
                        "POST",
                        f"{self.base_url}{self.chat_path}",
                        json={"message": message},
                        headers=headers,
                    ) as response:
                        response.raise_for_status()
                        server_session_id = response.headers.get("X-Session-Id")
                        async for line in response.aiter_lines():
                            line = (line or "").strip("\r\n").strip()
                            if not line:
                                continue
                            # 兼容标准 SSE：忽略 event:/id:/空行，只解析 data:
                            if line.startswith(":"):
                                continue
                            if not line.lower().startswith("data:"):
                                continue
                            payload_str = line.split(":", 1)[1].lstrip()
                            if not payload_str:
                                continue
                            try:
                                payload = json.loads(payload_str)
                            except json.JSONDecodeError as je:
                                logger.warning(
                                    "agent_sse_json_error: %s line_preview=%r",
                                    je,
                                    line[:500],
                                )
                                raise
                            if not isinstance(payload, dict):
                                logger.warning(
                                    "agent_sse_non_dict: type=%s preview=%r",
                                    type(payload).__name__,
                                    str(payload)[:200],
                                )
                                continue
                            if server_session_id and "session_id" not in payload:
                                payload["session_id"] = server_session_id
                            yield payload
                        return
            except Exception as exc:
                logger.exception(
                    "agent_chat_stream_failed url=%s%s attempt=%s",
                    self.base_url,
                    self.chat_path,
                    attempt + 1,
                )
                last_error = exc
                if attempt >= self.retries:
                    raise
        if last_error:
            raise last_error

    async def recommend_algorithms(
        self,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers: Dict[str, str] = {}
        if session_id:
            headers["X-Session-Id"] = session_id

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}{self.recommend_path}",
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    data = response.json() 
                    
                    if isinstance(data, dict):
                        return data
                    return {"recommendations": data}
            except Exception as exc:
                logger.exception(
                    "agent_recommend_failed url=%s%s attempt=%s",
                    self.base_url,
                    self.recommend_path,
                    attempt + 1,
                )
                last_error = exc
                if attempt >= self.retries:
                    raise
        if last_error:
            raise last_error

