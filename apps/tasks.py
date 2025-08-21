from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from fastapi.responses import StreamingResponse
import asyncio
import json
from datetime import datetime

from core.authentication import get_current_active_user, User
from database.models_1 import Tasks, Conversations
from apps.app02 import GenerationMetadata, SSEConversationInfo, SSETextChunk, SSEResponse, FileItem, PartData, SSEPartChunk, SSEImageChunk, MessageRequest
import os
from apps.chat import save_message_to_redis, Message, save_or_update_message_in_redis
from apps.app02 import  DifyClient
import time 
import uuid
import asyncio
import aiofiles

from pathlib import Path
import shutil
import httpx
from config import Settings

settings = Settings()

# 创建一个新的 APIRouter 实例
router = APIRouter(
    tags=["任务管理"]
)

# --- Pydantic 模型定义 ---

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
        from_attributes = True # Tortoise-ORM 模型实例可以直接转换为 Pydantic 模型

class TaskExecuteRequest(BaseModel):
    """执行任务的请求体模型"""
    task_id: int = Field(..., description="要执行的任务ID")
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_type: str = Field(..., description="任务类型，用于后端路由")
    query: Optional[str] = Field(None, description="用户的文本输入")
    file_url: Optional[str] = Field(None, description="上传文件的URL")
    # ... 其他特定于任务的参数
    files: Optional[List[FileItem]] = Field(None, description="文件列表")

class PendingTaskResponse(BaseModel):
    """待处理任务的响应体模型"""
    task_id: int
    task_type: str
    created_at: datetime
    conversation_title: str

    class Config:
        from_attributes = True

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
    async def close(self):
        """关闭 HTTP 客户端连接"""
        await self.client.aclose()


# # 依赖注入 - 提供算法客户端实例
# async def get_algorithm_client():
#     settings = Settings()
#     client = AlgorithmClient(
#         base_url=settings.OPTIMIZE_API_URL,
#     )
#     try:
#         yield client
#     finally:
#         await client.close()


# --- API 端点实现 ---

@router.get("/pending", response_model=List[PendingTaskResponse], summary="获取所有待处理的任务")
async def get_pending_tasks(
    current_user: User = Depends(get_current_active_user)
):
    """
    获取当前用户所有状态为 'pending' 的任务，并按创建时间升序排列。
    """
    pending_tasks = await Tasks.filter(
        user_id=current_user.user_id,
        status="pending"
    ).order_by("created_at").prefetch_related("conversation")

    # 手动构建响应数据，因为 Pydantic 模型需要 conversation_title
    response_data = [
        PendingTaskResponse(
            task_id=task.task_id,
            task_type=task.task_type,
            created_at=task.created_at,
            conversation_title=task.conversation.title if task.conversation else "未知会话"
        )
        for task in pending_tasks
    ]
    
    return response_data

@router.post("", response_model=TaskCreateResponse, summary="创建新任务")
async def create_task(
    request: Request,
    task_data: TaskCreateRequest,
    current_user: User = Depends(get_current_active_user)
):
    #print("task_data: ", task_data)
    #redis_client = request.app.state.redis
    """
    创建并注册一个新的任务实例。
    
    此接口是所有工作流程的第一步，用于在数据库中生成一个唯一的任务记录。
    """
    # 验证 conversation_id 是否存在且属于当前用户
    conversation = await Conversations.get_or_none(
        conversation_id=task_data.conversation_id, 
        user_id=current_user.user_id
    )
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or does not belong to the current user."
        )
    
    # 创建任务实例
    new_task = await Tasks.create(
        conversation_id=task_data.conversation_id,
        user_id=current_user.user_id,
        task_type=task_data.task_type,
        status="pending", # 初始状态
        #dift_conversation_id="", # 初始为空，后续可更新
        # 'details' 字段在 Tasks 模型中不存在，因此不直接保存
    )
    print("---------------这是一次创建啊任务------------------")
    # 创建任务的文件存放目录
    # 获取当前目录的上一级目录
    parent_dir = Path(os.getcwd())
    
    # 构建目标目录路径：上一级目录/files/会话ID
    task_dir = parent_dir / "files" / str(task_data.conversation_id) / str(new_task.task_id)
    
    try:
        # 创建目录（包括所有必要的父目录）
        task_dir.mkdir(parents=True, exist_ok=True)
        print(f"成功创建任务目录: {task_dir}")
    except Exception as e:
        print(f"创建任务目录失败: {e}")
        raise
    # 移除在此处保存消息的逻辑，该职责已转移到前端
    # message = Message(
    #     role="user",
    #     content=task_data.details.get("query", ""),
    #     timestamp=datetime.now()
    # )
    # await save_message_to_redis(user_id=current_user.user_id, task_id=new_task.task_id, task_type=task_data.task_type, message=message, redis_client=redis_client)

    return new_task


