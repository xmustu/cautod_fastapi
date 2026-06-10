"""
CAutoD 侧入口：在不修改上游 SichengHe6/solidworks_agent 克隆的前提下，
通过 sys.path 选择 multi_agent_src_v1|v2|v3，并子类化其 HTTP Handler 增补 cautod_fastapi 所需路由。
"""

from cautod_solidworks_agent_gateway.gateway import run_gateway

__all__ = ["run_gateway"]
