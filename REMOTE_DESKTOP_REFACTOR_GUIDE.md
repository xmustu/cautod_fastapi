# 远程桌面功能重构方案

## 架构调整说明

原来的设计是将远程桌面功能（包含 `pyautogui` 和屏幕截图）放在 Docker 容器的后端服务中，这会导致以下问题：
1. Docker 容器中没有 DISPLAY 环境变量，导致 `pyautogui` 导入失败
2. 容器内无法访问宿主机的图形界面
3. 需要额外配置 X11 转发或虚拟显示

**新架构**：
- **Windows 主机** (`algorithm/optimize`): 运行远程桌面服务，直接控制 Windows 桌面
- **Docker 后端** (`cautod_fastapi`): 作为 WebSocket 代理，转发前端请求到 Windows 主机
- **前端**: 连接到 Docker 后端的 WebSocket 端点

## 文件变更

### 1. 新增文件：`algorithm/optimize/remote_desktop_service.py`
已创建，包含完整的远程桌面控制逻辑：
- WebSocket 端点: `/ws/remote`
- HTTP 端点: `/health`, `/`
- 端口: `9200`

### 2. 修改文件：`cautod_fastapi/apps/routes/remote.py`
将其改为 WebSocket 代理，内容应替换为：

```python
"""
远程桌面 WebSocket 代理
该模块运行在 Docker 容器中，作为前端和 Windows 主机上远程桌面服务的桥梁
"""
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import aiohttp
import os

# 创建路由
app = APIRouter(tags=["远程控制代理"])

# 从环境变量读取远程桌面服务地址
REMOTE_DESKTOP_HOST = os.getenv("REMOTE_DESKTOP_HOST", "host.docker.internal")
REMOTE_DESKTOP_PORT = os.getenv("REMOTE_DESKTOP_PORT", "9200")
REMOTE_DESKTOP_WS_URL = f"ws://{REMOTE_DESKTOP_HOST}:{REMOTE_DESKTOP_PORT}/ws/remote"

print(f"[远程桌面代理] 配置的远程服务地址: {REMOTE_DESKTOP_WS_URL}")


@app.get("/")
async def remote_info():
    """获取远程桌面服务信息"""
    return {
        "service": "远程桌面代理",
        "remote_service": REMOTE_DESKTOP_WS_URL,
        "status": "running",
        "description": "该服务作为前端和 Windows 主机远程桌面服务之间的 WebSocket 代理"
    }


@app.get("/health")
async def health_check():
    """健康检查并测试与远程服务的连接"""
    try:
        # 尝试连接到远程服务的 HTTP 端点
        async with aiohttp.ClientSession() as session:
            health_url = f"http://{REMOTE_DESKTOP_HOST}:{REMOTE_DESKTOP_PORT}/health"
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    remote_health = await resp.json()
                    return {
                        "status": "healthy",
                        "proxy": "running",
                        "remote_service": {
                            "status": "connected",
                            "details": remote_health
                        }
                    }
                else:
                    return {
                        "status": "degraded",
                        "proxy": "running",
                        "remote_service": {
                            "status": "error",
                            "message": f"远程服务返回状态码: {resp.status}"
                        }
                    }
    except asyncio.TimeoutError:
        return {
            "status": "degraded",
            "proxy": "running",
            "remote_service": {
                "status": "timeout",
                "message": "连接远程服务超时"
            }
        }
    except Exception as e:
        return {
            "status": "degraded",
            "proxy": "running",
            "remote_service": {
                "status": "unreachable",
                "message": f"无法连接到远程服务: {str(e)}",
                "url": REMOTE_DESKTOP_WS_URL
            }
        }


@app.websocket("/ws/")
async def websocket_proxy(websocket: WebSocket):
    """
    WebSocket 代理端点
    将前端的 WebSocket 连接代理到 Windows 主机上的远程桌面服务
    """
    await websocket.accept()
    print(f"[远程桌面代理] 前端 WebSocket 连接已建立")
    
    remote_ws = None
    
    try:
        # 连接到远程桌面服务
        async with aiohttp.ClientSession() as session:
            try:
                remote_ws = await session.ws_connect(
                    REMOTE_DESKTOP_WS_URL,
                    timeout=aiohttp.ClientTimeout(total=10)
                )
                print(f"[远程桌面代理] 已连接到远程服务: {REMOTE_DESKTOP_WS_URL}")
                
                # 创建两个任务：一个从前端接收消息并转发到远程服务，另一个从远程服务接收消息并转发到前端
                async def forward_to_remote():
                    """从前端接收消息并转发到远程服务"""
                    try:
                        while True:
                            data = await websocket.receive_text()
                            await remote_ws.send_str(data)
                    except WebSocketDisconnect:
                        print("[远程桌面代理] 前端连接断开")
                    except Exception as e:
                        print(f"[远程桌面代理] 转发到远程时出错: {e}")
                
                async def forward_to_client():
                    """从远程服务接收消息并转发到前端"""
                    try:
                        async for msg in remote_ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                await websocket.send_bytes(msg.data)
                            elif msg.type == aiohttp.WSMsgType.TEXT:
                                await websocket.send_text(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                print(f"[远程桌面代理] 远程服务 WebSocket 错误")
                                break
                    except Exception as e:
                        print(f"[远程桌面代理] 转发到前端时出错: {e}")
                
                # 并行运行两个转发任务
                await asyncio.gather(
                    forward_to_remote(),
                    forward_to_client(),
                    return_exceptions=True
                )
                
            except asyncio.TimeoutError:
                error_msg = json.dumps({
                    "type": "error",
                    "message": "连接远程桌面服务超时",
                    "suggestion": "请确保 Windows 主机上的远程桌面服务正在运行"
                }, ensure_ascii=False)
                await websocket.send_text(f"error:{error_msg}")
                print(f"[远程桌面代理] 连接超时: {REMOTE_DESKTOP_WS_URL}")
            except aiohttp.ClientError as e:
                error_msg = json.dumps({
                    "type": "error",
                    "message": f"无法连接到远程桌面服务: {str(e)}",
                    "suggestion": "请检查 Windows 主机上的远程桌面服务是否正在运行，以及网络配置是否正确"
                }, ensure_ascii=False)
                await websocket.send_text(f"error:{error_msg}")
                print(f"[远程桌面代理] 连接失败: {e}")
            
    except WebSocketDisconnect:
        print("[远程桌面代理] 前端 WebSocket 连接断开")
    except Exception as e:
        print(f"[远程桌面代理] WebSocket 代理错误: {e}")
        try:
            error_msg = json.dumps({
                "type": "error",
                "message": f"代理服务错误: {str(e)}"
            }, ensure_ascii=False)
            await websocket.send_text(f"error:{error_msg}")
        except:
            pass
    finally:
        if remote_ws and not remote_ws.closed:
            await remote_ws.close()
        print("[远程桌面代理] WebSocket 连接已清理")


@app.websocket("/ws/{user_id}")
async def websocket_endpoint_with_user(websocket: WebSocket, user_id: str):
    """
    带用户ID的 WebSocket 端点（保持向后兼容）
    """
    print(f"[远程桌面代理] 用户 {user_id} 正在连接")
    await websocket_proxy(websocket)
```

