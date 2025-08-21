from typing import Optional, Dict, List, Any

from fastapi import APIRouter
from fastapi import Header
from pydantic import BaseModel
from pydantic import Field
from fastapi import Form
from pydantic import  field_validator

from core.authentication import authenticate

import httpx
from fastapi import status, HTTPException
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

class OptimizationParamsRequest(BaseModel):
    """接收优化参数的请求体模型"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_id: int = Field(..., description="任务ID")
    params: Dict[str, Dict[str, float]] = Field(..., description="优化参数及其范围，例如 {'param1': {'min': 0.1, 'max': 1.0}}")


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
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url)

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
                "/run-algorithm",
                json=request.model_dump(),
            )
            response.raise_for_status()
            return TaskStatus(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error running algorithm: {str(e)}"
            )
        
    async def send_parameter(self, model_path: str,param: dict):
        """发送优化参数到算法服务"""
        try:

            with open(rf"{model_path}\parametes.txt", "w", encoding="utf-8") as f:
                f.write(str(param))

            response = await self.client.post(
                "/sent_parameter",
                params={"model_path": model_path}
            )
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error sending parameters: {str(e)}"
            )
        
    async def close(self):
        """关闭 HTTP 客户端连接"""
        await self.client.aclose()
