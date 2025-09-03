from typing import Optional, Dict, List, Any, Union, Callable, Set
import json
import os
from datetime import datetime

from fastapi import APIRouter
from fastapi import Header
from pydantic import BaseModel
from pydantic import Field
from fastapi import Form
from pydantic import  field_validator



import httpx
from fastapi import status, HTTPException
from contextlib import asynccontextmanager
import websockets

import asyncio

import aiofiles
from pathlib import Path

from config import settings
from core.authentication import authenticate
from core.authentication import User
from database.models import Tasks
from database.models import OptimizationResults
from apps.chat import  save_or_update_message_in_redis
from apps.schemas import Message
from apps.schemas import (
    OptimizeRequest,
    UnitInfo,
    OptimizeResult,
    AlgorithmRequest,
    TaskStatus,
    HealthStatus
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



optimize = APIRouter()

async def optimize_stream_generator(
        request: TaskExecuteRequest,
        current_user: User,
        redis_client,
        combinde_query,
        task: Tasks
):

            assistant_message = Message(
                role="assistant",
                content="",
                timestamp=datetime.now(),
                parts=[],
                metadata={},
                status="in_progress"
            )
            # 初始化状态标识
            task_terminate_event = asyncio.Event()  # 任务终止信号（用于两个并行任务通信）
            control_monitor_result = {"success": None, "message": ""}  # 控制监听结果存储
            try:
                 # 1. 立即保存初始的 "in_progress" 消息,
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id,
                    task_id=request.task_id, 
                    task_type=request.task_type,
                    conversation_id=request.conversation_id, 
                    message=assistant_message, 
                    redis_client=redis_client
                )

                # 2. 发送会话和任务信息
                conversation_info_data = SSEConversationInfo(
                    conversation_id=request.conversation_id, 
                    task_id=str(request.task_id)
                )
                sse_conv_info = f'event: conversation_info\ndata: {conversation_info_data.model_dump_json()}\n\n'
                yield sse_conv_info

                # # 3. 模拟流式发送文本块并更新Redis
                # FILE_PATH = r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\846ac6da-3e33-419e-ba9f-de37a2a89df0\426\backend_log.txt"
                # with open(FILE_PATH, "rb") as f:
                #     full_answer_source = f.read().decode("utf-8")
                
                # for i in range(0, len(full_answer_source), 5):
                #     chunk = full_answer_source[i:i+5]
                #     assistant_message.content += chunk
                #     assistant_message.timestamp = datetime.now()
                    
                #     text_chunk_data = SSETextChunk(text=chunk)
                #     yield f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
                    
                #     await save_or_update_message_in_redis(
                #         user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                #         conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                #     )
                #     await asyncio.sleep(0.05)

                # 3. 准备模型路径和优化结果记录
                model_path = rf"{request.file_url}" if request.file_url else r".\AutoFrame.SLDPRT"
                print("optimize model_path: ", model_path)

                # 初始化或更新优化结果记录
                optimize_result = await OptimizationResults.get_or_none(task_id=task.task_id)
                print("找到优化结果吗？", optimize_result)
                update_data = {
                    "optimized_cad_file_path": model_path,  
                }
                if optimize_result:
                    # 如果存在则更新
                    await optimize_result.update_from_dict(update_data).save()
                else:

                    optimize_result = await OptimizationResults.create(
                        task_id=task.task_id,
                        **update_data
                )
                print("优化结果: ", optimize_result)
                await optimize_result.save()

                # 4. 准备算法请求
                request_to_algorithm = AlgorithmRequest(
                    task_id=str(task.task_id),
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
                

                # 5. 提交算法服务执行优化任务
                task_status = await algorithm_client.run_algorithm(request_to_algorithm)
                task.status = task_status.status
                await task.save()
                print(f"Algorithm service returned status: {task.status}")

                # 6. 创建控制文件监听回调
                monitor_callback = create_task_monitor_callback(
                    model_path = model_path,
                    client = algorithm_client,
                    task_terminate_event = task_terminate_event,

                )
                # 订阅任务启动通知
                status_monitor_task = asyncio.create_task(
                      monitor_callback()
                )
                print("出来了吗")

        
                # 7.  异步监控软件截图文件
                # 创建一个队列用于传递异步生成器产生的SSE chunks
                queue = asyncio.Queue()
                # 修改1：创建一个包装函数，消费异步生成器并将结果放入队列
                async def consume_image_generator(request, screen_path, extensions, task_terminate_event, queue):
                    """消费图片监控生成器，将结果放入队列"""
                    try:
                        # 异步迭代生成器产生的所有值
                        async for sse_chunk in monitor_image_files(request, screen_path, extensions, task_terminate_event):
                            # 将生成的chunk放入队列
                            print("截图sse_chunk: ", sse_chunk)
                            await queue.put(sse_chunk)
                            
                            # 检查是否需要终止
                            if task_terminate_event.is_set():
                                break
                    except Exception as e:
                        print(f"图片生成器消费出错: {str(e)}")
                        # 可以放入错误信息到队列
                        await queue.put(f"event: error\ndata: {str(e)}\n\n")
                    finally:
                        # 放入终止信号
                        await queue.put(None)  # None表示生成器已结束

                SCREEN_FILE_PATH = Path(request.file_url).with_name("PNGFILE") # 目录

                IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp'}  # 要监控的图片格式
                print("SCREEN_FILE_PATH: ", SCREEN_FILE_PATH)
                # image_monitor_task = asyncio.create_task(
                #     monitor_image_files(
                #         SCREEN_FILE_PATH, 
                #         IMAGE_EXTENSIONS,
                #         task_terminate_event, 
                #     )
                # )
                # 修改2：启动生成器消费任务，而不是直接启动monitor_image_files
                image_monitor_task = asyncio.create_task(
                    consume_image_generator(
                        request,
                        SCREEN_FILE_PATH,
                        IMAGE_EXTENSIONS,
                        task_terminate_event,
                        queue
                    )
                )
                print("图片监控任务已启动")

                # 8. 异步监控日志文件，提取指定任务的日志并生成SSE格式响应
                # 创建一个包装函数，消费异步生成器并将结果放入队列
                async def consume_log_generator(
                        request,
                        LOG_FILE_PATH,
                        state,
                        task_terminate_event,
                        assistant_message,
                        current_user,
                        redis_client,
                        queue):
                    """消费日志监控生成器，将结果放入队列"""
                    try:
                        # 异步迭代生成器产生的所有值
                        async for sse_chunk in monitor_log_files(
                            request,
                            LOG_FILE_PATH,
                            state,
                            task_terminate_event,
                            assistant_message,
                            current_user,
                            redis_client
                        ):
                            # 将生成的chunk放入队列
                            print("日志sse_chunk: ", sse_chunk)
                            await queue.put(sse_chunk)
                            
                            # 检查是否需要终止
                            if task_terminate_event.is_set():
                                break
                    except Exception as e:
                        print(f"图片生成器消费出错: {str(e)}")
                        # 可以放入错误信息到队列
                        await queue.put(f"event: error\ndata: {str(e)}\n\n")
                    finally:
                        # 放入终止信号
                        await queue.put(None)  # None表示生成器已结束
                
                state = {"full_answer": ""}  # 使用可变对象来共享状态
                LOG_FILE_PATH = Path(request.file_url).with_name("backend_log.txt")
                log_monitor_task = asyncio.create_task(
                    consume_log_generator(
                        request,
                        LOG_FILE_PATH,
                        state,
                        task_terminate_event,
                        assistant_message,
                        current_user,
                        redis_client,
                        queue
                    )
                )

                # 当 terminate_event 生效或任务结束后结束 SSE
                while not task_terminate_event.is_set():
                    chunk = await queue.get()
                    if chunk:
                        yield chunk

                # 取消后台任务
                image_monitor_task.cancel()
                log_monitor_task.cancel()

                print("full_answer: ", state)



                # 确保状态监控任务完成
                # if not status_monitor_task.done():
                #     await status_monitor_task
                print("执行这个close了吗")
                await algorithm_client.close()  # 关闭算法客户端连接

                # 9. 采用新的图片流式方案并更新Redis
                mock_images = [
                    {"path": rf"/files/{request.conversation_id}/{request.task_id}/convergence_curve.png", "alt": "收敛曲线"},
                    {"path": rf"/files/{request.conversation_id}/{request.task_id}/parameter_distribution.png", "alt": "参数分布图"}
                ]
                print("要展示的图片： ", mock_images)
                image_parts_for_redis = []
                for img_data in mock_images:
                    # if os.path.exists(img_data["path"]):
                    image_file_name = os.path.basename(img_data["path"])
                    image_url = img_data["path"] # 修正：指向 /files 路由
                    
                    image_part = {"type": "image", "imageUrl": image_url, "fileName": image_file_name, "altText": img_data["alt"]}
                    assistant_message.parts.append(image_part)
                    assistant_message.timestamp = datetime.now()

                    # # 调试：打印实际的文件路径
                    # current_file_dir = os.path.dirname(os.path.abspath(__file__))
                    # project_root = os.path.dirname(current_file_dir)
                    # base_dir = os.path.join(project_root, "files")
                    # safe_path = os.path.abspath(os.path.join(base_dir, image_file_name))
                    # print(f"Attempting to serve image from: {safe_path}")

                    # 使用 SSEImageChunk 发送图片信息
                    print("设计优化图片：", image_url)
                    image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=image_file_name, altText=img_data["alt"])
                    yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'

                    await save_or_update_message_in_redis(
                        user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                        conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                    )

                    await asyncio.sleep(0.1) # 恢复延迟
                        
                        # 准备存入Redis的数据
                        #image_parts_for_redis.append({"type": "image", "imageUrl": image_url, "fileName": image_file_name, "altText": img_data["alt"]})

                # 10. 发送结束消息
                final_metadata = GenerationMetadata(
                    cad_file=model_path,
                    code_file="script.py",
                    preview_image=None
                )
                final_response_data = SSEResponse(
                    answer="".join(state["full_answer"]),
                    metadata=final_metadata
                )
                
                sse_final = f'event: message_end\ndata: {final_response_data.model_dump_json()}\n\n'
                yield sse_final

                 # 11. 最后一次更新Redis，状态为 "done"
                assistant_message.status = "done"
                assistant_message.timestamp = datetime.now()
                await save_or_update_message_in_redis(
                    user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
                    conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
                )

                # 12. 数据库操作，保存任务状态，优化结果
                task.status = "done"
                await task.save()

                optimize_result = await OptimizationResults.get_or_none(task_id=task.task_id)
                print("找到优化结果吗？", optimize_result)
                update_data = {
                    "optimized_cad_file_path": model_path,  
                }
                if optimize_result:
                    # 如果存在则更新
                    await optimize_result.update_from_dict(update_data).save()
                else:

                    optimize_result = await OptimizationResults.create(
                        task_id=task.task_id,**update_data
                )
                print("优化结果: ", optimize_result)
                await optimize_result.save()

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





