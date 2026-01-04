from typing import Optional, Dict, List, Any, Union, Callable, Set
import json
import os
from datetime import datetime

from fastapi import APIRouter
from fastapi import Header
from pydantic import BaseModel
from pydantic import Field
from fastapi import Form
from pydantic import  field_validator

import httpx
from fastapi import status, HTTPException
from contextlib import asynccontextmanager

import asyncio

from pathlib import Path

from config import settings
from core.authentication import authenticate
from core.authentication import User
from database.models import Tasks
from database.models import OptimizationResults
from apps.routes.chat import  save_or_update_message_in_redis
from apps.schemas import Message
from apps.schemas import (
    OptimizeRequest,
    UnitInfo,
    OptimizeResult,
    TaskStatus,
    HealthStatus
)
from apps.schemas import (
    TaskExecuteRequest,
    GenerationMetadata,
    SSEConversationInfo,
    SSETextChunk,
    SSEResponse,
    PartData,
    SSEPartChunk,
    SSEImageChunk
)

import redis.asyncio as redis_async

optimize = APIRouter()

# 新的优化配置模型（与服务端对应）
class GetInitialParametersRequest(BaseModel):
    """获取初始参数请求模型"""
    task_id: str = Field(..., description="任务ID，用于跟踪")
    model_path: str = Field(..., description="SolidWorks模型路径")
    simulation_type: str = Field(default='StressSimulation', description="仿真类型: StressSimulation 或 FlowSimulation")
    exe_path: Optional[str] = Field(default=None, description="sldxunhuan.exe路径,None则自动查找")


class OptimizationConfig(BaseModel):
    """优化配置模型"""
    task_id: str = Field(..., description="任务ID，用于跟踪")
    model_path: str = Field(..., description="SolidWorks模型路径")
    simulation_type: str = Field(default='StressSimulation', description="仿真类型: StressSimulation 或 FlowSimulation")
    population_size: int = Field(default=10, ge=1, le=100, description="种群大小")
    num_generations: int = Field(default=10, ge=1, le=100, description="进化代数")
    
    # 参数边界（具体数值，而非系数）
    lower_bounds: Dict[str, float] = Field(..., description="参数下界字典 {'param_name': lower_value}")
    upper_bounds: Dict[str, float] = Field(..., description="参数上界字典 {'param_name': upper_value}")
    
    # 应力仿真专用参数
    max_stress: Optional[float] = Field(default=2.5e8, description="最大应力约束(Pa), 仅StressSimulation使用")
    
    # 流体仿真专用参数
    max_volume: Optional[float] = Field(default=None, description="最大体积约束(m³), 仅FlowSimulation使用")
    goal_name: str = Field(default="GG 平均值 温度（固体） 21", description="Flow仿真目标名称")
    
    # 优化方法（占位符，后续扩展）
    optimization_method: Optional[str] = Field(default="GA", description="优化方法: GA, PSO, DE等（占位符）")
    
    # 可选配置
    exe_path: Optional[str] = Field(default=None, description="sldxunhuan.exe路径,None则自动查找")
    seed: Optional[int] = Field(default=None, description="随机种子,None则使用时间戳")


class GenerationData(BaseModel):
    """单代优化数据"""
    generation: int
    rank: int
    fitness: float
    cv: float  # 约束违反度
    params: List[float]
    timestamp: str


class OptimizationProgress(BaseModel):
    """优化进度响应"""
    task_id: str
    status: str
    total_generations: int
    current_generation: int
    data: List[GenerationData]


