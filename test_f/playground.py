from time import sleep

from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/redis")
async def redis_set(request: Request):
    
    value = await request.app.state.redis.get("fastapi_redis")

    if value is None:
        sleep(5)
        hi = 'hey, redis!'
        await request.app.state.redis.set(
            "fastapi_redis",  #键名
            hi,     #键值
            ex=60  # 设置过期时间为60秒
            )
        return hi
    return value