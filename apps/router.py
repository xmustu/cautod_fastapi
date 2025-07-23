from typing import Optional
from fastapi import APIRouter
from fastapi import Request
from fastapi.templating import Jinja2Templates
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
templates = Jinja2Templates(directory="templates")
router = APIRouter()

@router.get("/")
def home(request: Request, alert: Optional[str] = None):

    return templates.TemplateResponse(
        "home.html", {"request": request, "alert": alert}
    )


@router.get("/items/")
async def read_items(token: str = Depends(oauth2_scheme)):
    return {"token": token}