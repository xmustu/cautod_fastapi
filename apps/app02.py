from typing import Optional, Dict, List, AsyncGenerator, Union, List, Literal,Any

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
from pydantic import HttpUrl
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
import httpx
import os
import aiohttp
import redis.asyncio as aioredis
from pathlib import Path
from config import Settings

settings = Settings()

geometry = APIRouter()

# 请求模型
class FileItem(BaseModel):
    type: str = Field(..., description="文件类型（如 'image'）")
    transfer_method: str = Field(..., description="文件传输方式（如 'remote_url'）") 
    url: str = Field(..., description="文件访问 URL") # 仅当传递方式为 remote_url 时

class MessageRequest(BaseModel):
    inputs: object
    query: str
    response_mode: Optional[str] = "streaming"  # 目前仅支持 streaming
    conversation_id: Optional[str] = None
    user: Optional[str] = "abc-123"  # 用户标识符
    files: Optional[List[FileItem]] = None
    auto_generate_name: Optional[bool] = False

# 响应模型
# ------------------ 各事件体 ------------------
class MessageChunk(BaseModel):
    event: Literal["message"]
    task_id: str
    message_id: str
    conversation_id: str
    answer: str
    created_at: int

class MessageFileChunk(BaseModel):
    event: Literal["message_file"]
    id: str
    type: Literal["image"]
    belongs_to: Literal["assistant"]
    url: str
    conversation_id: str

class MessageEndChunk(BaseModel):
    event: Literal["message_end"]
    task_id: str
    message_id: str
    conversation_id: str
    metadata: dict

# class TTSMessageChunk(BaseModel):
#     event: Literal["tts_message"]
#     task_id: str
#     message_id: str
#     audio: str  # base64 mp3
#     created_at: int

# class TTSMessageEndChunk(BaseModel):
#     event: Literal["tts_message_end"]
#     task_id: str
#     message_id: str
#     audio: str = ""  # empty
#     created_at: int

class MessageReplaceChunk(BaseModel):
    event: Literal["message_replace"]
    task_id: str
    message_id: str
    conversation_id: str
    answer: str
    created_at: int

class WorkflowStartedChunk(BaseModel):
    event: Literal["workflow_started"]
    task_id: str
    workflow_run_id: str
    data: dict

class NodeStartedChunk(BaseModel):
    event: Literal["node_started"]
    task_id: str
    workflow_run_id: str
    data: dict

class NodeFinishedChunk(BaseModel):
    event: Literal["node_finished"]
    task_id: str
    workflow_run_id: str
    data: dict

class WorkflowFinishedChunk(BaseModel):
    event: Literal["workflow_finished"]
    task_id: str
    workflow_run_id: str
    data: dict

class ErrorChunk(BaseModel):
    event: Literal["error"]
    task_id: str
    message_id: str
    status: int
    code: str
    message: str

class PingChunk(BaseModel):
    event: Literal["ping"]

# ------------------ 联合模型 ------------------
StreamChunk = Union[
    MessageChunk,
    MessageFileChunk,
    MessageEndChunk,
    # TTSMessageChunk,
    # TTSMessageEndChunk,
    MessageReplaceChunk,
    WorkflowStartedChunk,
    NodeStartedChunk,
    NodeFinishedChunk,
    WorkflowFinishedChunk,
    ErrorChunk,
    PingChunk,
]

class ChunkChatCompletionResponse(BaseModel):
    """SSE 流式块"""
    chunk: StreamChunk





# 依赖项：获取Dify API客户端
async def get_dify_client():
    async with httpx.AsyncClient(base_url=settings.DIFY_API_BASE_URL) as client:
        client.headers.update({
            "Authorization": f"Bearer {settings.DIFY_API_KEY}",
            "Content-Type": "application/json"
        })
        yield client

