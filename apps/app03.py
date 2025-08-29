from typing import Optional, Dict, List, Any, Union, Callable

from fastapi import APIRouter
from fastapi import Header
from pydantic import BaseModel
from pydantic import Field
from fastapi import Form
from pydantic import  field_validator

from core.authentication import authenticate

import httpx
from fastapi import status, HTTPException
from contextlib import asynccontextmanager
import websockets

import asyncio
import json
import os


optimize = APIRouter()

@optimize.get("")
async def optimize_home():
    return {"message": "Design optimization home page"}


# 数据模型定义
class OptimizeRequest(BaseModel):
    """设计优化接口请求参数模型"""
    method: int = Field(..., description="优化方法编号")
    file: str = Field(..., description="待优化的CAD文件名称（如model.sldpart）")
    constraints: Optional[Dict[str, Any]] = Field(None, description="优化约束条件")
    parameters: Optional[List[str]] = Field(None, description="需要优化的参数列表")
    target: Optional[str] = Field("minimize_volume", description="优化目标（如minimize_volume, minimize_stress）")
    @field_validator('method')
    def response_mode_must_be_streaming(cls, v):

        if v not in (0, 1):
            raise ValueError('method must be 0 or 1')
        return v

class UnitInfo(BaseModel):
    """单位信息模型"""
    volume: str = Field("m³", description="体积单位")
    stress: str = Field("Pa", description="应力单位")

class OptimizeResult(BaseModel):
    """优化结果模型"""
    optimized_file: str = Field(..., description="优化后的CAD文件路径或下载链接（.sldpart格式）")
    best_params: List[float] = Field(..., description="优化得到的最优参数数组")
    final_volume: float = Field(..., description="优化后CAD模型的体积")
    final_stress: float = Field(..., description="优化后CAD模型的应力值")
    unit: UnitInfo = Field(..., description="单位说明")
    constraint_satisfied: bool = Field(..., description="是否满足约束条件")