async def optimize_stream_generator(
        request: TaskExecuteRequest,
        current_user: User,
        redis_client,
        combinde_query,
        task: Tasks
):
    """
    新的优化流式生成器，使用新的服务端接口
    流程：
    1. 保存初始消息
    2. 发送会话和任务信息
    3. 准备模型路径和优化结果记录
    4. 创建算法客户端并检查健康状态
    5. 获取初始参数
    6. 返回参数给前端
    7. 等待前端提交参数后，在 /optimize/progress/{task_id} 中启动优化任务
    """
    assistant_message = Message(
        role="assistant",
        content="",
        timestamp=datetime.now(),
        parts=[],
        metadata={},
        status="in_progress"
    )
    
    algorithm_client = None
    try:
        # 1. 立即保存初始的 "in_progress" 消息
        await save_or_update_message_in_redis(
            user_id=current_user.user_id,
            task_id=request.task_id, 
            task_type=request.task_type,
            conversation_id=request.conversation_id, 
            message=assistant_message, 
            redis_client=redis_client
        )

        # 2. 发送会话和任务信息
        conversation_info_data = SSEConversationInfo(
            conversation_id=request.conversation_id, 
            task_id=str(request.task_id)
        )
        sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
        yield sse_conv_info

        # 3. 准备模型路径和优化结果记录
        model_path = rf"{request.file_url}" if request.file_url else r".\AutoFrame.SLDPRT"
        print("optimize model_path: ", model_path)

        # 初始化或更新优化结果记录
        optimize_result = await OptimizationResults.get_or_none(task_id=task.task_id)
        print("找到优化结果吗？", optimize_result)
        update_data = {
            "optimized_cad_file_path": model_path,  
        }
        if optimize_result:
            await optimize_result.update_from_dict(update_data).save()
        else:
            optimize_result = await OptimizationResults.create(
                task_id=task.task_id,
                **update_data
            )
        print("优化结果: ", optimize_result)
        await optimize_result.save()

        # 4. 创建算法客户端并检查健康状态
        algorithm_client = AlgorithmClient(base_url=settings.OPTIMIZE_API_URL)
        health_status = await algorithm_client.check_health()
        if health_status.status != "healthy":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Algorithm service is not healthy."
            )

        # 5. 获取初始参数
        task_id_str = str(task.task_id)
        initial_params_request = GetInitialParametersRequest(
            task_id=task_id_str,
            model_path=model_path,
            simulation_type="StressSimulation"  # 默认，可以从 query 或其他来源获取
        )
        
        initial_params_result = await algorithm_client.get_initial_parameters(initial_params_request)
        initial_parameters = initial_params_result.get("initial_parameters", {})
        
        print(f"获取到初始参数: {len(initial_parameters)} 个")
        
        # 6. 返回参数给前端（通过SSE发送）
        # 将初始参数转换为适合前端的格式
        params_text = "获取到以下初始参数，请设置优化范围：\n\n"
        for param_name, param_value in initial_parameters.items():
            params_text += f"- {param_name}: {param_value:.8f}m\n"
        
        assistant_message.content += params_text
        assistant_message.timestamp = datetime.now()
        
        # 发送参数信息
        text_chunk_data = SSETextChunk(text=params_text)
        yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
        
        # 发送初始参数数据（用于前端表单填充）
        params_event_data = {
            "event": "initial_parameters",
            "task_id": task_id_str,
            "parameters": initial_parameters
        }
        yield f'event: initial_parameters\ndata: {json.dumps(params_event_data, ensure_ascii=False)}\n\n'
        
        # 更新Redis中的消息
        await save_or_update_message_in_redis(
            user_id=current_user.user_id,
            task_id=request.task_id,
            task_type=request.task_type,
            conversation_id=request.conversation_id,
            message=assistant_message,
            redis_client=redis_client
        )
        
        # 提示前端提交参数
        prompt_text = "\n请在前端设置优化参数范围，然后提交参数以开始优化任务。\n"
        assistant_message.content += prompt_text
        assistant_message.timestamp = datetime.now()
        
        text_chunk_data = SSETextChunk(text=prompt_text)
        yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
        
        await save_or_update_message_in_redis(
            user_id=current_user.user_id,
            task_id=request.task_id,
            task_type=request.task_type,
            conversation_id=request.conversation_id,
            message=assistant_message,
            redis_client=redis_client
        )
        
        # 发送结束事件（第一阶段完成，等待参数提交）
        final_metadata = GenerationMetadata(
            cad_file=model_path,
            code_file="",
            preview_image=None
        )
        final_response_data = SSEResponse(
            answer=assistant_message.content,
            metadata=final_metadata
        )
        sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
        yield sse_final
        
        # 更新任务状态为等待参数
        task.status = "waiting_params"
        await task.save()

    except Exception as e:
        task.status = "failed"
        await task.save()
        print(f"Error during initial parameters retrieval: {e}")
        
        if algorithm_client:
            try:
                await algorithm_client.close()
            except:
                pass
            
        assistant_message.content += f"\n\n**获取初始参数出错**: {e}"
        assistant_message.status = "failed"
        assistant_message.timestamp = datetime.now()
        
        try:
            await save_or_update_message_in_redis(
                user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
            )
        except Exception as redis_err:
            print(f"Error saving error message to Redis: {redis_err}")

        error_data = json.dumps({"error": "An error occurred during initial parameters retrieval."})
        yield f'event: error\ndata: {error_data}\n\n'


@optimize.get("")
async def optimize_home():
    return {"message": "Design optimization home page"}


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
    
    return optimization_stream()


# 新的算法服务客户端
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
            headers={"Connection": "keep-alive"}
        )
        print("连接上算法服务端了：",self.client)
        self._is_closed = False

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
    
    async def get_initial_parameters(self, request: GetInitialParametersRequest) -> Dict[str, Any]:
        """获取模型初始参数值"""
        try:
            response = await self.client.post(
                "/get-initial-parameters",
                json=request.model_dump()
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error getting initial parameters: {str(e)}"
            )
    
    async def start_optimization(self, config: OptimizationConfig) -> TaskStatus:
        """启动优化任务"""
        try:
            response = await self.client.post(
                "/start-optimization",
                json=config.model_dump()
            )
            response.raise_for_status()
            return TaskStatus(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error starting optimization: {str(e)}"
            )
    
    async def get_optimization_status(self, task_id: str) -> TaskStatus:
        """查询任务状态"""
        try:
            response = await self.client.get(f"/optimization-status/{task_id}")
            response.raise_for_status()
            return TaskStatus(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error getting optimization status: {str(e)}"
            )
    
    async def get_optimization_progress(self, task_id: str, limit: int = 100) -> OptimizationProgress:
        """获取优化进度数据"""
        try:
            response = await self.client.get(
                f"/optimization-progress/{task_id}",
                params={"limit": limit}
            )
            response.raise_for_status()
            return OptimizationProgress(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error getting optimization progress: {str(e)}"
            )
    
    async def get_optimization_result(self, task_id: str) -> Dict[str, Any]:
        """获取最终优化结果"""
        try:
            response = await self.client.get(f"/optimization-result/{task_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error getting optimization result: {str(e)}"
            )
        
    async def close(self):
        """关闭 HTTP 客户端连接"""
        if self._is_closed:
            return
        print("Closing AlgorithmClient connections...")
        if not self.client.is_closed:
            await self.client.aclose()
        self._is_closed = True


# 兼容性函数（新接口不再使用控制文件，但保留以兼容旧代码）
def write_key(file_path, key, value):
    """写入键值对到文件（兼容性函数，新接口不再使用）"""
    try:
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
    except Exception as e:
        print(f"write_key failed (compatibility function): {e}")


def read_key(file_path, key):
    """读取文件中指定键的值（兼容性函数）"""
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
