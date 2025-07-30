from typing import Optional, Dict, List

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import status
from fastapi import Header
from fastapi import Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pydantic import Field
from pydantic import validator, field_validator
from pydantic import ValidationError
from fastapi import Depends
import uuid
from datetime import datetime
from database.models_1 import Conversations
from core.authentication import get_current_active_user
from core.authentication import User

#from sse_starlette import StreamingResponse
import asyncio
import json 

geometry = APIRouter()

@geometry.get("/")
async def geometry_home():
    return {"message": "Geometry modeling home page"}




# 定义请求和响应模型
class ConversationCreateRequest(BaseModel):
    title: str = Field(..., max_length=100, description="新会话的标题")

class ConversationResponse(BaseModel):
    conversation_id: str
    user_id: int
    title: str
    created_at: datetime

    class Config:
        from_attributes = True # Pydantic V2, or orm_mode = True for V1

class FileItem(BaseModel):
    type: str = Field(..., description="文件类型（如 'image'）")
    transfer_method: str = Field(..., description="文件传输方式（如 'remote_url'）")
    url: str = Field(..., description="文件访问 URL")


# 响应模型
class GenerationMetadata(BaseModel):
    """生成结果的元数据模型，包含格式验证"""
    cad_file: str  # 生成的 CAD 模型文件下载地址（.step 格式）
    code_file: str  # 生成的参数化建模代码文件（.py 格式）
    preview_image: str  # 3D 模型预览图片（.png 格式）

    @field_validator('cad_file')
    def validate_cad_file(cls, v):
        # 验证文件扩展名
        if not v.lower().endswith('.step'):
            raise ValueError('CAD文件必须是.step格式')
        return v

    @field_validator('code_file')
    def validate_code_file(cls, v):
        if not v.lower().endswith('.py'):
            raise ValueError('代码文件必须是.py格式')
        return v

    @field_validator('preview_image')
    def validate_preview_image(cls, v):
        if not v.lower().endswith('.png'):
            raise ValueError('预览图片必须是.png格式') 
        return v

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
    metadata: GenerationMetadata


# 创建新会话的接口
@geometry.post("/conversation", response_model=ConversationResponse)
async def create_conversation(
    request: ConversationCreateRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    创建一个新的会话并将其存储在数据库中。
    """
    conversation_id = str(uuid.uuid4())
    conversation = await Conversations.create(
        conversation_id=conversation_id,
        user_id=current_user.user_id,
        title=request.title
    )
    return conversation
