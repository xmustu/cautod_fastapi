from typing import Optional
from fastapi import APIRouter
from fastapi import Request
from fastapi import File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi import Depends
from fastapi import status
from fastapi import Form
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import hashlib
from core.authentication import authenticate
from core.authentication import get_current_active_user, User
from database.models_1 import *
from .schemas import ConversationOut
import os
import mimetypes
from apps.chat import get_message_key, get_user_task_key

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
templates = Jinja2Templates(directory="templates")
router = APIRouter()

# --- 配置允许访问的基础目录列表 ---
# 这里列出所有允许访问的目录的绝对路径
ALLOWED_BASE_DIRS = [
    # 原有的files目录
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files")),
    # 新增允许访问的目录1
    r"C:\Users\dell\Projects\cadquery_test\cadquery_test\mcp\mcp_out",
    # 新增允许访问的目录2
    r"C:\Users\dell\Projects\CAutoD\wenjian"
]

async def save_file(file, path: Optional[str] = None):
    if path == None:
        path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files"))
    res = await file.read()
    #hash_name = hashlib.md5(file.filename.encode()).hexdigest()[:16]
    #file_name = f"{hash_name}.{file.filename.rsplit('.', 1)[-1]}"
    full_file = f"{path}\{file.filename}"
    with open(full_file, "wb") as f:
        f.write(res)
    return full_file



@router.get("/")
def home(request: Request, alert: Optional[str] = None):

    return templates.TemplateResponse(
        "home.html", {"request": request, "alert": alert}
    )

@router.post("/upload_file", summary="上传文件")
async def upload_file(*, 
                file: UploadFile,
                current_user: User = Depends(get_current_active_user),
                path: Optional[str] = None,
                ):
    
    file_local = await save_file(file, path)
    return {"file_name":file.filename, # hash随机命名
            "content_type": file.content_type,
            "path": file_local
    }


@router.get("/download_file/{file_name:path}", summary="下载文件")
async def download_file(
    file_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    从服务器安全地下载文件。
    - file_name: 要下载的文件的名称或相对路径。
    """
    print("下载文件:", file_name)  # Debug log
    try:
        # 构建文件的完整路径并标准化
        safe_path = None
        for base_dir in ALLOWED_BASE_DIRS:
            # 尝试在每个允许的目录下查找文件
            candidate_path = os.path.abspath(os.path.join(base_dir, file_name))
            # 检查路径是否在当前基础目录下且是一个文件
            if os.path.isfile(candidate_path):
                safe_path = candidate_path
                break  # 找到第一个匹配的文件即停止

        # 检查文件是否存在于任何允许的目录中
        if not safe_path:
            # 构建详细的错误信息，方便调试
            checked_paths = [os.path.join(dir, file_name) for dir in ALLOWED_BASE_DIRS]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文件未找到。已检查路径: {checked_paths}"
            )


        # 提取纯文件名用于响应头
        response_file_name = os.path.basename(safe_path)
        
        # 动态推断 MIME 类型
        media_type, _ = mimetypes.guess_type(safe_path)
        print(f"Guessed MIME type for {file_name}: {media_type}") # Debug log
        if media_type is None:
            media_type = 'application/octet-stream' # 如果无法推断，则使用默认值

        return FileResponse(
            path=safe_path,
            filename=response_file_name,
            media_type=media_type
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"下载文件时发生错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务器内部错误。"
        )

# 获取任务状态接口
@router.post(
        "/result_status/{task_id}",
        #tags=["Optimization"],
        summary="获取任务状态")
async def get_task_status(task_id: str, #authorization : str = Form()):
                          current_user: User = Depends(get_current_active_user)
):
    # 验证授权
    #authenticate(authorization)
    status = await Tasks.get(task_id=task_id)
    return status


@router.post("/conversation/{conversation_id}", summary="获取单个会话", response_model=ConversationOut)
async def get_conversation(request: Request, conversation_id: str, #authorization : str = Form()):
                           current_user: User = Depends(get_current_active_user)
):
    # 验证授权
    #await authenticate(authorization)
    # 获取会话并预加载相关的任务
    conver = await Conversations.get(conversation_id=conversation_id).prefetch_related("tasks")
    return conver

@router.post("/conversation_all/{user_id}", summary="获取全部会话")
async def get_all_conversations(request: Request, #user_id: str, authorization : str = Form()):
                                current_user: User = Depends(get_current_active_user)
):
    # 验证授权
    #await authenticate(authorization)
    conversations = await Conversations.filter(user_id=current_user.user_id).all()
    return conversations

@router.delete("/conversation/{conversation_id}", summary="删除会话及其所有关联数据")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    删除一个会话，包括：
    - 会话本身
    - 该会话下的所有任务
    - 每个任务在 Redis 中的对话历史
    """
    redis_client = request.app.state.redis

    # 1. 查找会话
    conversation = await Conversations.get_or_none(
        conversation_id=conversation_id, user_id=current_user.user_id
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or does not belong to the current user."
        )

    # 2. 查找并删除关联的任务及其 Redis 历史
    associated_tasks = await Tasks.filter(conversation_id=conversation_id)
    if redis_client:
        user_task_key = get_user_task_key(current_user.user_id)
        for task in associated_tasks:
            task_id_str = str(task.task_id)
            message_key = get_message_key(current_user.user_id, task_id_str)
            # 从用户任务哈希中删除任务
            await redis_client.hdel(user_task_key, task_id_str)
            # 删除任务的消息列表
            await redis_client.delete(message_key)

    # 3. 明确删除所有关联的任务
    for task in associated_tasks:
        await task.delete()

    # 4. 最后删除会话
    await conversation.delete()
    
    return {"message": "会话及所有关联数据已成功删除"}