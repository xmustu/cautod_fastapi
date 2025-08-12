from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from fastapi.responses import StreamingResponse
import asyncio
import json
from datetime import datetime

from core.authentication import get_current_active_user, User
from database.models_1 import Tasks, Conversations
from apps.app02 import GenerationMetadata, SSEConversationInfo, SSETextChunk, SSEResponse, FileItem, PartData, SSEPartChunk, SSEImageChunk
import os
from apps.chat import save_message_to_redis, Message
from apps.app02 import geometry_dify_api
import time 
import uuid
import asyncio
import subprocess
import threading
import queue

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
    print("task_data: ", task_data)
    redis_client = request.app.state.redis
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
        status="pending" # 初始状态
        # 'details' 字段在 Tasks 模型中不存在，因此不直接保存
    )
    
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
        await save_message_to_redis(
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
            try:
                # 首先发送会话和任务信息
                conversation_info_data = SSEConversationInfo(conversation_id=request.conversation_id, task_id=str(request.task_id))
                sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
                yield sse_conv_info

                # 前端测试案例
                # 1. 模拟流式发送文本块
                full_answer = ""
                FILE_PATH = r"D:\else\CAutoD_SoftWare\temp\cautod_fastapi\files\test_example.txt"
                with open(FILE_PATH, "rb") as f:
                    full_answer = f.read().decode("utf-8")
                for i in range(0, len(full_answer), 5):
                    chunk = full_answer[i:i+5]
                    text_chunk_data = SSETextChunk(text=chunk)
                    sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    yield sse_chunk
                    await asyncio.sleep(0.05)

 

                
                # full_answer = []
                # async for chunk in geometry_dify_api(query=combinde_query):
                #     text_chunk_data = SSETextChunk(text=chunk)
                #     sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                #     yield sse_chunk
                #     await asyncio.sleep(0.05)
                #     full_answer.append(chunk)
                
                

                # 2. 流式发送预览图
                image_parts_for_redis = []
                preview_image_path = r"D:\else\CAutoD_SoftWare\temp\cautod_fastapi\files\yuanbao.png"
                if os.path.exists(preview_image_path):
                    file_name = os.path.basename(preview_image_path)
                    image_url = f"/files/{file_name}" # 修正：指向 /files 路由
                    
                    image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=file_name, altText="几何建模预览图")
                    yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'
                    await asyncio.sleep(0.1)
                    
                    image_parts_for_redis.append({"type": "image", "imageUrl": image_url, "fileName": file_name, "altText": "几何建模预览图"})

                # 3. 发送包含完整元数据的结束消息
                final_response_data = SSEResponse(
                    answer=''.join(full_answer),
                    metadata=GenerationMetadata(
                        cad_file="model.step",
                        code_file="script.py",
                        preview_image=None  # 置空，因为已通过 image_chunk 发送
                    )
                )
                
                sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
                yield sse_final

                # 4. 保存结构化的助手消息到Redis
                message = Message(
                    role="assistant",
                    content=''.join(full_answer),
                    parts=image_parts_for_redis, # 保存图片信息
                    metadata=final_response_data.metadata.model_dump(),
                    timestamp=datetime.now()
                )
                await save_message_to_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=message,
                    redis_client=redis_client
                )

                # 任务成功完成，更新状态
                task.status = "done"
                await task.save()

            except Exception as e:
                # 任务失败，更新状态
                task.status = "failed"
                await task.save()
                # 可以选择性地记录错误日志
                print(f"Error during task execution: {e}")
                # 向客户端发送错误事件
                error_data = json.dumps({"error": "An error occurred during task execution."})
                yield f'event: error\ndata: {error_data}\n\n'

        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    elif request.task_type == "retrieval":
        async def stream_generator():
            try:
                # 1. 发送会话和任务信息
                conversation_info_data = SSEConversationInfo(conversation_id=request.conversation_id, task_id=str(request.task_id))
                yield f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'

                # 2. 发送初始文本块
                initial_text = "Part retrieval completed! See:"
                text_chunk_data = SSETextChunk(text=initial_text)
                yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                
                # 3. 模拟并流式发送零件数据
                mock_parts = [
                    PartData(id=1, name="高强度齿轮", imageUrl="https://images.unsplash.com/photo-1559496447-8c6f7879e879?q=80&w=2940&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", fileName="gear_model_v1.step"),
                    PartData(id=2, name="轻量化支架", imageUrl="https://images.unsplash.com/photo-1620756243474-450c37a58759?q=80&w=2940&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", fileName="bracket_lite_v3.stl"),
                    PartData(id=3, name="耐磨轴承", imageUrl="https://images.unsplash.com/photo-1506794778202-b6f7a14994d6?q=80&w=2592&auto=format&fit=crop&ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D", fileName="bearing_wear_resistant.iges")
                ]

                for part_data in mock_parts:
                    part_chunk_data = SSEPartChunk(part=part_data)
                    yield f'event: part_chunk\ndata: {part_chunk_data.model_dump_json()}\n\n'
                    await asyncio.sleep(0.1) # 模拟网络延迟

                # 4. 发送结束信号 (这里我们发送一个简单的结束事件)
                yield 'event: message_end\ndata: {"status": "completed"}\n\n'

                # 5. 保存包含所有零件的最终消息
                final_parts_message = Message(
                    role="assistant",
                    content=initial_text,
                    parts=[part.model_dump() for part in mock_parts],
                    timestamp=datetime.now()
                )
                await save_message_to_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=final_parts_message,
                    redis_client=redis_client
                )

                # 任务成功完成，更新状态
                task.status = "done"
                await task.save()

            except Exception as e:
                task.status = "failed"
                await task.save()
                print(f"Error during retrieval task execution: {e}")
                error_data = json.dumps({"error": "An error occurred during task execution."})
                yield f'event: error\ndata: {error_data}\n\n'
        
        return StreamingResponse(stream_generator(), media_type="text/event-stream")

    elif request.task_type == "optimize":
        async def stream_generator():
            try:
                # 首先发送会话和任务信息
                conversation_info_data = SSEConversationInfo(conversation_id=request.conversation_id, task_id=str(request.task_id))
                sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
                yield sse_conv_info

                #full_answer = "已完成机械臂的轻量化设计。根据要求，在满足材料屈服强度为250MPa、安全系数为2（许用应力125MPa）的约束下，我们对机械臂进行了拓扑优化。最终，机械臂质量显著降低，且最大应力点满足安全要求。优化过程的收敛曲线图如下所示。"

                # 前端测试案例
                # 1. 模拟流式发送文本块
                full_answer = ""
                FILE_PATH = r"D:\else\CAutoD_SoftWare\temp\cautod_fastapi\files\test_example.txt"
                with open(FILE_PATH, "rb") as f:
                    full_answer = f.read().decode("utf-8")
                for i in range(0, len(full_answer), 5):
                    chunk = full_answer[i:i+5]
                    text_chunk_data = SSETextChunk(text=chunk)
                    sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    yield sse_chunk
                    await asyncio.sleep(0.05)
                # 2. 发送包含完整元数据的结束消息
                # 1. 定义在子线程中运行的函数：读取子进程输出并放入队列
                # ----------实际部分----------
                # output_queue = queue.Queue()  # 线程安全的队列

                # def read_subprocess_output(proc: subprocess.Popen, q: queue.Queue):
                #     """在独立线程中读取子进程输出"""
                #     # 读取stdout
                #     for line in iter(proc.stdout.readline, ''):
                #         if line:
                #             q.put(('stdout', line.strip()))
            
                #     # 读取stderr
                #     for line in iter(proc.stderr.readline, ''):
                #         if line:
                #             q.put(('stderr', line.strip()))
            
                #     proc.wait()
                #     q.put(('done', None))  # 发送结束信号
                
                
                # command = [r"C:\Users\dell\anaconda3\envs\sld\python.exe", r"C:\Users\dell\Projects\CAutoD\wenjian\sldwks.py"]
                
                # proc =  subprocess.Popen(
                #     command,
                #     stdout=subprocess.PIPE,
                #     stderr=subprocess.PIPE,
                #     text=True,          # 输出为字符串
                #     bufsize=1,          # 行缓冲
                #     universal_newlines=True
                # )
                # print("启动程序了吗")
                # full_answer = ""
                # # FILE_PATH = r"C:\Users\dell\Projects\CAutoD\wenjian\logdebug.txt"
                # # async with open(FILE_PATH, "rb") as f:
                # #     full_answer = await f.read().decode("utf-8")
                # # 启动读取线程
                # read_thread = threading.Thread(
                #     target=read_subprocess_output,
                #     args=(proc, output_queue),
                #     daemon=True
                # )
                # read_thread.start()
                # while True:
                #     # 非阻塞检查队列（避免阻塞事件循环）
                #     try:
                #         # 使用0.1秒超时，既保证实时性又不阻塞事件循环
                #         stream_type, line = output_queue.get(timeout=0.1)
                
                #         if stream_type == 'done':
                #             break  # 进程结束
                
                #         if line:
                #             print(f"[{stream_type}] {line}")
                #             # 发送到前端
                #             text_chunk_data = SSETextChunk(text=line)
                #             sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                #             yield sse_chunk
                #             await asyncio.sleep(0.05)  # 控制发送速度
                    
                #             # 积累完整回答
                #             if stream_type == 'stdout':
                #                 full_answer += line + "\n\n"
                #             else:  # stderr
                #                 full_answer += f"[错误] {line}\n\n"
                
                #         output_queue.task_done()
            
                #     except queue.Empty:
                #     # 队列空时检查进程是否已意外终止
                #         if proc.poll() is not None and not read_thread.is_alive():
                #             break
                #         continue
                # ----------实际部分----------

                #     line = proc.stdout.readline().strip()
                #     if not line and proc.poll() is None:
                #         # 如果读取到空字符串且进程已结束，则退出循环
                #         break
                #     if line:
                #         print("line: ", line)
                #         text_chunk_data = SSETextChunk(text=line)
                #         sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                #         yield sse_chunk
                #         await asyncio.sleep(0.05)
                #         full_answer = full_answer + line + "\n\n"
                # proc.wait()
                # for i in range(0, len(full_answer), 5):
                #     chunk = full_answer[i:i+5]
                #     text_chunk_data = SSETextChunk(text=chunk)
                #     sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                #     yield sse_chunk
                #     await asyncio.sleep(0.05)
                
                # --- 采用新的图片流式方案 ---
                mock_images = [
                    {"path": r"D:\else\CAutoD_SoftWare\temp\cautod_fastapi\files\yuanbao.png", "alt": "收敛曲线"},
                    {"path": r"D:\else\CAutoD_SoftWare\temp\cautod_fastapi\files\yuanbao.png", "alt": "参数分布图"}
                ]

                image_parts_for_redis = []
                for img_data in mock_images:
                    if os.path.exists(img_data["path"]):
                        file_name = os.path.basename(img_data["path"])
                        image_url = f"/files/{file_name}" # 修正：指向 /files 路由
                        
                        # 调试：打印实际的文件路径
                        current_file_dir = os.path.dirname(os.path.abspath(__file__))
                        project_root = os.path.dirname(current_file_dir)
                        base_dir = os.path.join(project_root, "files")
                        safe_path = os.path.abspath(os.path.join(base_dir, file_name))
                        print(f"Attempting to serve image from: {safe_path}")

                        # 使用 SSEImageChunk 发送图片信息
                        image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=file_name, altText=img_data["alt"])
                        yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'
                        await asyncio.sleep(0.1) # 恢复延迟
                        
                        # 准备存入Redis的数据
                        image_parts_for_redis.append({"type": "image", "imageUrl": image_url, "fileName": file_name, "altText": img_data["alt"]})

                final_response_data = SSEResponse(
                    answer=full_answer,
                    metadata=GenerationMetadata(
                        # 提供所有必需的字段，并确保格式正确
                        cad_file="model.step",
                        code_file="script.py",
                        preview_image=None
                    )
                )
                
                sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
                yield sse_final

                # 3. 保存结构化的助手消息到Redis
                message = Message(
                    role="assistant",
                    content=full_answer,
                    # 将图片信息也存入 message
                    parts=image_parts_for_redis, 
                    metadata=final_response_data.metadata.model_dump(),
                    timestamp=datetime.now()
                )
                await save_message_to_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id,
                    task_type=request.task_type,
                    conversation_id=request.conversation_id,
                    message=message,
                    redis_client=redis_client
                )

                # 任务成功完成，更新状态
                task.status = "done"
                await task.save()

            except Exception as e:
                task.status = "failed"
                await task.save()
                print(f"Error during optimization task execution: {e}")
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
