from typing import Optional
import os
import mimetypes

from fastapi import APIRouter
from fastapi import Request
from fastapi import File, UploadFile
from fastapi.templating import Jinja2Templates
from fastapi import Depends
from fastapi import status
from fastapi import Form
from fastapi import HTTPException
from fastapi import Response
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from pathlib import Path

from core.authentication import authenticate
from core.authentication import get_current_active_user
# 修改后 (请直接复制)：
from apps.schemas.user import UserResponse as User
from core.permissions import PermissionChecker
from core.system_config import check_file_size_async, check_maintenance_mode
from database.models import *

from apps.routes.chat import get_message_key, get_user_task_key

from config import settings
from apps.schemas import FileRequest
from apps.schemas import ConversationOut

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

async def save_file(file, path: Optional[str] = None, conversation_id: int = None, task_id: int = None):
    base_dir = settings.DIRECTORY
    if path == None:
        if base_dir:
            # 使用环境变量定义的目录作为基础
            path = os.path.join(base_dir, str(conversation_id), str(task_id))
        else:
            path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "files", str(conversation_id), str(task_id)))
        os.makedirs(path, exist_ok=True)
    print("path: ", path)
    res = await file.read()
    # 注意：文件大小检查已经在 upload_file 接口中完成
    #hash_name = hashlib.md5(file.filename.encode()).hexdigest()[:16]
    #file_name = f"{hash_name}.{file.filename.rsplit('.', 1)[-1]}"
    # full_file = f"{path}\{file.filename}"
    full_file = str(Path(path) / file.filename)
    with open(full_file, "wb") as f:
        f.write(res)
    await file.close()
    return full_file



@router.get("/")
def home(request: Request, alert: Optional[str] = None):

    return templates.TemplateResponse(
        "home.html", {"request": request, "alert": alert}
    )

@router.post("/model", response_class=Response)
async def get_model(request: FileRequest,
              current_user: User = Depends(check_maintenance_mode)):
    
    # 验证文件归属
    task = await Tasks.get_or_none(
        task_id=request.task_id,
        user_id=current_user.user_id,
        conversation_id=request.conversation_id
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="model does not belong to the current user/conversation."
        )
    # 传递模型文件
    try:
        # 构建文件路径
        #file_path = Path("files") / str(request.conversation_id) / str(request.task_id) / request.file_name
        base_dir = settings.DIRECTORY or "files"
    
        file_path =   Path(base_dir) / str(request.conversation_id) / str(request.task_id) / request.file_name
        print(f"请求模型文件地址: {file_path}")
        # 验证文件存在
        if not Path(file_path).is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"STL 文件不存在: {file_path}"
            )
        # 简单校验扩展名
        #if not file_path.lower().endswith(".stl"):
        if file_path.suffix.lower() != ".stl":
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="仅支持 .stl 格式文件"
            )

        with open(file_path, "rb") as f:
            stl_content = f.read()
        return Response(content=stl_content, media_type="application/sla")
    
    # 文件级错误
    except PermissionError as e:
        print(f"文件权限错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"无权限读取文件: {e}"
        )
    except OSError as e:
        print(f"文件系统错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件读取失败: {e}"
        )
    # 兜底
    except Exception as e:
        print(f"处理模型文件时发生未知错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"未知错误: {e}"
        )
    finally:
        pass
        # 确保临时文件被删除
        #if os.path.exists(file_path):
        #    os.unlink(file_path)
        #)
@router.post("/upload_file", summary="上传文件")
async def upload_file(*, 
                file: UploadFile,
                conversation_id: str = Form(...),
                task_id: int = Form(...),
                current_user: User = Depends(check_maintenance_mode),
                path: Optional[str] = None,

                ):
    # 检查文件大小限制
    # 读取文件内容检查大小
    file_content = await file.read()
    await check_file_size_async(len(file_content))
    
    # 将内容写回到文件对象（使用 BytesIO 包装以便 save_file 可以重新读取）
    from io import BytesIO
    file.file = BytesIO(file_content)
    file.file.seek(0)
    
    file_local = await save_file(file, path, conversation_id, task_id)
    return {"file_name":file.filename, 
            "content_type": file.content_type,
            "path": file_local
    }


