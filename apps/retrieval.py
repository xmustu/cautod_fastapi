import asyncio
import json 
from database.models_1 import Conversations
from database.models_1 import Tasks
from apps.schemas import Message
from core.authentication import User
from datetime import datetime
from apps.chat import  save_or_update_message_in_redis
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

async def retrieval_stream_generator(
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
    try:
        # 1. 立即保存初始的 "in_progress" 消息
        await save_or_update_message_in_redis(
            user_id=current_user.user_id, task_id=request.task_id, task_type=request.task_type,
            conversation_id=request.conversation_id, message=assistant_message, redis_client=redis_client
        )

        # 2. 发送会话信息
        conversation_info_data = SSEConversationInfo(
            conversation_id=request.conversation_id, 
            task_id=str(request.task_id)
        )
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

        # 7. 数据库操作，保存任务状态,优化结果
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