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


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    解码 token 并获取当前用户信息。
    现在它依赖于 oauth2_scheme，会自动从 'Authorization: Bearer <token>' 头中提取 token。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_token(token)
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    
    # 返回 Pydantic 模型而不是字典，以便 FastAPI 进行类型检查
    user = await Users.get_or_none(email=email)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    """获取当前活跃用户"""
    # 这里可以添加检查用户是否被禁用的逻辑
    # if current_user.disabled:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def authenticate(authorization : str):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的授权令牌格式，应为 'Bearer <API_KEY>'"
        )
    
    await authenticate_user(authorization.split("Bearer ")[1])