@optimize.get("")
async def optimize_home():
    return {"message": "Design optimization home page"}



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


# 算法服务客户端
class AlgorithmClient:
    def __init__(self, 
                 base_url: str,
                 timeout: float = 30.0,
                 max_connections: int = 100
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=self.timeout,
            #limits=httpx.limits(max_connections=max_connections),
            headers={"Connection": "keep-alive"}
        )
        print("连接上算法服务端了：",self.client)
        self._is_closed = False
        self.websocket : Optional[websockets.WebSocketClientProtocol] = None
        self.websocket_task: Optional[asyncio.Task] = None
        self.status = None

    async def __aenter__(self):
        """支持异步上下文管理器进入"""
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """支持异步上下文管理器退出，确保连接关闭"""
        await self.close()

    @asynccontextmanager
    async def _request_context(self):
        """请求上下文管理器，确保异常情况下的资源处理"""
        if self._is_closed:
            raise RuntimeError("Client has been closed. Create a new instance.")
        
        try:
            yield
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Request to algorithm service timed out."
            )
        except httpx.HTTPError as e:
            # 根据不同错误类型细化异常处理
            if isinstance(e,(httpx.ConnectError, httpx.ConnectTimeout)):
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Could not connect to service: {str(e)}"
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"HTTP error occurred: {str(e)}"
            )
        except Exception as e:
            # 确保任何异常都不会导致资源泄漏
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unexpected error: {str(e)}"
            )

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
                "/run-algorithm",#"/submit-task",
                json=request.model_dump(),
            )
            response.raise_for_status()
            
            return TaskStatus(**response.json())
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error running algorithm: {str(e)}"
            )
    async def check_task_status(self, task_id, callback: Callable):
        try:
            while True:
                response = await self.client.get(
                    f"/task-status/{task_id}",
                    timeout=10  # 设置10秒超时
                )
                
                response.raise_for_status()

                data = response.json()
                try:
                    taskstatus = TaskStatus(**data)
                except Exception as e:
                    raise ValueError(f"服务端返回的数据格式不符合要求: {str(e)}")
                
                # 检查任务状态
                print(f"查询到任务{task_id}状态 {taskstatus.status}")
                if taskstatus.status == "running":
                    # 状态为运行中，调用回调函数
                    await callback()  # 如果回调是异步函数
                    # 或者：callback(task_status)  # 如果回调是同步函数
                    break  # 触发回调后退出轮询

                # 等待1秒后再次查询
                await asyncio.sleep(5)
        except Exception as e:
            if response.status_code == 404:
                raise ValueError(f"任务ID不存在: {task_id}") from e
            else:
                raise ValueError(f"查询失败，HTTP状态码: {response.status_code}") from e

    async def subscribe_to_task_start(self, task_id, callback: Callable):
        """
        订阅任务启动通知
        """

        # 构建WebSocket URL
        ws_protocol = "wss" if self.base_url.startswith("https") else "ws"
        base_ws_url = self.base_url.replace("http", ws_protocol, 1).rstrip("/")
        ws_url = f"{base_ws_url}/ws/{task_id}"
        print("ws_url: ", ws_url)
        try:
            # 连接WebSocket
            async with websockets.connect(ws_url) as websocket:
                self.websocket = websocket

            # 等待消息
            while True:
                try:
                    # 接收消息， 设置超时
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=10) # 10小时超时
                    data = json.loads(message)
                    print("收到websocker return:", data)

                    # 处理订阅确认
                    if data.get("status") == "subscribed" :
                        print(f"已成功订阅任务通知: 任务{task_id}")
                    # 处理任务启动通知
                    elif data.get("status") == "connected":
                        pass
                    elif data.get("status") == "running":
                        print(f"任务已启动: {task_id}")
                        await callback(data)  # 调用回调函数
                        break  # 收到启动通知后退出循环

                except asyncio.TimeoutError:
                    await self.websocket.send(json.dumps({"type": "ping"}))
                except websockets.exceptions.ConnectionClosed:
                    print(f"WebSocket连接已关闭: {task_id}")
                    break
        except Exception as e:
            print(f"WebSocket订阅出错: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error subscribing to task notifications: {str(e)}"
            )
        
    async def send_parameter(self, model_path: str,param: dict):
        """发送优化参数到算法服务"""
        try:

            with open(rf"{model_path}\parameters.txt", "w", encoding="utf-8") as f:
                json.dump(param, f)

            response = await self.client.post(
                "/sent_parameter",
                params={"model_path": model_path}
            )
            return response.json()
        except IOError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error writing parameters file: {str(e)}"
            )
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error sending parameters: {str(e)}"
            )
        
    async def close(self):
        if self._is_closed:
            return
        """关闭 HTTP 客户端连接"""
        print("Closing AlgorithmClient connections...")
        if not self.client.is_closed:
            await self.client.aclose()

        # 关闭WebSocket连接
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()

        # 取消WebSocket任务
        if self.websocket_task and not self.websocket_task.done():
            self.websocket_task.cancel()
            
        self._is_closed = True


