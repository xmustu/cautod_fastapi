from datetime import datetime, timedelta, timezone
import jwt

SECRET_KEY = "2703d9889343165118045a6fae0d1f42b3ee721ae803063dbea52a36fe92ede8"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
def create_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp":datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    encode_jwt = jwt.encode(
        to_encode,  # 要通过TOKEN传输的内容
        SECRET_KEY, # JWT签名的密钥
        algorithm=ALGORITHM, # JWT签名的算法
    )
    return encode_jwt




def verify_token(token):
    pass