@router.post("/execute", summary="执行任务")
async def execute_task(
    global_request: Request,  # 使用全局请求对象
    request: TaskExecuteRequest,
    current_user: User = Depends(get_current_active_user)
):
    redis_client = global_request.app.state.redis
    """
    根据 task_type 执行一个已创建的任务。
    """
    print(f"--- Received request to execute task: {request.task_id} ({request.task_type}) ---")
    # 验证任务是否存在且属于当前用户
    task = await Tasks.get_or_none(
        task_id=request.task_id, 
        user_id=current_user.user_id
    )
    if not task or task.conversation_id != request.conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or does not belong to the current user/conversation."
        )

    # --- 新增：在执行任务前，保存用户的消息 ---
    if request.query:
        user_message = Message(
            role="user",
            content=request.query,
            timestamp=datetime.now()
        )
        await save_or_update_message_in_redis(
            user_id=current_user.user_id,
            task_id=request.task_id,
            task_type=request.task_type,
            conversation_id=request.conversation_id,
            message=user_message,
            redis_client=redis_client
        )
    # --- 修改结束 ---

    assistant_message = {
        "role": "assistant",
    }
    # 更新任务状态为“处理中”
    #task.status = "processing"
    task.status = "running"
    await task.save()
    # 时间戳采用秒级+3位随机数，避免同一秒内冲突
    timestamp = f"{int(time.time())}_{uuid.uuid4().hex[:3]}"

    file_name = f'{current_user.user_id}_{request.conversation_id}_{request.task_id}_{timestamp}'
    combinde_query = request.query + f". 我希望生成的.py 和 .step 文件的命名为：{file_name}" 
    # + r'\n请注意文件保存路径为"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\mcp_out"'
    print("combinde_query: ", combinde_query)
    # 根据任务类型路由到不同的处理逻辑
    if request.task_type == "geometry":
        # --- 从 app02.py 移植过来的几何建模逻辑 ---
        async def stream_generator():
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
                # 获取建议问题
                suggested_questions = client.Next_Suggested_Questions()

                # 4. 流式发送预览图
                image_parts_for_redis = []
                preview_image_path = r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\yuanbao.png"
                if os.path.exists(preview_image_path):
                    imgage_file_name = os.path.basename(preview_image_path)
                    image_url = f"/files/{imgage_file_name}" # 修正：指向 /files 路由

                    image_part = {"type": "image", "imageUrl": image_url, "fileName": file_name, "altText": "几何建模预览图"}
                    assistant_message.parts.append(image_part)
                    assistant_message.timestamp = datetime.now()

                    image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=imgage_file_name, altText="几何建模预览图")
                    yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'

                    await save_or_update_message_in_redis(
                        user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                        conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                    )

                    await asyncio.sleep(0.1)
                    
                    #image_parts_for_redis.append({"type": "image", "imageUrl": image_url, "fileName": imgage_file_name, "altText": "几何建模预览图"})

                # 5. 发送包含完整元数据的结束消息
                final_metadata = GenerationMetadata(
                    cad_file=f"{file_name}.step",
                    code_file=f"{file_name}.py",
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

                task.status = "done"
                await task.save()

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

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    elif request.task_type == "retrieval":
        async def stream_generator():
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

                # 2. 发送会话信息
                conversation_info_data = SSEConversationInfo(conversation_id=request.conversation_id, task_id=str(request.task_id))
                yield f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'

                # 3. 发送初始文本块并更新Redis
                initial_text = "Part retrieval completed! See:"
                assistant_message.content = initial_text
                assistant_message.timestamp = datetime.now()
                text_chunk_data = SSETextChunk(text=initial_text)
                yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                    conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                )
                
                # 4. 模拟并流式发送零件数据，同时更新Redis
                mock_parts = [
                    PartData(id=1, name="高强度齿轮", imageUrl="https://images.unsplash.com/photo-1559496447-8c6f7879e879?q=80&w=2940&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", fileName="gear_model_v1.step"),
                    PartData(id=2, name="轻量化支架", imageUrl="https://images.unsplash.com/photo-1620756243474-450c37a58759?q=80&w=2940&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", fileName="bracket_lite_v3.stl"),
                    PartData(id=3, name="耐磨轴承", imageUrl="https://images.unsplash.com/photo-1506794778202-b6f7a14994d6?q=80&w=2592&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", fileName="bearing_wear_resistant.iges")
                ]

                for part_data in mock_parts:
                    part_dict = part_data.model_dump()
                    part_dict['type'] = 'part'  # 确保每个 part 对象都有 type 字段
                    assistant_message.parts.append(part_dict)
                    assistant_message.timestamp = datetime.now()
                    
                    part_chunk_data = SSEPartChunk(part=part_data)
                    yield f'event: part_chunk\ndata: {part_chunk_data.model_dump_json()}\n\n'
                    
                    await save_or_update_message_in_redis(
                        user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                        conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                    )
                    await asyncio.sleep(0.1)

                # 5. 发送结束信号
                yield 'event: message_end\ndata: {"status": "completed"}\n\n'

                # 6. 最后一次更新Redis，状态为 "done"
                assistant_message.status = "done"
                assistant_message.timestamp = datetime.now()
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                    conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                )

                task.status = "done"
                await task.save()

            except Exception as e:
                task.status = "failed"
                await task.save()
                print(f"Error during retrieval task execution: {e}")

                assistant_message.content += f"\n\n**任务执行出错**: {e}"
                assistant_message.status = "failed"
                assistant_message.timestamp = datetime.now()
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                    conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                )

                error_data = json.dumps({"error": "An error occurred during task execution."})
                yield f'event: error\ndata: {error_data}\n\n'
        
        return StreamingResponse(stream_generator(), media_type="text/event-stream")


    elif request.task_type == "optimize":
        """
        将 swg_path 指向的单个文件复制到目录。
        如果同名文件已存在，则跳过。
        弃用，算法测已改进
        """
        # swg_path = r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\machweijfiweowef.swp"
        # if not os.path.isfile(swg_path):
        #     print(f"错误：{swg_path} 不存在或不是文件")
        #     return

        # dst_path = os.path.join(os.path.dirname(request.file_url), os.path.basename(swg_path))

        # if os.path.exists(dst_path):
        #     print(f"跳过：{dst_path} 已存在")
        # else:
        #     shutil.copy2(swg_path, dst_path)   # copy2 保留元数据
        #     print(f"已复制：{swg_path} -> {dst_path}")

        async def stream_generator():

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

                # 3. 启动算法服务
                model_path = rf"{request.file_url}" if request.file_url else r".\AutoFrame.SLDPRT"
                request_to_algorithm = AlgorithmRequest(
                    task_id=str(request.task_id),
                    conversation_id = str(request.conversation_id),
                    geometry_description="",
                    parameters={
                        "model_path": model_path,
                       
                    }
                )
                algorithm_client = AlgorithmClient(base_url=settings.OPTIMIZE_API_URL)
                # 检查算法服务健康状态
                health_status = await algorithm_client.check_health()
                if health_status.status != "healthy":
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Algorithm service is not healthy."
                    )
                # 调用算法服务执行优化任务
                task_status = await algorithm_client.run_algorithm(request_to_algorithm)
                task.status = task_status.status
                await task.save()
                
                """
                4.异步监控日志文件，提取指定任务的日志并生成SSE格式响应
                 """
                full_answer = ""
                LOG_FILE_PATH = Path(request.file_url).with_name("backend_log.txt")
                if not LOG_FILE_PATH.exists():
                    with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                        f.write("")  # 创建空文件

                # 记录初始文件位置
                start_position = LOG_FILE_PATH.stat().st_size
                async with aiofiles.open(LOG_FILE_PATH, "r",encoding="utf-8") as log_file:

                    await log_file.seek(start_position) 

                    while True:
                        # 1. 检查任务状态
                        try:
                            pass
                        except:
                            pass

                        #2. 读取新增日志
                        line = await log_file.readline()
                        if line:
                            if not line.endswith('\n'):
                                 line += '\n'
                            chunk = line #.replace("\\n", "\n")

                            assistant_message.content += chunk
                            assistant_message.timestamp = datetime.now()

                            text_chunk_data = SSETextChunk(text=chunk)
                            sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'

                            await save_or_update_message_in_redis(
                                user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                                conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                            )
                            
                            yield sse_chunk
                            await asyncio.sleep(0.05)  # 控制发送速度
                        else:
                            # 无新内容时等待
                            await asyncio.sleep(0.05)

                            full_answer += line + "\n\n"


                # 5. 采用新的图片流式方案并更新Redis
                mock_images = [
                    {"path": r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\convergence_curve.png", "alt": "收敛曲线"},
                    {"path": r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\parameter_distribution.png", "alt": "参数分布图"}
                ]

                image_parts_for_redis = []
                for img_data in mock_images:
                    if os.path.exists(img_data["path"]):
                        image_file_name = os.path.basename(img_data["path"])
                        image_url = f"/files/{image_file_name}" # 修正：指向 /files 路由
                        
                        image_part = {"type": "image", "imageUrl": image_url, "fileName": file_name, "altText": img_data["alt"]}
                        assistant_message.parts.append(image_part)
                        assistant_message.timestamp = datetime.now()

                        # 调试：打印实际的文件路径
                        current_file_dir = os.path.dirname(os.path.abspath(__file__))
                        project_root = os.path.dirname(current_file_dir)
                        base_dir = os.path.join(project_root, "files")
                        safe_path = os.path.abspath(os.path.join(base_dir, image_file_name))
                        print(f"Attempting to serve image from: {safe_path}")

                        # 使用 SSEImageChunk 发送图片信息
                        image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=image_file_name, altText=img_data["alt"])
                        yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'

                        await save_or_update_message_in_redis(
                            user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                            conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                        )

                        await asyncio.sleep(0.1) # 恢复延迟
                        
                        # 准备存入Redis的数据
                        #image_parts_for_redis.append({"type": "image", "imageUrl": image_url, "fileName": image_file_name, "altText": img_data["alt"]})

                # 6. 发送结束消息
                final_metadata = GenerationMetadata(
                    cad_file=request.file_url,
                    code_file="script.py",
                    preview_image=None
                )
                final_response_data = SSEResponse(
                    answer=full_answer,
                    metadata=final_metadata
                )
                
                sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
                yield sse_final

                 # 7. 最后一次更新Redis，状态为 "done"
                assistant_message.status = "done"
                assistant_message.timestamp = datetime.now()
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                    conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                )

                task.status = "done"
                await task.save()

            except Exception as e:
                task.status = "failed"
                await task.save()
                print(f"Error during optimization task execution: {e}")

                assistant_message.content += f"\n\n**任务执行出错**: {e}"
                assistant_message.status = "failed"
                assistant_message.timestamp = datetime.now()
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                    conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                )

                error_data = json.dumps({"error": "An error occurred during task execution."})
                yield f'event: error\ndata: {error_data}\n\n'

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    else:
        #模拟保存生成的消息到数据库, 仅使用示例
        assistant_message["content"] = "Unknown task type. Please check your request."
        # 保存助手消息到Redis
        message = Message(
            role="assistant",
            content=assistant_message["content"],
            timestamp=datetime.now()
        )
        print("结果回复信息: ", message)
        await save_message_to_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=message,
                    redis_client=redis_client
                )
        
        task.status = "failed"
        await task.save()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown task type: {request.task_type}"
        )


class OptimizationParamsRequest(BaseModel):
    """接收优化参数的请求体模型"""
    conversation_id: str = Field(..., description="任务所属的对话ID")
    task_id: int = Field(..., description="任务ID")
    params: Dict[str, Dict[str, float]] = Field(..., description="优化参数及其范围，例如 {'param1': {'min': 0.1, 'max': 1.0}}")

@router.post("/optimize/submit-params", summary="提交优化参数")
async def submit_optimization_params(
    request_data: OptimizationParamsRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    接收前端提交的优化参数，并打印。
    """
    print(f"--- Received optimization parameters for conversation {request_data.conversation_id}, task {request_data.task_id} ---")
    print("Received Params:", request_data.params)

    # 这里可以添加验证逻辑，例如验证 task_id 和 conversation_id 是否属于当前用户
    task = await Tasks.get_or_none(
        task_id=request_data.task_id,
        user_id=current_user.user_id,
        conversation_id=request_data.conversation_id
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found or does not belong to the current user/conversation."
        )

    # 模拟成功响应
    return {"message": "Parameters received successfully and printed to console."}