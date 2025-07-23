from fastapi import APIRouter
from fastapi import Request
from fastapi import Form
from fastapi import status
from fastapi import responses
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
from pydantic import ValidationError 
from database.models_1 import *
from core.hashing import Hasher
from core.authentication import create_token
from typing import List, Optional

import json

async def authenticate_user(email: str, password: str):
    user = await Users.filter(email=email)
    print("user: ", user)
    for i in user:
        print("i", i)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
       # return False
    if not Hasher.verify_password(plain_password=password, hashed_password=user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    return user

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
    
@user.get("/login")
async def login():
    return {"login": "login"}

@user.post("/login")
async def login(request: Request,
                email: str = Form(),
                password: str = Form()):

    user = await Users.get(email=email)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not Hasher.verify_password(plain_password=password, hashed_password=user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")
    
    access_token = create_token(data={"sub": user.email})
    response = responses.RedirectResponse(
        "/?alert=Successfully Logged In", status_code=status.HTTP_302_FOUND
    )
    response.set_cookie(
        key="access_token", value=f"Bearer {access_token}", httponly=True
    )
    return response


@user.get("/register")
async def register(request: Request):
    return {"content":"register page"}
    #return templates.TemplateResponse("auth/register.html", {"request": request})

@user.post("/register")
async def register(request: Request, 
                   user_in : UserIn):
    errors  = []
    try:
        user = await Users.create(name=user_in.user_id,
                             email=user_in.email,
                             password_hash=Hasher.get_password_hash(user_in.pwd),
        )
        return user
    except ValidationError as e:
        errors_list = json.loads(e.json())
        for item in errors_list:
            errors.append(item.get("loc")[0] + ": " + item.get("msg"))
        return {"request": request, "errors": errors}
        #return templates.TemplateResponse("auth/register.html", 
        #                                  {"request": request, "errors": errors})

