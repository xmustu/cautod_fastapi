from fastapi import APIRouter
from fastapi import Request
from fastapi import Form
from fastapi import status
from fastapi import responses
from fastapi import Depends
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, field_validator
from pydantic import ValidationError 
from database.models_1 import *
from core.hashing import Hasher
from core.authentication import create_token
from typing import List, Optional
from core.authentication import Token, User
from core.authentication import get_current_active_user
import json





user = APIRouter()

templates = Jinja2Templates(directory="templates")

class UserIn(BaseModel):
    user_id : int
    email : str
    pwd : str

    #@field_validator('name')
    #def name_must_alpha(cls, v):
    #    assert v.isalpha(), 'name must be alpha'
    #    return v
 

@user.get("/{user_id}")
async def get_user(user_id: int):
    user = await Users.get(user_id=user_id).values("user_id", "email", "created_at")
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@user.get("/me")
async def get_me(current_user: dict = Depends(get_current_active_user)):
    return current_user

@user.get("/login")
async def login():
    return {"login": "login"}

@user.post("/login",summary="用户登录，获取JWT令牌")
async def login(request: Request,
                email: str = Form(),
                password: str = Form()):

    user = await Users.get(email=email)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not Hasher.verify_password(plain_password=password, hashed_password=user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    access_token = create_token(data={"sub": user.email})
    """
    response = responses.RedirectResponse(
        "/?alert=Successfully Logged In", status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return response
    """
    return {"status":"success", "access_token":access_token}

@user.post("/google_login")
async def google_login():
    return {"login": "google login"}

@user.get("/register")
async def register(request: Request):
    return {"content":"register page"}
    #return templates.TemplateResponse("auth/register.html", {"request": request})

@user.post("/register",summary="用户注册")
async def register(request: Request, 
                   user_in : UserIn):
    errors  = []
    try:
        user = await Users.create(name=user_in.user_id,
                             email=user_in.email,
                             password_hash=Hasher.get_password_hash(user_in.pwd),
        )
        #return user
        return responses.RedirectResponse(
            "/?alert=Successfully%20Registered", status_code=status.HTTP_302_FOUND
        )
    except ValidationError as e:
        errors_list = json.loads(e.json())
        for item in errors_list:
            errors.append(item.get("loc")[0] + ": " + item.get("msg"))
        return {"request": request, "errors": errors}
        #return templates.TemplateResponse("auth/register.html", 
        #                                  {"request": request, "errors": errors})

