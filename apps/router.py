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
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
templates = Jinja2Templates(directory="templates")
router = APIRouter()

async def save_file(file, path: Optional[str] = None):
    if path == None:
        path = "files"
    res = await file.read()
    hash_name = hashlib.md5(file.filename.encode()).hexdigest()[:16]
    file_name = f"{hash_name}.{file.filename.rsplit('.', 1)[-1]}"
    full_file = f"{path}/{file_name}"
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
                #authorization : str = Form(),
                current_user: User = Depends(get_current_active_user),
                path: Optional[str] = None,
                ):
    
    # 验证授权
    #authenticate(authorization)
    file_local = await save_file(file, path)
    return {"file_name":file.filename, # hash随机命名
            "content_type": file.content_type,
            "path": file_local
    }
import os
import mimetypes

@router.get("/download_file/{file_name:path}", summary="下载文件")
async def download_file(
    file_name: str,
    current_user: User = Depends(get_current_active_user)
):
    """
    从服务器安全地下载文件。
    - file_name: 要下载的文件的名称。
    """
    try:
        # --- 健壮的路径计算 ---
        # 获取当前文件(router.py)所在的目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        # 从 'apps' 目录上升到项目根目录
        project_root = os.path.dirname(current_file_dir)
        # 安全地拼接 'files' 目录
        base_dir = os.path.join(project_root, "files")

        # 构建安全的文件路径，防止目录遍历攻击
        safe_path = os.path.abspath(os.path.join(base_dir, file_name))

        if not safe_path.startswith(base_dir):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="禁止访问非授权目录。"
            )

        if not os.path.isfile(safe_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件未找到。"
            )

        # 提取纯文件名用于响应头
        response_file_name = os.path.basename(safe_path)
        
        # 动态推断 MIME 类型
        media_type, _ = mimetypes.guess_type(safe_path)
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
