import pytest

from apps.providers import geometry_provider


class _DummyRequest:
    task_id = 123
    provider = "agent"
    version = None


@pytest.mark.asyncio
async def test_geometry_provider_fallback_to_dify(monkeypatch):
    async def failing_agent(*args, **kwargs):
        raise RuntimeError("agent down")
        yield  # pragma: no cover

    async def dify_ok(*args, **kwargs):
        yield "event: text_chunk\ndata: {\"text\":\"ok\"}\n\n"

    monkeypatch.setattr(geometry_provider.settings, "AGENT_FALLBACK_TO_DIFY", True)
    monkeypatch.setattr(geometry_provider, "geometry_agent_stream_generator", failing_agent)
    monkeypatch.setattr(geometry_provider, "dify_geometry_stream_generator", dify_ok)

    chunks = []
    async for chunk in geometry_provider.geometry_stream_by_provider(
        None, _DummyRequest(), None, None, "hello", None
    ):
        chunks.append(chunk)
    assert any("text_chunk" in item for item in chunks)


@pytest.mark.asyncio
async def test_geometry_provider_agent_no_fallback(monkeypatch):
    async def failing_agent(*args, **kwargs):
        raise RuntimeError("agent down")
        yield  # pragma: no cover

    async def dify_ok(*args, **kwargs):
        yield "x"

    monkeypatch.setattr(geometry_provider.settings, "AGENT_FALLBACK_TO_DIFY", False)
    monkeypatch.setattr(geometry_provider, "geometry_agent_stream_generator", failing_agent)
    monkeypatch.setattr(geometry_provider, "dify_geometry_stream_generator", dify_ok)

    with pytest.raises(RuntimeError):
        async for _ in geometry_provider.geometry_stream_by_provider(
            None, _DummyRequest(), None, None, "hello", None
        ):
            pass


def test_resolve_geometry_provider():
    assert geometry_provider.resolve_geometry_provider("agent") == "agent"
    assert geometry_provider.resolve_geometry_provider("agent_v1") == "agent"
    assert geometry_provider.resolve_geometry_provider("agent_v3") == "agent"
    assert geometry_provider.resolve_geometry_provider("v3") == "agent"
    assert geometry_provider.resolve_geometry_provider("dify") == "dify"


def test_resolve_agent_version():
    assert geometry_provider.resolve_agent_version("agent_v1", None) == "v1"
    assert geometry_provider.resolve_agent_version("agent_v2", None) == "v2"
    assert geometry_provider.resolve_agent_version("agent", None) == "v3"
    assert geometry_provider.resolve_agent_version("agent_v3", None) == "v3"
    assert geometry_provider.resolve_agent_version("agent", "v2") == "v2"


def test_resolve_agent_service_base_url():
    assert geometry_provider.resolve_agent_service_base_url("v1").endswith(":8501")
    assert geometry_provider.resolve_agent_service_base_url("v2").endswith(":8502")
    assert geometry_provider.resolve_agent_service_base_url("v3").endswith(":8503")


def test_solidworks_agent_bindings():
    for version in ("v1", "v2", "v3"):
        binding = geometry_provider.get_solidworks_agent_binding(version)
        assert binding["version"] == version
        assert binding["src_path"].endswith(f"multi_agent_src_{version}")
        assert f"--version {version}" in binding["gateway_hint"]
