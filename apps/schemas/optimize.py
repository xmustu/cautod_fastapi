from typing import Optional, Dict, List, Any, Union, Callable


from pydantic import BaseModel
from pydantic import Field
from pydantic import  field_validator


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


class AlgorithmRecommendation(BaseModel):
    """推荐算法项"""
    algorithm: str = Field(..., description="推荐算法名称，如 GA/PSO/DE")
    reason: Optional[str] = Field(None, description="推荐理由")
    score: Optional[float] = Field(None, description="推荐评分/置信度")


class AlgorithmRecommendRequest(BaseModel):
    """算法推荐请求"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_id: int = Field(..., description="任务ID")
    selected_params: Dict[str, Any] = Field(..., description="用户选择的优化参数")


class AlgorithmRecommendResponse(BaseModel):
    """算法推荐响应"""
    task_id: int
    recommendations: List[AlgorithmRecommendation]
    provider: Optional[str] = Field(None, description="推荐来源")


class OptimizationInitialParamsRequest(BaseModel):
    """获取初始参数请求"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_id: int = Field(..., description="任务ID")
    file_url: str = Field(..., description="上传的模型文件路径")
    simulation_type: Optional[str] = Field(default="StressSimulation", description="仿真类型")



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
