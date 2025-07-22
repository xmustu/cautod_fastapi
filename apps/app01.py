from fastapi import APIRouter
from fastapi import Request
from fastapi import Form
from fastapi import status
from fastapi.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
from pydantic import ValidationError 
from database.models_1 import *
from typing import List, Optional

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
    
@user.get("/login")
async def login():
    return {"login": "login"}

@user.post("/login")
async def login(request: Request,
                email: str = Form(),
                password: str = Form()):
    errors = []
    user = a
    return {"login": "login"}


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
                             password_hash=user_in.pwd,
        )
        return user
    except ValidationError as e:
        errors_list = json.loads(e.json())
        for item in errors_list:
            errors.append(item.get("loc")[0] + ": " + item.get("msg"))
        return {"request": request, "errors": errors}
        #return templates.TemplateResponse("auth/register.html", 
        #                                  {"request": request, "errors": errors})