@router.post("/download_file", summary="下载文件")
async def download_file(
    request: FileRequest,
    current_user: User = Depends(check_maintenance_mode)
):
    """
    从服务器安全地下载文件。
    - file_name: 要下载的文件的名称或相对路径。
    """
    print("下载文件:", request.file_name)  # Debug log
    try:
        # # 构建文件的完整路径并标准化
        # safe_path = None
        # for base_dir in ALLOWED_BASE_DIRS:
        #     # 尝试在每个允许的目录下查找文件
        #     candidate_path = os.path.abspath(os.path.join(base_dir, file_name))
        #     # 检查路径是否在当前基础目录下且是一个文件
        #     if os.path.isfile(candidate_path):
        #         safe_path = candidate_path
        #         break  # 找到第一个匹配的文件即停止

        # # 检查文件是否存在于任何允许的目录中
        # if not safe_path:
        #     # 构建详细的错误信息，方便调试
        #     checked_paths = [os.path.join(dir, file_name) for dir in ALLOWED_BASE_DIRS]
        #     raise HTTPException(
        #         status_code=status.HTTP_404_NOT_FOUND,
        #         detail=f"文件未找到。已检查路径: {checked_paths}"
        #     )


        # # 提取纯文件名用于响应头
        # response_file_name = os.path.basename(safe_path)
        
        
        # 验证归属权
        task = await Tasks.get_or_none(
        task_id=request.task_id,
        user_id=current_user.user_id,
        conversation_id=request.conversation_id
        )
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found or does not belong to the current user/conversation."
            )
        
        # construct user's file path according to conversation_id and task_id
        # 创建任务的文件存放目录
        # 使用settings中的DIRECTORY作为基础目录，若未设置则默认使用"files"
        base_dir = Path(settings.DIRECTORY) if settings.DIRECTORY else Path("files")
  
        # 构建目标目录路径：上一级目录/files/会话ID
        task_dir = base_dir / str(request.conversation_id) / str(request.task_id)

        # 关键：前端可能把 agent 返回的“路径字符串”原样带回来（甚至是绝对 Windows 路径）
        # 为了安全与可映射性：始终只允许在 task_dir 下取文件。
        raw_name = str(request.file_name or "")
        normalized = raw_name.replace("\\", "/").strip()

        # 去掉形如 "C:/..." 的驱动器前缀
        if len(normalized) >= 3 and normalized[1] == ":":
            normalized = normalized[2:].lstrip("/")

        # 如果字符串里包含 "/{conversation_id}/{task_id}/" 则截取其后部分作为相对路径
        marker = f"/{request.conversation_id}/{request.task_id}/"
        lower_normalized = normalized.lower()
        lower_marker = marker.lower()
        idx = lower_normalized.find(lower_marker)
        if idx != -1:
            rel = normalized[idx + len(marker):]
        else:
            # 否则退化为“仅文件名”，仍然保证落在 task_dir 下
            rel = os.path.basename(normalized)

        rel = rel.replace("\\", "/").strip().lstrip("/")
        if not rel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文件未找到：{request.file_name}",
            )

        rel_parts = [p for p in rel.split("/") if p not in ("", ".")]
        # 禁止路径穿越
        if any(p == ".." for p in rel_parts) or any(":" in p for p in rel_parts):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="非法文件路径请求。",
            )

        safe_rel = Path(*rel_parts)
        file = task_dir / safe_rel
        # 💥 最小修复点：增加文件存在性检查 💥
        if not file.is_file():
            print(f"File not found at expected path: {file}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文件未找到：{request.file_name}"
            )
        # 动态推断 MIME 类型
        media_type, _ = mimetypes.guess_type(file)
        print(f"Guessed MIME type for {request.file_name}: {media_type}") # Debug log
        if media_type is None:
            media_type = 'application/octet-stream' # 如果无法推断，则使用默认值
        print()
        return FileResponse(
            path=file,
            filename=file.name,
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
async def get_task_status(
    task_id: str,
    current_user: User = Depends(check_maintenance_mode)
):
    """
    获取任务状态
    - 普通用户：只能查看自己的任务状态
    - 管理员：可以查看任何任务的状态
    """
    # 检查用户是否为管理员
    is_admin = await PermissionChecker.is_admin(current_user.email)
    
    # 获取任务
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在"
        )
    
    # 权限验证：普通用户只能查看自己的任务
    if not is_admin and task.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限查看此任务"
        )
    
    return task


