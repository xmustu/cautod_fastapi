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
from database.models_1 import *
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
                authorization : str = Form(),
                path: Optional[str] = None,
                ):
    
    # 验证授权
    authenticate(authorization)
    file_local = await save_file(file, path)
    return {"file_name":file.filename, # hash随机命名
            "content_type": file.content_type,
            "path": file_local
    }
    
    

@router.post("/download_file/{file_name}", summary="下载文件")
async def download_file(
                  file_name: str,
                  authorization : str = Form(),
                  path: Optional[str] = None):

    # 验证授权
    authenticate(authorization)

    """
    raise NotimpltedError

    验证文件所有权， 待实施

    """


    if path == None:
        path = "files"
    return FileResponse(f"{path}/{file_name}")
    
    

# 获取任务状态接口
@router.post(
        "/result_status/{task_id}",
        #tags=["Optimization"],
        summary="获取任务状态")
async def get_task_status(task_id: str, authorization : str = Form()):
    # 验证授权
    authenticate(authorization)
    status = await Tasks.get(task_id=task_id)
    return status


@router.post("/conservation/{conversation_id}",summary="获取单个会话")
async def get_conservation(request: Request, conversation_id: str, authorization : str = Form()):
    # 验证授权
    authenticate(authorization)
    conver = await Conversations.get(conversation_id=conversation_id)
    return conver

@router.post("/conservation_all/{user_id}", summary="获取全部会话")
async def get_conservation(request: Request, user_id: str, authorization : str = Form()):
    # 验证授权
    authenticate(authorization)
    conversations = await Conversations.filter(user_id=user_id).all()
    return conversations
