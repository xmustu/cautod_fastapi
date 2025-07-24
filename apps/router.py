from typing import Optional
from fastapi import APIRouter
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
templates = Jinja2Templates(directory="templates")
router = APIRouter()

@router.get("/")
def home(request: Request, alert: Optional[str] = None):

    return templates.TemplateResponse(
        "home.html", {"request": request, "alert": alert}
    )

@router.post("/upload_file")
def upload_file(request: Request):
    
    return {"request": request, "message": "Upload file page"}
    
    

@router.get("/download_file")
def upload_file(request: Request):
    
    return {"request": request, "message": "downloadfile page"}
    
    

# 获取任务状态接口
@router.get(
        "/result_status/{task_id}",
        #tags=["Optimization"],
        summary="获取任务状态")
def get_task_status(task_id: str):

    return 0


@router.get("/conservation/{conversation_id}")
def get_conservation(request: Request, conversation_id: str):
    return 0

@router.get("/conservation_all/{user_id}", summary="获取全部会话")
def get_conservation(request: Request, user_id: str):
    return 0
    