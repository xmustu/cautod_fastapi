from typing import Optional, Dict, List, Any

from fastapi import APIRouter
from fastapi import Header
from pydantic import BaseModel
from pydantic import Field
from fastapi import Form
from pydantic import  field_validator

from core.authentication import authenticate



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