# 命令常量
class ControlCommand:
    INIT = 0
    PARAMS_READY = 1
    RESULT_READY = 2
    EXIT = 3
    CSERROR = -1
    PYERROR = -2

# 工具函数：读写文件
def read_key(file_path, key):
    """读取文件中指定键的值"""
    if not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"读取键值失败（{key}）：{e}")
    return None

def write_key(file_path, key, value):
    """写入键值对到文件"""
    lines = []
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f]

    found = False
    for i in range(len(lines)):
        if lines[i].startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

class ControlFileMonitor:
    """控制文件监视器，处理监听和错误处理逻辑"""
    def __init__(self, model_path:str, client):
        self.model_path = model_path
        self.control_file = os.path.join(os.path.dirname(model_path), "control.txt")
        self.client = client
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
        
    async def start_monitoring(self, completion_callback: Callable = None):
        self.running = True
        self.monitor_task = asyncio.create_task(
            self._monitor_loop(completion_callback)
        )
        return self.monitor_task
    
    async def _monitor_loop(self, completion_callback: Callable = None):
        """监听循环，定期检查控制文件状态"""
        try:
            while self.running:
                # 读取命令值
                #print(f"control.txt url: {self.control_file}")
                command_str = read_key(self.control_file, "command")
                #print(f"监听control.txt, command={command_str}")
                if not command_str:
                        await asyncio.sleep(1)  # 1秒后重试
                        continue
                
                if command_str in [str(ControlCommand.CSERROR), str(ControlCommand.PYERROR)]:
                    print(f"检测到致命错误（命令: {command_str}），终止任务")

                    # 写入EXIT命令终止依赖运行
                    write_key(self.control_file, "command", str(ControlCommand.EXIT))
                    
                    # 清理资源
                    # await self._cleanup_resources()

                    # 调用完成回调（如果有）
                    if completion_callback:
                        await completion_callback(False, f"任务失败: {command_str}")

                    self.running = False
                    break
                    
                elif command_str == str(ControlCommand.EXIT):
                    print(f"任务已正常退出: {self.model_path}")
                    
                    if completion_callback:
                        await completion_callback(True, "任务正常退出")
                    # await self._cleanup_resources()

                    self.running = False
                    print("准备推出循环")
                    break

                # 每秒检查一次
                await asyncio.sleep(1)
        except Exception as e:
            print(f"监听控制文件时出错: {str(e)}")
            if completion_callback:
                await completion_callback(False, f"监听错误: {str(e)}")
            await self._cleanup_resources()
        print("推出try了吗")

    async def _cleanup_resources(self):
         
         
        """清理资源：关闭连接和客户端实例"""
        self.running = False
        print(f"清理任务资源: {self.model_path}")
        
        # 关闭客户端连接
        if self.client and not self.client._is_closed:
            await self.client.close()

        await self.stop_monitoring()
    async def stop_monitoring(self):
        """停止监听"""
        self.running = False
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                print("进入等待")
                # await self.monitor_task
                print("推出等待")
            except asyncio.CancelledError:
                print("关闭监听错误")

         # 无论任务是否存在，都清空引用
        self.monitor_task = None

