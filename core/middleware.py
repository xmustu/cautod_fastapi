from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware


import time
import logging
from collections import defaultdict

#logger = logging.getLogger("uvicorn.access")
#logger.disable = True  # 禁用默认的访问日志

def logger(message: str):
    print("message: ",message)

def count_time_middleware(app: FastAPI):
    # 打印每个请求所用的时间
    @app.middleware("http")
    async def count_time(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        duration = time.time() - start_time
        print(f"请求 {request.url} 耗时: {duration:.4f} 秒")
        return response
    
    @app.middleware("http")
    async def logging(request: Request, call_next):
        message = f"{request.client.host}:{request.client.port}  {request.method} {request.url.path}"
        logger(message)
        response = await call_next(request)
        return response

def request_response_middleware(app: FastAPI):
    
    # 首先获取请求
    @app.middleware("http")
    async def only_for_request(request: Request, call_next):
        print(f"获取到了请求路径： {request.url}")
        """
        仅对特定请求进行处理的中间件示例
        """
        response = await call_next(request)
        # 可以在这里添加额外的逻辑
        return response

    # 最后返回响应
    @app.middleware("http")
    async def only_for_response(request: Request, call_next):
        response = await call_next(request)
        print(f"返回了响应结果： {response.headers['Content-Type'] if 'Content-Type' in response.headers else 'No Content-Type'}")
        """
        仅对特定响应进行处理的中间件示例
        """
        # 可以在这里添加额外的逻辑
        return response
    



# 访问速率限制的中间件示例
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: FastAPI, rate_limit: int = 100):
        super().__init__(app)
        self.rate_limit = rate_limit
        self.request_records: dict[str, float] = defaultdict(float) # defacultdict 当访问键值对不存在时，新建

    # 重载

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        current_time = time.time()

        if current_time - self.request_records[ip] < 5:
            return Response(content="Too Many Requests", status_code=429)
        
        response = await call_next(request)
        self.request_records[ip] = current_time
        return response
    
    