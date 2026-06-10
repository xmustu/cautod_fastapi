from __future__ import annotations

import argparse
import logging
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from urllib.parse import urlparse

LOG = logging.getLogger("cautod_solidworks_agent_gateway")


def _normalize_version_arg(version: str) -> str:
    v = version.strip().lower()
    if v in {"1", "v1"}:
        return "v1"
    if v in {"2", "v2"}:
        return "v2"
    if v in {"3", "v3"}:
        return "v3"
    if v.startswith("multi_agent_src_"):
        return v.removeprefix("multi_agent_src_")
    return v


def _version_src_dir(upstream_root: Path, version: str) -> Path:
    v = _normalize_version_arg(version)
    d = upstream_root / f"multi_agent_src_{v}"
    if not d.is_dir():
        raise FileNotFoundError(
            f"未找到版本目录: {d}（upstream_root={upstream_root}，version={version!r}）"
        )
    if not (d / "web_demo.py").is_file():
        raise FileNotFoundError(f"目录中缺少 web_demo.py: {d}")
    return d


def load_upstream_web_demo(version_src: Path) -> ModuleType:
    """
    将版本目录置于 sys.path 首位后导入 web_demo，不修改上游仓库内任何文件。
    """
    root = str(version_src.resolve())
    if sys.path[0] != root:
        sys.path.insert(0, root)
    import importlib

    # 避免重复加载同名模块指向错误目录
    for name in ("web_demo", "agents", "orchestrator", "config", "executor", "agent_tools"):
        sys.modules.pop(name, None)
    return importlib.import_module("web_demo")


def build_gateway_handler(upstream_web_demo: ModuleType, version_label: str):
    Base = upstream_web_demo.DemoHandler

    class CautodGatewayHandler(Base):
        server_version = f"CautodSolidWorksGateway/{version_label}"

        def do_GET(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self.send_json(
                    {
                        "ok": True,
                        "upstream_version_dir": version_label,
                        "gateway": "cautod_solidworks_agent_gateway",
                    }
                )
                return
            return super().do_GET()

        def do_POST(self) -> None:  # type: ignore[override]
            parsed = urlparse(self.path)
            if parsed.path == "/api/optimize/recommend-algorithms":
                length = int(self.headers.get("Content-Length", "0"))
                if length > 0:
                    try:
                        self.rfile.read(length)
                    except Exception:
                        pass
                # cautod_fastapi 在解析失败或空列表时会回退 GA/PSO/DE
                self.send_json({"recommendations": []})
                return
            return super().do_POST()

    return CautodGatewayHandler


def run_gateway(
    upstream_root: Path | None,
    version: str,
    host: str,
    port: int,
    agent_src: Path | None = None,
) -> None:
    if agent_src is not None:
        version_src = agent_src.expanduser().resolve()
        if not (version_src / "web_demo.py").is_file():
            raise FileNotFoundError(f"--agent-src 中缺少 web_demo.py: {version_src}")
        vlabel = version_src.name
    else:
        if upstream_root is None:
            raise ValueError("必须提供 upstream_root 或 agent_src")
        version_src = _version_src_dir(upstream_root, version)
        vlabel = version_src.name
    LOG.info("loading upstream web_demo from %s", version_src)
    mod = load_upstream_web_demo(version_src)
    handler_cls = build_gateway_handler(mod, vlabel)
    server = ThreadingHTTPServer((host, port), handler_cls)
    print(
        f"[cautod_solidworks_agent_gateway] {vlabel} @ {version_src}\n"
        f"  HTTP: http://{host}:{port}\n"
        f"  chat SSE: POST http://{host}:{port}/api/chat-sse\n"
        f"  recommend (stub): POST http://{host}:{port}/api/optimize/recommend-algorithms\n"
        f"  health: GET http://{host}:{port}/health\n"
    )
    server.serve_forever()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "启动网关：从上游 solidworks_agent 克隆中选择 multi_agent_src_v1|v2|v3，"
            "不修改上游代码；仅增补 cautod_fastapi 使用的推荐接口存根。"
        )
    )
    p.add_argument(
        "--upstream",
        type=Path,
        default=None,
        help="上游仓库根目录（内含 multi_agent_src_v1 等）；与 --agent-src 二选一",
    )
    p.add_argument(
        "--agent-src",
        type=Path,
        default=None,
        help="直接指定含 web_demo.py 的目录（例如本仓库 solidworks_agent/multi_agent_src），与 --upstream 二选一",
    )
    p.add_argument(
        "--version",
        default="v3",
        help="在 --upstream 模式下使用：v1 | v2 | v3（默认 v3）",
    )
    p.add_argument("--host", default="127.0.0.1", help="监听地址")
    p.add_argument("--port", type=int, default=8500, help="监听端口（与 cautod_fastapi AGENT_SERVICE_BASE_URL 一致）")
    p.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG 日志",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    agent_src = args.agent_src.expanduser().resolve() if args.agent_src else None
    upstream_root = args.upstream.expanduser().resolve() if args.upstream else None
    if agent_src is None and upstream_root is None:
        raise SystemExit("请指定 --upstream（官方克隆根目录）或 --agent-src（含 web_demo 的目录）其一")
    if agent_src is not None and upstream_root is not None:
        raise SystemExit("--upstream 与 --agent-src 请勿同时使用")
    if agent_src is not None:
        if not agent_src.is_dir():
            raise SystemExit(f"--agent-src 不是目录: {agent_src}")
        run_gateway(None, args.version, args.host, args.port, agent_src=agent_src)
    else:
        assert upstream_root is not None
        if not upstream_root.is_dir():
            raise SystemExit(f"--upstream 不是目录: {upstream_root}")
        run_gateway(upstream_root, args.version, args.host, args.port, agent_src=None)


if __name__ == "__main__":
    main()