# 工厂函数
def create_task_monitor_callback(model_path: str, client, task_terminate_event):
    """创建任务启动后的回调函数，用于开始监听控制文件"""
    if not isinstance(model_path, str) or not model_path.strip():
        raise ValueError("初始化时的model_path必须是有效的非空字符串")
    if not client:
        raise ValueError("client参数不能为空")
    if not task_terminate_event:
        raise ValueError("task_terminate_event参数不能为空")
    async def task_start_callback(data: Optional[Dict] = None):
        if data and isinstance(data, dict):
            callback_model_path = data.get("model_path", model_path)
        else:
            callback_model_path = model_path  # data为空时直接使用初始路径
        
        try:
        
            monitor = ControlFileMonitor(model_path, client)

            # 定义任务完成后的处理
            async def on_completion(success: bool, message: str):
                print(f"任务处理完成: {message}")
                # 可以在这里添加后续处理逻辑，如通知用户等
                # 当控制文件监听完成时，触发终止事件以结束日志监控
                if not task_terminate_event.is_set():
                    await asyncio.sleep(1)
                    task_terminate_event.set()
                    print("控制文件监听结束，已触发日志监控终止事件")
                return
            # 启动监听
            await monitor.start_monitoring(on_completion)
            print("回调函数里，监听结束了吗")
            return 
        except Exception as e:
            print(f"任务监控启动失败: {str(e)}")
            # 发生异常时也触发终止事件
            if not task_terminate_event.is_set():
                task_terminate_event.set()
    return task_start_callback