# class OptimizationParamsRequest(BaseModel):
#     """接收优化参数的请求体模型"""
#     conversation_id: str = Field(..., description="任务所属的对话ID")
#     task_id: int = Field(..., description="任务ID")
#     params: Dict[str, Dict[str, float]] = Field(..., description="优化参数及其范围，例如 {'param1': {'min': 0.1, 'max': 1.0}}")
class OptimizationParamsRequest(BaseModel):
    """接收优化参数的请求体模型"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_id: int = Field(..., description="任务ID")
    params: Dict[str, Dict[str, Union[float, str]]] = Field(..., description="优化参数及其范围，例如 {'param1': {'min': 0.1, 'max': 1.0}}")

# 数据模型（与算法侧对应）
class AlgorithmRequest(BaseModel):
    task_id: str
    conversation_id: str
    geometry_description: str = None
    parameters: Optional[Dict[str, Any]] = None

class TaskStatus(BaseModel):
    task_id: str
    status: str
    message: Optional[str] = None

class HealthStatus(BaseModel):
    status: str
    dependencies: Dict[str, str] 



# 设计优化接口
@optimize.post("/")
async def optimize_design(
    request: OptimizeRequest,
    authorization: str = Header(...)
):
    """
    设计优化接口
    
    接收CAD模型文件和优化参数，进行设计优化并返回结果
    """
    # 验证授权
    authenticate(authorization)
    
    # 模拟SSE流式响应生成器
    def optimization_stream():

        result = OptimizeResult(
            optimized_file = f"optimized_model.sldpart",
            best_params = [120.5, 60.2, 10.1, 25.3],
            final_volume = 0.00125,
            final_stress = 250000000,
            unit = {
                    "volume": "m³",
                    "stress": "Pa"
                },
            constraint_satisfied =  True
        )
        return result.model_dump_json()
    
    #return StreamingResponse(
    #    optimization_stream(),
    #    media_type="text/event-stream"
    #)
    return optimization_stream()


# 算法服务客户端
class AlgorithmClient:
    def __init__(self, 
                 base_url: str,
                 timeout: float = 30.0,
                 max_connections: int = 100
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=self.timeout,
            #limits=httpx.limits(max_connections=max_connections),
            headers={"Connection": "keep-alive"}
        )
        print("连接上算法服务端了：",self.client)
        self._is_closed = False
        self.websocket : Optional[websockets.WebSocketClientProtocol] = None
        self.websocket_task: Optional[asyncio.Task] = None
        self.status = None

    async def __aenter__(self):
        """支持异步上下文管理器进入"""
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """支持异步上下文管理器退出，确保连接关闭"""
        await self.close()

    @asynccontextmanager
    async def _request_context(self):
        """请求上下文管理器，确保异常情况下的资源处理"""
        if self._is_closed:
            raise RuntimeError("Client has been closed. Create a new instance.")
        
        try:
            yield
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Request to algorithm service timed out."
            )
        except httpx.HTTPError as e:
            # 根据不同错误类型细化异常处理
            if isinstance(e,(httpx.ConnectError, httpx.ConnectTimeout)):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Could not connect to service: {str(e)}"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"HTTP error occurred: {str(e)}"
            )
        except Exception as e:
            # 确保任何异常都不会导致资源泄漏
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unexpected error: {str(e)}"
            )

    async def check_health(self) -> HealthStatus:
        """
        检查算法服务的健康状态。
        返回一个 HealthStatus 实例，包含状态信息。
        """
        try:
            response = await self.client.get("/health")
            response.raise_for_status()
            return HealthStatus(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Algorithm service is unavailable: {str(e)}"
            )
        
    async def run_algorithm(self, request: AlgorithmRequest) -> TaskStatus:
        """调用算法服务的运行接口"""
        try:
            response = await self.client.post(
                "/run-algorithm",#"/submit-task",
                json=request.model_dump(),
            )
            response.raise_for_status()
            
            return TaskStatus(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error running algorithm: {str(e)}"
            )
    async def check_task_status(self, task_id, callback: Callable):
        try:
            while True:
                response = await self.client.get(
                    f"/task-status/{task_id}",
                    timeout=10  # 设置10秒超时
                )
                
                response.raise_for_status()

                data = response.json()
                try:
                    taskstatus = TaskStatus(**data)
                except Exception as e:
                    raise ValueError(f"服务端返回的数据格式不符合要求: {str(e)}")
                
                # 检查任务状态
                print(f"查询到任务{task_id}状态 {taskstatus.status}")
                if taskstatus.status == "running":
                    # 状态为运行中，调用回调函数
                    await callback()  # 如果回调是异步函数
                    # 或者：callback(task_status)  # 如果回调是同步函数
                    break  # 触发回调后退出轮询

                # 等待1秒后再次查询
                await asyncio.sleep(5)
        except Exception as e:
            if response.status_code == 404:
                raise ValueError(f"任务ID不存在: {task_id}") from e
            else:
                raise ValueError(f"查询失败，HTTP状态码: {response.status_code}") from e

    async def subscribe_to_task_start(self, task_id, callback: Callable):
        """
        订阅任务启动通知
        """

        # 构建WebSocket URL
        ws_protocol = "wss" if self.base_url.startswith("https") else "ws"
        base_ws_url = self.base_url.replace("http", ws_protocol, 1).rstrip("/")
        ws_url = f"{base_ws_url}/ws/{task_id}"
        print("ws_url: ", ws_url)
        try:
            # 连接WebSocket
            async with websockets.connect(ws_url) as websocket:
                self.websocket = websocket

            # 等待消息
            while True:
                try:
                    # 接收消息， 设置超时
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=10) # 10小时超时
                    data = json.loads(message)
                    print("收到websocker return:", data)

                    # 处理订阅确认
                    if data.get("status") == "subscribed" :
                        print(f"已成功订阅任务通知: 任务{task_id}")
                    # 处理任务启动通知
                    elif data.get("status") == "connected":
                        pass
                    elif data.get("status") == "running":
                        print(f"任务已启动: {task_id}")
                        await callback(data)  # 调用回调函数
                        break  # 收到启动通知后退出循环

                except asyncio.TimeoutError:
                    await self.websocket.send(json.dumps({"type": "ping"}))
                except websockets.exceptions.ConnectionClosed:
                    print(f"WebSocket连接已关闭: {task_id}")
                    break
        except Exception as e:
            print(f"WebSocket订阅出错: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error subscribing to task notifications: {str(e)}"
            )
        
    async def send_parameter(self, model_path: str,param: dict):
        """发送优化参数到算法服务"""
        try:

            with open(rf"{model_path}\parameters.txt", "w", encoding="utf-8") as f:
                json.dump(param, f)

            response = await self.client.post(
                "/sent_parameter",
                params={"model_path": model_path}
            )
            return response.json()
        except IOError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error writing parameters file: {str(e)}"
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error sending parameters: {str(e)}"
            )
        
    async def close(self):
        if self._is_closed:
            return
        """关闭 HTTP 客户端连接"""
        print("Closing AlgorithmClient connections...")
        if not self.client.is_closed:
            await self.client.aclose()

        # 关闭WebSocket连接
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()

        # 取消WebSocket任务
        if self.websocket_task and not self.websocket_task.done():
            self.websocket_task.cancel()
            
        self._is_closed = True


# 命令常量
class ControlCommand:
    INIT = 0
    PARAMS_READY = 1
    RESULT_READY = 2
    EXIT = 3
    CSERROR = -1
    PYERROR = -2

# 工具函数：读写文件
def read_key(file_path, key):
    """读取文件中指定键的值"""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"读取键值失败（{key}）：{e}")
    return None

def write_key(file_path, key, value):
    """写入键值对到文件"""
    lines = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f]

    found = False
    for i in range(len(lines)):
        if lines[i].startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

class ControlFileMonitor:
    """控制文件监视器，处理监听和错误处理逻辑"""
    def __init__(self, model_path:str, client):
        self.model_path = model_path
        self.control_file = os.path.join(os.path.dirname(model_path), "control.txt")
        self.client = client
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
        
    async def start_monitoring(self, completion_callback: Callable = None):
        self.running = True
        self.monitor_task = asyncio.create_task(
            self._monitor_loop(completion_callback)
        )
        return self.monitor_task
    
    async def _monitor_loop(self, completion_callback: Callable = None):
        """监听循环，定期检查控制文件状态"""
        try:
            while self.running:
                # 读取命令值
                print(f"control.txt url: {self.control_file}")
                command_str = read_key(self.control_file, "command")
                print(f"监听control.txt, command={command_str}")
                if not command_str:
                        await asyncio.sleep(1)  # 1秒后重试
                        continue
                
                if command_str in [str(ControlCommand.CSERROR), str(ControlCommand.PYERROR)]:
                    print(f"检测到致命错误（命令: {command_str}），终止任务")

                    # 写入EXIT命令终止依赖运行
                    write_key(self.control_file, "command", str(ControlCommand.EXIT))
                    
                    # 清理资源
                    # await self._cleanup_resources()

                    # 调用完成回调（如果有）
                    if completion_callback:
                        await completion_callback(False, f"任务失败: {command_str}")

                    self.running = False
                    break
                    
                elif command_str == str(ControlCommand.EXIT):
                    print(f"任务已正常退出: {self.model_path}")
                    
                    if completion_callback:
                        await completion_callback(True, "任务正常退出")
                    # await self._cleanup_resources()

                    self.running = False
                    break

                # 每秒检查一次
                await asyncio.sleep(1)
        except Exception as e:
            print(f"监听控制文件时出错: {str(e)}")
            if completion_callback:
                await completion_callback(False, f"监听错误: {str(e)}")
            await self._cleanup_resources()

    async def _cleanup_resources(self):
         
         
        """清理资源：关闭连接和客户端实例"""
        self.running = False
        print(f"清理任务资源: {self.model_path}")
        
        # 关闭客户端连接
        if self.client and not self.client._is_closed:
            await self.client.close()

        await self.stop_monitoring()
    async def stop_monitoring(self):
        """停止监听"""
        self.running = False
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                print("进入等待")
                # await self.monitor_task
                print("推出等待")
            except asyncio.CancelledError:
                print("关闭监听错误")

         # 无论任务是否存在，都清空引用
        self.monitor_task = None

# 工厂函数
def create_task_monitor_callback(model_path: str, client):
    """创建任务启动后的回调函数，用于开始监听控制文件"""
    if not isinstance(model_path, str) or not model_path.strip():
        raise ValueError("初始化时的model_path必须是有效的非空字符串")
    if not client:
        raise ValueError("client参数不能为空")
    async def task_start_callback(data: Optional[Dict] = None):
        if data and isinstance(data, dict):
            callback_model_path = data.get("model_path", model_path)
        else:
            callback_model_path = model_path  # data为空时直接使用初始路径
        
        try:
        
            monitor = ControlFileMonitor(model_path, client)

            # 定义任务完成后的处理
            async def on_completion(success: bool, message: str):
                print(f"任务处理完成: {message}")
                # 可以在这里添加后续处理逻辑，如通知用户等
            
            # 启动监听
            await monitor.start_monitoring(on_completion)
            print("回调函数里，监听结束了吗")
            return 
        except Exception as e:
            print(f"任务监控启动失败: {str(e)}")
    return task_start_callback