from typing import Optional, Dict, List, AsyncGenerator, Union

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
import http.client
import json

geometry = APIRouter()


# 调用dify的API进行几何建模
async def geometry_dify_api(query: str) -> AsyncGenerator:
   # 连接本地服务，使用Dify默认端口5001（根据实际情况修改）
   conn = http.client.HTTPConnection("127.0.0.1",8000)

   payload = json.dumps({
      "inputs": {},
      "query": query,
      "response_mode": "streaming",
      "conversation_id": "",
      "user": "abc-123"
   })

   headers = {
      'Authorization': 'Bearer app-JBlZJUfwVvBguF3ngZlQMluL',
      'Content-Type': 'application/json',
      'Accept': '*/*',
      'Host': 'localhost',
      'Connection': 'keep-alive'
      # 已移除User-Agent字段
   }

   conn.request("POST", "/v1/chat-messages", payload, headers)
   res = conn.getresponse()
   
   if res.status != 200:
       yield f"错误： Dify服务返回状态 {res.status} {res.reason}"
       return
   print("连上了吗")
   # 处理流式响应
   full_answer = []
   for line in res:
       line_str = line.decode('utf-8').strip()
       if not line_str:
           continue 
       
       if line_str.startswith("data: "):
               
           data_part = line_str[len("data: "):]
        
           
           
           json_data = json.loads(data_part)
           if json_data['event'] == "message":
                
                if "answer" in json_data:

                    chunk = json_data['answer']
                    yield chunk
                    
                    full_answer.append(chunk)



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
    preview_image: Union[str, None]  # 3D 模型预览图片（.png 格式）

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
        #仅当 v 是一个非空字符串时才进行验证
        if v and not v.lower().endswith('.png'):
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