async def get_existing_images(SCREEN_FILE_PATH, IMAGE_EXTENSIONS) -> Set[str]:
    """获取当前目录下所有符合条件的图片文件路径"""
    images = set()
    if not SCREEN_FILE_PATH.exists():
        return images
        
    # 使用os.scandir替代iterdir，减少系统调用
    with os.scandir(SCREEN_FILE_PATH) as entries:
        for entry in entries:
            # 只检查文件，且扩展名符合要求
            if entry.is_file(follow_symlinks=False):
                _, ext = os.path.splitext(entry.name)
                if ext.lower() in IMAGE_EXTENSIONS:
                    images.add(entry.path)
    return images

async def process_new_image(image_path):
    """处理新发现的图片并推送至前端"""
    try:
        # 获取图片文件名作为标识
        image_file_name = os.path.basename(image_path)
        print(f"传递 图片{image_file_name}")
       
        # 构建图片信息
        alt_Text = "screenshot"
        # # 更新消息内容
        # assistant_message.content += f"新图片: {image_filename}\n"
        # assistant_message.timestamp = datetime.now()
        

        # # 保存消息到Redis
        # await save_or_update_message_in_redis(
        #     user_id=current_user.user_id,
        #     task_id=request.task_id,
        #     task_type=request.task_type,
        #     conversation_id=request.conversation_id,
        #     message=assistant_message,
        #     redis_client=redis_client
        # )
        
        # 使用 SSEImageChunk 发送图片信息
        image_chunk_data = SSEImageChunk(imageUrl=image_path, fileName=image_file_name, altText=alt_Text)
        yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'
        
    except Exception as e:
        print(f"处理图片 {image_path} 时出错: {str(e)}")


