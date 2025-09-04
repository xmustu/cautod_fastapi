from typing import Optional, Dict, List, AsyncGenerator, Union, List, Literal,Any
from datetime import datetime
import json 
import http.client
import httpx
import os

import aiohttp
from pathlib import Path
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Depends
import uuid
import asyncio
from database.models import Conversations
from core.authentication import get_current_active_user
from core.authentication import User
from database.models import Tasks
from apps.chat import save_or_update_message_in_redis
from database.models import Tasks, Conversations, GeometryResults


from config import settings

from apps.schemas import FileItem
from apps.schemas import Message
from apps.schemas import MessageRequest
from apps.schemas import (
    ConversationCreateRequest,
    ConversationResponse,
    ConversationOut
)
from apps.schemas import (
    MessageChunk,
    MessageFileChunk,
    MessageEndChunk,
    MessageReplaceChunk,
    WorkflowStartedChunk,
    NodeStartedChunk,
    NodeFinishedChunk,
    WorkflowFinishedChunk,
    ErrorChunk,
    PingChunk,
    StreamChunk,
    ChunkChatCompletionResponse,
    SuggestedQuestionsResponse
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



geometry = APIRouter()



async def geometry_stream_generator(
        request: TaskExecuteRequest,
        current_user: User,
        redis_client,
        combinde_query,
        task: Tasks
):
    # 初始化一个内存中的助手消息对象
    assistant_message = Message(
        role="assistant",
        content="",
        timestamp=datetime.now(),
        parts=[],
        metadata={},
        status="in_progress"
    )
    try:
        # 1. 立即保存初始的 "in_progress" 消息
        await save_or_update_message_in_redis(
            user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
            conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
        )
        # 2. 发送会话和任务信息
        conversation_info_data = SSEConversationInfo(conversation_id=request.conversation_id, task_id=str(request.task_id))
        sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
        yield sse_conv_info

        # markdownsign ="```"
        # yield f'event: text_chunk\ndata: {SSETextChunk(text=markdownsign).model_dump_json()}\n\n'
        # greetings = "请耐心等待，正在检索数据库...\n"
        # yield f'event: text_chunk\ndata: {SSETextChunk(text=greetings).model_dump_json()}\n\n'
        # 前端测试案例
        # 1. 模拟流式发送文本块
        # full_answer = ""
        # FILE_PATH = r"D:\else\CAutoD_SoftWare\temp\cautod_fastapi\files\test_example.txt"
        # with open(FILE_PATH, "rb") as f:
        #     full_answer = f.read().decode("utf-8")
        # for i in range(0, len(full_answer), 5):
        #     chunk = full_answer[i:i+5]
        #     text_chunk_data = SSETextChunk(text=chunk)
        #     sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
        #     yield sse_chunk
        #     await asyncio.sleep(0.05)



        # 3. 连接dify chat-messsage, 处理流式回复
        client = DifyClient(
            api_key=settings.DIFY_API_KEY,
            base_url=settings.DIFY_API_BASE_URL,
            task_id=request.task_id,
            task_instance = task
            )
        
        dify_request = MessageRequest(
            inputs={},
            query=combinde_query,
            response_mode= "streaming",
            conversation_id=task.dify_conversation_id,
            #files= [],
            #auto_generate_name= True,  # 自动生成文件名
        )

        
        full_answer = []
        async for chunk in client.chat_stream(dify_request):
            
            # 关键：将字符串中的 \n 转义符替换为真正的换行控制字符
            formatted_chunk = chunk.replace("\\n", "\n")

            assistant_message.content += chunk
            assistant_message.timestamp = datetime.now()

            text_chunk_data = SSETextChunk(text=formatted_chunk)
            sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
            
            yield sse_chunk
            await save_or_update_message_in_redis(
                user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
            )

            #await asyncio.sleep(0.05)
            full_answer.append(chunk)

        # markdownsign ="```"
        # yield f'event: text_chunk\ndata: {SSETextChunk(text=markdownsign).model_dump_json()}\n\n'
        # 获取建议问题
        suggested_questions = await client.Next_Suggested_Questions()



        # # 查询是否有建模结果
        # geometry_result = await GeometryResults.get_or_none(task_id=task.task_id)

        
        # # 4. 流式发送预览图
        # if geometry_result:

        #     preview_image_path = geometry_result.preview_image_path if geometry_result.preview_image_path else r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\yuanbao.png"
        #     if os.path.exists(preview_image_path):
        #         imgage_file_name = os.path.basename(preview_image_path)
        #         image_url = f"{imgage_file_name}" # 修正：指向 /files 路由

        #         image_part = {"type": "image", "imageUrl": image_url, "fileName": imgage_file_name, "altText": "几何建模预览图"}
        #         assistant_message.parts.append(image_part)
        #         assistant_message.timestamp = datetime.now()

        #         image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=imgage_file_name, altText="几何建模预览图")
        #         yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'

        #         await save_or_update_message_in_redis(
        #             user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
        #             conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
        #         )

        #         await asyncio.sleep(0.1)
            
            #image_parts_for_redis.append({"type": "image", "imageUrl": image_url, "fileName": imgage_file_name, "altText": "几何建模预览图"})

        # 4. 发送包含完整元数据的结束消息
        geometry_result = await GeometryResults.get_or_none(task_id=task.task_id)
        if geometry_result:
            final_metadata = GenerationMetadata(
                    cad_file="model.step",
                    stl_file="model.stl",
                    code_file="script.py",

                    preview_image="Oblique_View.png"
            )

            # 5. 通知前端展示预览图
            image_file_name = "Oblique_View.png"

            # 定义路径片段
            base_dir = Path(settings.STATIC_URL) if settings.STATIC_URL else Path("/files")
            # 用 "/" 拼接路径
            image_url = rf"{base_dir}/{request.conversation_id}/{request.task_id}/{image_file_name}"
            #image_url = os.path.join("/files", str(request.conversation_id), str(task.task_id), imgage_file_name)
            print("image_url: ", image_url)
            image_part = {"type": "image", "imageUrl": image_url, "fileName": image_file_name, "altText": "几何建模预览图"}
            assistant_message.parts.append(image_part)
            assistant_message.timestamp = datetime.now()

            image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=image_file_name, altText="几何建模预览图")
            print("几何建模预览图: ",image_url)
            yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'

            await save_or_update_message_in_redis(
                user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
            )

            await asyncio.sleep(0.1)

        else:
            final_metadata = GenerationMetadata(
                cad_file=None,
                code_file=None,
                stl_file=None,
                preview_image=None
            )

        assistant_message.metadata = final_metadata.model_dump()


        final_response_data = SSEResponse(
            answer=''.join(full_answer),
            suggested_questions=suggested_questions,
            metadata=final_metadata
        )
        
        sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
        yield sse_final


        # 6. 保存结构化的助手消息到Redis,最后一次更新Redis，状态为 "done"
        assistant_message.status = "done"
        assistant_message.timestamp = datetime.now()
        await save_or_update_message_in_redis(
            user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
            conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
        )

        # 7. 数据库操作，保存任务状态，建模结果
        task.status = "done"
        await task.save()
        
        # 保存几何建模在mcp中进行
        # geometry_result = await GeometryResults.get_or_none(task_id=task.task_id)
        
        # update_data = {
        #     "cad_file_path" : f"{file_name}.step",
        #     "code_file_path" : f"{file_name}.py",
        #     "preview_image_path" : None
        # }
        # if geometry_result:
        #     # 如果存在则更新
        #     await geometry_result.update_from_dict(update_data).save()
        # else:
        #     # 如果不存在则创建
        #     geometry_result = await GeometryResults.create(
        #         task_id=task.task_id,** update_data
        #     )

        # await geometry_result.save()
    except Exception as e:
        # 任务失败，更新状态
        task.status = "failed"
        await task.save()
        # 可以选择性地记录错误日志
        print(f"Error during task execution: {e}")

        # 更新Redis中的消息状态为 "failed"
        assistant_message.content += f"\n\n**任务执行出错**: {e}"
        assistant_message.status = "failed"
        assistant_message.timestamp = datetime.now()
        await save_or_update_message_in_redis(
            user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
            conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
        )

        # 向客户端发送错误事件
        error_data = json.dumps({"error": "An error occurred during task execution."})
        yield f'event: error\ndata: {error_data}\n\n'
    

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
    def __init__(self,api_key: str, base_url: str, task_id: int, task_instance: "Tasks"):
        self.api_key = api_key
        self.base_url = base_url
        self.task_id = task_id
        self.task_instance = task_instance  # 任务实例
        self.last_message_id = None
        self.headers =  {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Host': 'localhost',
            'Connection': 'keep-alive'
        }

    async def chat_stream(self, request: MessageRequest):
        """发送聊天请求并处理流式响应"""

        url = f"{self.base_url}/v1/chat-messages"
        payload = json.dumps(request.model_dump())
        FLAG = True

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
                            FLAG = False

                            await self.add_conversation_id(data["conversation_id"])
                            self.last_message_id = data["message_id"]
                            FLAG = False

                        if data["event"] == "message":
                            if "answer" in data:
                                #text_chunk = SSETextChunk(event="text_chunk", text=chunk.answer)
                                #sse_chunk = f'event: text_chunk\ndata: {text_chunk.model_dump_json()}\n\n'
                                yield data["answer"]
                    except Exception as e:
                         #yield f"event: error\ndata: {'message': f'解析响应失败: {str(e)}'}\n\n"
                        yield f"解析响应失败: {str(e)}"
                    #await asyncio.sleep(0.05)
    async def add_conversation_id(self,conversation_id: str):
        
        self.task_instance.dify_conversation_id = conversation_id  # 更新任务的Dify会话ID
        await self.task_instance.save()


    async def Next_Suggested_Questions(self):
        print("获取下一步建议问题...")  # Debug log
        url = f"{self.base_url}/v1/messages/{self.last_message_id}/suggested?user=abc-123"
        print("建议问题URL:", url)  # Debug log
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url, 
                    headers={
                        'Authorization': self.headers["Authorization"],
                        'Content-Type': 'application/json',

                    }
                )
                print("建议响应:", response)  # Debug log
                print("建议响应:", response.json()["data"])  # Debug log
                return response.json()
        except Exception as e:
            print(f"获取建议问题时出错: {e}")

    """疑似有bug"""
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
    
# --------------------------已弃用------------------------
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

# --------------------------已弃用------------------------

@geometry.get("/")
async def geometry_home():
    return {"message": "Geometry modeling home page"}





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
    if settings.DIRECTORY:
        base_dir = Path(settings.DIRECTORY) 
    else:
        base_dir = Path(os.getcwd()) / "files"
    # 构建目标目录路径：上一级目录/files/会话ID
    conversation_dir = base_dir / conversation_id
    
    try:
        # 创建目录（包括所有必要的父目录）
        conversation_dir.mkdir(parents=True, exist_ok=True)
        print(f"成功创建会话目录: {conversation_dir}")
    except Exception as e:
        print(f"创建会话目录失败: {e}")
        raise
    return conversation