## 部署步骤

### 1. 在 Windows 主机上启动远程桌面服务

```bash
cd D:\CAutoD\algorithm\optimize
python remote_desktop_service.py
```

服务将在端口 `9200` 上运行。

### 2. 配置 Docker 环境变量

在 `docker-compose.yml` 中添加环境变量：

```yaml
services:
  cautod_fastapi:
    environment:
      - REMOTE_DESKTOP_HOST=host.docker.internal  # Docker Desktop 自动解析为宿主机
      - REMOTE_DESKTOP_PORT=9200
```

对于 Linux Docker，使用：
```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - REMOTE_DESKTOP_HOST=host.docker.internal
      - REMOTE_DESKTOP_PORT=9200
```

### 3. 安装依赖

后端需要添加 `aiohttp`：
```bash
# 在cautod_fastapi/requirements.txt 中添加
aiohttp>=3.9.0
```

Windows 主机的 optimize 服务需要：
```bash
pip install fastapi uvicorn pyautogui pillow mss
```

### 4. 启动服务

**启动顺序**：
1. 先启动 Windows 主机上的远程桌面服务（端口 9200）
2. 再启动 Docker 后端服务

### 5. 测试

1. 访问 `http://localhost:8000/api/remote/health` 检查代理状态
2. 前端连接到 `ws://localhost:8000/api/remote/ws/` 进行远程控制

## 优势

1. **架构清晰**：Docker 只负责业务逻辑，Windows 主机负责图形界面交互
2. **无需 DISPLAY**：Docker 容器不需要配置图形界面环境
3. **易于调试**：两个服务独立运行，可以分别调试
4. **性能更好**：减少了 Docker 和宿主机之间的复杂映射
5. **安全隔离**：远程桌面服务只在内网运行，通过代理访问

## 防火墙配置

确保 Windows 防火墙允许端口 `9200`：

```powershell
New-NetFirewallRule -DisplayName "Remote Desktop Service" -Direction Inbound -Protocol TCP -LocalPort 9200 -Action Allow
```

## 故障排查

1. **无法连接到远程服务**
   - 检查 Windows 主机上的服务是否启动
   - 检查端口 9200 是否被占用
   - 检查防火墙设置

2. **连接超时**
   - 确认 `host.docker.internal` 可以解析
   - 尝试使用宿主机的实际 IP 地址

3. **截图失败**
   - 确保 Windows 主机没有锁屏
   - 检查是否安装了 `pyautogui` 和 `pillow`

## 备注

- 远程桌面服务（端口 9200）应该只在内网访问，不要暴露到公网
- 如果需要多用户支持，可以在远程桌面服务中添加身份验证
- 建议使用 systemd 或 Windows 服务管理器来管理远程桌面服务的自动启动