# dift 客户端
class DifyClient:
    def __init__(self,api_key: str, base_url: str, user_id: int, task_id: int,redis_client:aioredis.Redis,):
        self.api_key = api_key
        self.base_url = base_url
        self.user_id = user_id
        self.task_id = task_id
        self.redis = redis_client
        self.headers =  {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Host': 'localhost',
            'Connection': 'keep-alive'
        }

    async def chat_stream(self, request: MessageRequest):
        """发送聊天请求并处理流式响应"""
        #print("request: ",request.model_dump())
        url = f"{self.base_url}/v1/chat-messages"
        payload = json.dumps(request.model_dump())

        # 如果没有提供会话ID，则在接下来记住会话ID
        FLAG = False
        if request.conversation_id is None:
            FLAG = True
        #print("请求的URL:", url)  # Debug log
        #print("请求的payload:", payload)  # Debug log
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=self.headers) as response:
                #print("响应状态码:", response.status)  # Debug log
                if response.status != 200:
                    error_detail = await response.text()
                    raise HTTPException(
                        status_code=response.status, 
                        detail=f"Dify API error: {error_detail}"
                    )
                # 处理流式响应
                async for line in response.content:
                    
                    # 处理SSE格式 (data: ...)
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue 
                    if line.startswith('data: '):
                        data_str = line[len('data: '):]


                    try:
                        data = json.loads(data_str)
                        # 根据event类型解析为对应的模型
                        #chunk = self._parse_chunk(data)
                        if FLAG:
                            self.add_conversation_id(data["conversation_id"])
                            FLAG = False
                        if data["event"] == "message":
                            if "answer" in data:
                                #text_chunk = SSETextChunk(event="text_chunk", text=chunk.answer)
                                #sse_chunk = f'event: text_chunk\ndata: {text_chunk.model_dump_json()}\n\n'
                                yield data["answer"]
                    except Exception as e:
                         #yield f"event: error\ndata: {'message': f'解析响应失败: {str(e)}'}\n\n"
                        yield f"解析响应失败: {str(e)}"
                    await asyncio.sleep(0.05)

    async def add_conversation_id(self,conversation_id: str):

        def get_user_task_key(user_id: str) -> str:
            """获取用户任务列表在Redis中的键名"""
            return f"user_tasks:{user_id}"

        user_task_key = get_user_task_key(self.user_id)
        task_json = await self.redis.hget(user_task_key, self.task_id)
        if task_json is None:
            raise RuntimeError("task not found")

        task_info = json.loads(task_json)
        task_info["dify_chat_conversation_id"] = conversation_id   # 这里修改

        await self.redis.hset(user_task_key, self.task_id, json.dumps(task_info))


    # 解析不同类型的SSE事件
    def _parse_chunk(self, data: Dict[str, Any]) -> StreamChunk:
        """根据event类型解析数据到对应的模型"""
        event_type = data.get('event')
        print("解析的事件类型:", event_type)  # Debug log
        chunk_map = {
            'message': MessageChunk,
            'message_file': MessageFileChunk,
            'message_end': MessageEndChunk,
            'message_replace': MessageReplaceChunk,
            'workflow_started': WorkflowStartedChunk,
            'node_started': NodeStartedChunk,
            'node_finished': NodeFinishedChunk,
            'workflow_finished': WorkflowFinishedChunk,
            'error': ErrorChunk,
            'ping': PingChunk
        }
        
        chunk_class = chunk_map.get(event_type)
        if not chunk_class:
            raise ValueError(f"未知的事件类型: {event_type}")
        print("解析的事件数据:", chunk_class(**data))  # Debug log
        return chunk_class(**data)
    

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

    # 获取当前目录的上一级目录
    parent_dir = Path(os.getcwd())
    
    # 构建目标目录路径：上一级目录/files/会话ID
    conversation_dir = parent_dir / "files" / conversation_id
    
    try:
        # 创建目录（包括所有必要的父目录）
        conversation_dir.mkdir(parents=True, exist_ok=True)
        print(f"成功创建会话目录: {conversation_dir}")
    except Exception as e:
        print(f"创建会话目录失败: {e}")
        raise
    return conversation
