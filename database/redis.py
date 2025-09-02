import redis.asyncio as redis
from redis.exceptions import ConnectionError, TimeoutError
from config import Settings

settings = Settings()

# redis 连接池
redis_pool = redis.ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    #password=settings.REDIS_PASSWORD,  # 密码
    decode_responses=True,  # 自动解码响应
    encoding='utf-8',  # 设置编码
)


async def redis_connect():
    try:
        redis_client = redis.Redis(connection_pool=redis_pool)
        sig = await redis_client.ping()  # 测试连接
        print(sig,", Redis connected.")
        return redis_client
    except ConnectionError:
        print("Redis connection error")
    except TimeoutError:
        print("Redis connection timed out")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
