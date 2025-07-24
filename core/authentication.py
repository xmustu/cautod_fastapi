from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from fastapi import HTTPException
from fastapi import status
from fastapi import Form
from database.models_1 import *
from core.hashing import Hasher
from pydantic import BaseModel
from jwt.exceptions import InvalidTokenError


SECRET_KEY = "2703d9889343165118045a6fae0d1f42b3ee721ae803063dbea52a36fe92ede8"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
ACCESS_TOKEN_EXPIRE_DAYS = 7

class Token(BaseModel):
    status: str
    token : str

class User(BaseModel):
    user_id: int
    email: str
    created_at: datetime
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


def create_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp":datetime.now(timezone.utc) + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)})
    encode_jwt = jwt.encode(
        to_encode,  # 要通过TOKEN传输的内容
        SECRET_KEY, # JWT签名的密钥
        algorithm=ALGORITHM, # JWT签名的算法
    )
    return encode_jwt


def verify_token(token: str ):
    """验证JWT令牌并返回解码后的内容"""
    try:
        playroad = jwt.decode(
            token,
            SECRET_KEY,  # JWT签名的密钥
            algorithms=[ALGORITHM]  # JWT签名的算法
        )
        print("playroad: ", playroad)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return playroad

async def authenticate_user(token: str):
    user = await get_current_user(token)

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invlid authorization!")


async def get_current_user(token: str):
    """获取当前用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        playroad = verify_token(token)
        print("playroad: ", playroad)
        email = playroad.get("sub")
        if email is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    
    user = await Users.filter(email=email).values("user_id", "email", "created_at")
    return user

def get_current_active_user(current_user: dict = Depends(get_current_user)):
    """获取当前活跃用户"""
    #if current_user.get("disabled"):
    #    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user


async def authenticate(authorization : str):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的授权令牌格式，应为 'Bearer <API_KEY>'"
        )
    
    await authenticate_user(authorization.split("Bearer ")[1])