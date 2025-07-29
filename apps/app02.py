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
from database.models_1 import Conversations
from core.authentication import get_current_active_user
from core.authentication import User

#from sse_starlette import StreamingResponse
import asyncio
import json 

geometry = APIRouter()

@geometry.get("") 
async def geometry_home():
    return {"message": "Geometry modeling home page"}




# 定义请求模型
class FileItem(BaseModel):
    type: str = Field(..., description="文件类型（如 'image'）")
    transfer_method: str = Field(..., description="文件传输方式（如 'remote_url'）")
    url: str = Field(..., description="文件访问 URL")

class GeometryRequest(BaseModel):
    query: str = Field(..., description="用户自然语言描述（几何建模意图）")
    response_mode: str = Field("streaming", description="固定值 'streaming'，表示 SSE 流式响应模式")
    user: str = Field(..., description="用户唯一标识")
    conversation_id: Optional[str] = Field(None, description="会话 ID，用于多轮对话")
    inputs: Optional[Dict] = Field(None, description="附加参数（如长、宽、孔径等设计参数）")
    files: Optional[List[FileItem]] = Field(None, description="文件列表，用于上传参考图片或草图")

    @field_validator('response_mode')
    def response_mode_must_be_streaming(cls, v):
        """验证response_mode必须为streaming"""
        if v != "streaming":
            raise ValueError('response_mode must be "streaming"')
        return v

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

class SSETextChunk(BaseModel):
    event: str = "text_chunk"
    text: str

class SSEResponse(BaseModel):
    event: str = "message_end"
    answer: str  #输出描述文本
    metadata: GenerationMetadata


# 几何建模接口
@geometry.post("/")
async def geometry_modeling(
    request: GeometryRequest,
    current_user: User = Depends(get_current_active_user)
):
    # 认证已由 Depends(get_current_active_user) 自动处理
    
    # 验证response_mode是否为streaming
    if request.response_mode != "streaming":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="response_mode must be 'streaming'"
        )

    # 处理会话 ID
    conversation_id = request.conversation_id or str(uuid.uuid4())

    # 获取或创建会话
    conversation, created = await Conversations.get_or_create(
        conversation_id=conversation_id,
        defaults={"user_id": current_user.user_id, "title": request.query}
    )
    
    # 模拟SSE流式响应生成器
    async def stream_generator():
        # 首先发送会话信息
        conversation_info_data = SSEConversationInfo(conversation_id=conversation_id)
        sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
        yield sse_conv_info

        full_answer = "已根据您的需求生成带孔矩形零件，尺寸符合设计要求。"
        
        # 1. 模拟流式发送文本块
        for i in range(0, len(full_answer), 5): # 一次发送5个字符
            chunk = full_answer[i:i+5]
            text_chunk_data = SSETextChunk(text=chunk)
            sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
            yield sse_chunk
            await asyncio.sleep(0.05) # 模拟AI思考的延迟

        # 2. 发送包含完整元数据的结束消息
        final_response_data = SSEResponse(
            answer=full_answer,
            metadata=GenerationMetadata(
                cad_file="https://example.com/generated_model.step",
                code_file="https://example.com/parametric_model.py",
                preview_image="https://example.com/preview_image.png" # 使用一个符合.png格式的URL进行测试
            )
        )
        
        sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
        yield sse_final

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream"
    )