async def monitor_image_files(
        request,
        SCREEN_FILE_PATH: Path, 
        IMAGE_EXTENSIONS,
        task_terminate_event, 
):
    """监控图片文件目录，当新图片出现时推送至前端"""
    # if not SCREEN_FILE_PATH.exists() or not SCREEN_FILE_PATH.is_dir():
    #     print(f"图片监控目录不存在或不是目录: {SCREEN_FILE_PATH}")
    #     return
    
    # 记录初始已存在的图片文件，避免监控开始时推送历史图片
    initial_images = await get_existing_images(SCREEN_FILE_PATH, IMAGE_EXTENSIONS)
    print(f"开始监控图片目录: {SCREEN_FILE_PATH}, 初始图片数量: {len(initial_images)}")
    
    # 用于跟踪已处理过的图片，避免重复推送
    processed_images = set(initial_images)
    # 延长检查间隔，减少文件系统访问
    check_interval = 2  # 2秒检查一次，比原来更长
    last_check_time = datetime.now()
    
    try:
        while not task_terminate_event.is_set():
             # 只有到达检查时间才执行目录扫描
            if (datetime.now() - last_check_time).total_seconds() >= check_interval:
                # 获取当前目录下的所有图片
                current_images = await  get_existing_images(SCREEN_FILE_PATH, IMAGE_EXTENSIONS)
                print("current_images: ", current_images)
                
                # 找出新增的图片
                new_images = [img for img in current_images if img not in processed_images]
                
                for image_path in new_images:
                    # 处理新图片
                    image_file_name = os.path.basename(image_path)
                    print(f"传递 图片{image_file_name}")
                    # 构建图片信息
                    image_url =rf"/files/{request.conversation_id}/{request.task_id}/PNGFILE/{image_file_name}"
                    print(f"传递 图片{image_url}")
                    alt_Text = "screenshot"
                    image_chunk_data = SSEImageChunk(imageUrl=image_url, fileName=image_file_name, altText=alt_Text)
                    yield f'event: image_chunk\ndata: {image_chunk_data.model_dump_json()}\n\n'
                    
                    # 将新图片加入已处理集合
                    processed_images.add(image_path)
                last_check_time = datetime.now()
            # 控制监控频率
            await asyncio.sleep(1)  # 每1秒检查一次新图片
            
    except Exception as e:
        print(f"图片监控过程出错: {str(e)}")
    finally:
        print("图片监控任务已终止")


async def monitor_log_files(
        request,
        LOG_FILE_PATH,
        state,
        task_terminate_event,
        assistant_message,
        current_user,
        redis_client
):
    
    if not LOG_FILE_PATH.exists():
        with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
            f.write("")  # 创建空文件

    # 记录初始文件位置
    start_position = LOG_FILE_PATH.stat().st_size
    async with aiofiles.open(LOG_FILE_PATH, "r",encoding="utf-8") as log_file:

        await log_file.seek(start_position) 

        while not task_terminate_event.is_set():
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

            state["full_answer"] += line 