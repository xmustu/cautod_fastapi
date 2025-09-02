
from typing import Optional, Dict, List, AsyncGenerator, Union, List, Literal,Any
from datetime import datetime

from pydantic import BaseModel, Field
from pydantic import field_validator

from .common import FileItem
from .geometry import SuggestedQuestionsResponse




class TaskOut(BaseModel):
    """任务输出模型"""
    task_id: int
    task_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class TaskCreateRequest(BaseModel):
    """创建新任务的请求体模型"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_type: str = Field(..., description="任务类型 (e.g., 'geometry', 'retrieval')")
    details: Optional[Dict[str, Any]] = Field(None, description="与任务相关的附加信息")

class TaskCreateResponse(BaseModel):
    """创建新任务的响应体模型"""
    task_id: int
    conversation_id: str
    user_id: int
    task_type: str
    status: str

    class Config:
        from_attributes = True

class TaskExecuteRequest(BaseModel):
    """执行任务的请求体模型"""
    task_id: int = Field(..., description="要执行的任务ID")
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_type: str = Field(..., description="任务类型，用于后端路由")
    query: Optional[str] = Field(None, description="用户的文本输入")
    file_url: Optional[str] = Field(None, description="上传文件的URL")
    files: Optional[List[FileItem]] = Field(None, description="文件列表")

class PendingTaskResponse(BaseModel):
    """待处理任务的响应体模型"""
    task_id: int
    task_type: str
    created_at: datetime
    conversation_title: str

    class Config:
        from_attributes = True




# 生成结果响应模型
class GenerationMetadata(BaseModel):
    """生成结果的元数据模型，包含格式验证"""
    cad_file: Optional[str] = None  # 生成的 CAD 模型文件下载地址（.step 格式）
    code_file: Optional[str] = None  # 生成的参数化建模代码文件（.py 格式）
    stl_file: Optional[str] = None
    preview_image: Union[str, None]  # 3D 模型预览图片（.png 格式）

    @field_validator('cad_file')
    def validate_cad_file(cls, v):
        # 验证文件扩展名
        if v and not v.lower().endswith('.step') and not v.lower().endswith('.sldprt'):
            raise ValueError('CAD文件必须是.step或者.sldprt格式')
        return v

    @field_validator('code_file')
    def validate_code_file(cls, v):
        if v and not v.lower().endswith('.py'):
            raise ValueError('代码文件必须是.py格式')
        return v

    @field_validator('preview_image')
    def validate_preview_image(cls, v):
        #仅当 v 是一个非空字符串时才进行验证
        if v and not v.lower().endswith('.png'):
            raise ValueError('预览图片必须是.png格式') 
        return v

# ------- SSE 传输相关 Pydantic模型 ----------
class SSEConversationInfo(BaseModel):
    event: str = "conversation_info"
    conversation_id: str
    task_id: str # 任务ID也应在任务开始时告知前端

class SSETextChunk(BaseModel):
    event: str = "text_chunk"
    text: str

class SSEResponse(BaseModel):
    event: str = "message_end"
    answer: str  #输出描述文本
    suggested_questions: Optional[SuggestedQuestionsResponse] = None  # 新增：建议问题列表
    metadata: GenerationMetadata

# --- 新增：用于零件检索的SSE模型 ---
class PartData(BaseModel):
    """单个零件的数据模型"""
    id: int
    name: str
    imageUrl: str
    fileName: str

class SSEPartChunk(BaseModel):
    """用于通过SSE流式传输零件数据的模型"""
    event: str = "part_chunk"
    part: PartData

class SSEImageChunk(BaseModel):
    """用于通过SSE流式传输单个图片URL的模型"""
    event: str = "image_chunk"
    imageUrl: str
    fileName: str
    altText: Optional[str] = None