@router.post("/conversation/{conversation_id}", summary="获取单个会话", response_model=ConversationOut)
async def get_conversation(
    request: Request,
    conversation_id: str,
    current_user: User = Depends(check_maintenance_mode)
):
    """
    获取单个会话
    - 普通用户：只能查看自己的会话
    - 管理员：可以查看任何用户的会话
    """
    # 检查用户是否为管理员
    is_admin = await PermissionChecker.is_admin(current_user.email)
    
    # 获取会话并预加载相关的任务
    conversation = await Conversations.get_or_none(
        conversation_id=conversation_id
    ).prefetch_related("tasks")
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )
    
    # 权限验证：普通用户只能查看自己的会话
    if not is_admin and conversation.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限查看此会话"
        )
    
    return conversation

@router.post("/conversation_all/{user_id}", summary="获取全部会话")
async def get_all_conversations(
    request: Request,
    user_id: str,
    current_user: User = Depends(check_maintenance_mode)
):
    """
    获取全部会话
    - 普通用户：只能查看自己的会话（忽略路径中的user_id参数）
    - 管理员：可以查看指定user_id的会话，或查看所有会话（user_id='all'）
    
    注意：为保持向后兼容，保留了user_id路径参数，但普通用户会被强制只能查看自己的会话
    """
    # 检查用户是否为管理员
    is_admin = await PermissionChecker.is_admin(current_user.email)
    
    if is_admin:
        # 管理员可以查看指定用户的会话，如果user_id为'all'或空则查看所有会话
        if user_id and user_id != 'all':
            try:
                conversations = await Conversations.filter(user_id=int(user_id)).all()
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的用户ID"
                )
        else:
            conversations = await Conversations.all()
    else:
        # 普通用户只能查看自己的会话
        conversations = await Conversations.filter(user_id=current_user.user_id).all()
    
    return conversations

@router.delete("/conversation/{conversation_id}", summary="删除会话及其所有关联数据")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    current_user: User = Depends(check_maintenance_mode)
):
    """
    删除一个会话，包括：
    - 会话本身
    - 该会话下的所有任务
    - 每个任务在 Redis 中的对话历史
    
    权限控制：
    - 普通用户：只能删除自己的会话
    - 管理员：可以删除任何用户的会话
    """
    redis_client = request.app.state.redis
    
    # 检查用户是否为管理员
    is_admin = await PermissionChecker.is_admin(current_user.email)

    # 1. 查找会话
    conversation = await Conversations.get_or_none(conversation_id=conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在"
        )
    
    # 2. 权限验证：普通用户只能删除自己的会话
    if not is_admin and conversation.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有权限删除此会话"
        )

    # 3. 查找并删除关联的任务及其 Redis 历史
    associated_tasks = await Tasks.filter(conversation_id=conversation_id)
    if redis_client:
        # 使用会话所属用户的ID（可能是当前用户或其他用户）
        conversation_owner_id = conversation.user_id
        user_task_key = get_user_task_key(conversation_owner_id)
        
        for task in associated_tasks:
            task_id_str = str(task.task_id)
            message_key = get_message_key(conversation_owner_id, task_id_str)
            # 从用户任务哈希中删除任务
            await redis_client.hdel(user_task_key, task_id_str)
            # 删除任务的消息列表
            await redis_client.delete(message_key)

    # 4. 明确删除所有关联的任务
    for task in associated_tasks:
        await task.delete()

    # 5. 最后删除会话
    await conversation.delete()
    
    return {"message": "会话及所有关联数据已成功删除"}


@router.get("/dify-chat-config", summary="获取 Dify 聊天配置")
async def get_dify_chat_config():
    """
    获取 Dify 聊天嵌入配置
    这是一个公开端点，不需要认证，用于前端初始化聊天组件
    """
    return {
        "token": settings.DIFY_CHAT_TOKEN,
        "baseUrl": settings.DIFY_CHAT_BASE_URL,
    }


@router.get("/dify-chat-embed", summary="获取 Dify 聊天嵌入代码")
async def get_dify_chat_embed(request: Request):
    """
    获取完整的 Dify 聊天嵌入代码（HTML/JS/CSS）
    这是一个公开端点，不需要认证，返回可直接插入页面的完整嵌入代码
    """
    # 清理 baseUrl，确保没有末尾斜杠
    base_url = settings.DIFY_CHAT_BASE_URL.rstrip('/')
    token = settings.DIFY_CHAT_TOKEN
    
    # 使用模板渲染嵌入代码
    return templates.TemplateResponse(
        "dify_embed.html",
        {
            "request": request,
            "token": token,
            "base_url": base_url,
        },
        media_type="text/html"
    )