from fastapi import FastAPI
from fastapi import Request
from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from datetime import datetime
import json

from typing import Optional, Dict, Any
import time

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
    



# 访问速率限制的中间件（基于 Redis）
class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基于 Redis 的 API 速率限制中间件
    使用固定时间窗口算法（每分钟）
    """
    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.time_window = 60  # 时间窗口：60秒（1分钟）
        self.redis_client = None
        
    async def dispatch(self, request: Request, call_next):
        # 跳过健康检查和静态文件
        if request.url.path in ["/docs", "/openapi.json", "/redoc", "/favicon.ico"]:
            return await call_next(request)
        
        # 跳过静态文件路径
        if request.url.path.startswith(("/static/", "/files/")):
            return await call_next(request)
        
        # 获取客户端标识（优先使用用户ID，否则使用IP）
        client_id = await self._get_client_id(request)
        
        # 从系统配置获取速率限制
        rate_limit = await self._get_rate_limit()
        
        # 如果速率限制为0或负数，则不限制
        if rate_limit <= 0:
            return await call_next(request)
        
        # 获取 Redis 客户端（从 app.state 获取）
        redis_client = None
        try:
            redis_client = request.app.state.redis
            self.redis_client = redis_client
        except AttributeError:
            pass
        
        # 检查速率限制
        if redis_client:
            is_allowed = await self._check_rate_limit_redis(redis_client, client_id, rate_limit)
        else:
            # 如果没有 Redis，使用内存版本（不推荐用于生产环境）
            is_allowed = await self._check_rate_limit_memory(client_id, rate_limit)
        
        if not is_allowed:
            return Response(
                content=json.dumps({
                    "detail": f"请求过于频繁，请稍后再试。限制：{rate_limit} 次/分钟"
                }),
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(self.time_window),
                    "X-RateLimit-Limit": str(rate_limit),
                    "X-RateLimit-Window": str(self.time_window)
                }
            )
        
        # 继续处理请求
        response = await call_next(request)
        
        # 添加速率限制响应头
        try:
            redis_client = request.app.state.redis
            remaining = await self._get_remaining_requests(redis_client, client_id, rate_limit)
        except:
            remaining = rate_limit
        
        response.headers["X-RateLimit-Limit"] = str(rate_limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Window"] = str(self.time_window)
        
        return response
    
    async def _get_client_id(self, request: Request) -> str:
        """
        获取客户端标识
        优先使用用户ID（如果已登录），否则使用IP地址
        """
        # 尝试从请求中获取用户信息
        try:
            # 检查是否有认证token
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                # 这里可以解析token获取用户ID，但为了简化，我们使用IP
                # 如果需要更精确的用户级别限制，可以在这里实现
                pass
        except:
            pass
        
        # 使用IP地址作为客户端标识
        client_ip = request.client.host if request.client else "unknown"
        return f"rate_limit:{client_ip}"
    
    async def _get_rate_limit(self) -> int:
        """
        从系统配置获取速率限制
        """
        try:
            from core.system_config import get_system_config_cached
            system_config = await get_system_config_cached()
            return system_config.api_rate_limit or 100
        except Exception as e:
            # 如果获取配置失败，返回默认值
            print(f"获取速率限制配置失败: {e}")
            return 100
    
    async def _check_rate_limit_redis(self, redis_client, client_id: str, rate_limit: int) -> bool:
        """
        使用 Redis 检查速率限制（固定时间窗口）
        """
        try:
            import time
            current_time = int(time.time())
            window_start = current_time - (current_time % self.time_window)
            key = f"{client_id}:{window_start}"
            
            # 获取当前窗口的请求数
            current_count = await self.redis_client.get(key)
            
            if current_count is None:
                # 第一次请求，设置计数为1，过期时间为时间窗口
                await self.redis_client.setex(key, self.time_window, 1)
                return True
            
            current_count = int(current_count)
            
            if current_count >= rate_limit:
                return False
            
            # 增加计数
            await self.redis_client.incr(key)
            # 更新过期时间（防止key过期）
            await self.redis_client.expire(key, self.time_window)
            
            return True
        except Exception as e:
            # Redis 连接失败时，允许请求通过（避免因Redis问题导致服务不可用）
            print(f"Redis速率限制检查失败: {e}，允许请求通过")
            return True
    
    async def _check_rate_limit_memory(self, client_id: str, rate_limit: int) -> bool:
        """
        使用内存检查速率限制（备用方案，不推荐用于生产环境）
        """
        import time
        current_time = time.time()
        window_start = int(current_time) - (int(current_time) % self.time_window)
        key = f"{client_id}:{window_start}"
        
        if not hasattr(self, '_memory_rate_limit'):
            self._memory_rate_limit = {}
        
        # 清理过期的记录
        expired_keys = [
            k for k, v in self._memory_rate_limit.items()
            if time.time() - v['timestamp'] > self.time_window
        ]
        for k in expired_keys:
            del self._memory_rate_limit[k]
        
        # 检查当前窗口的请求数
        if key not in self._memory_rate_limit:
            self._memory_rate_limit[key] = {'count': 1, 'timestamp': current_time}
            return True
        
        if self._memory_rate_limit[key]['count'] >= rate_limit:
            return False
        
        self._memory_rate_limit[key]['count'] += 1
        return True
    
    async def _get_remaining_requests(self, redis_client, client_id: str, rate_limit: int) -> int:
        """
        获取剩余请求数
        """
        if not redis_client:
            return rate_limit
        
        try:
            import time
            current_time = int(time.time())
            window_start = current_time - (current_time % self.time_window)
            key = f"{client_id}:{window_start}"
            
            current_count = await redis_client.get(key)
            if current_count is None:
                return rate_limit
            
            return max(0, rate_limit - int(current_count))
        except:
            return rate_limit
    
    
class FullRequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # --------------------------
        # 第一步：请求处理前 - 捕获并打印请求信息
        # --------------------------
        request_start_time = datetime.now()
        self._log_request_details(request, request_start_time)

        # --------------------------
        # 第二步：继续处理请求（不阻塞业务逻辑）
        # --------------------------
        # 特殊处理：SSE请求需保留请求体（避免后续读取失败）
        # 先读取请求体并缓存，后续再放回请求对象
        request_body: Optional[Dict[str, Any]] = None
        if request.method in ["POST", "PUT", "PATCH"] and request.headers.get(
            "Content-Type", ""
        ).startswith("application/json"):
            try:
                # 读取请求体（异步读取，避免阻塞）
                request_body = await request.json()
                # 将读取的请求体重新放回请求对象，供后续接口使用
                # （FastAPI的request.json()只能读取一次，需手动缓存）
                async def _get_body():
                    return json.dumps(request_body).encode("utf-8")
                request.body = _get_body
            except Exception as e:
                # 处理非JSON格式的请求体（如表单、原始文本）
                try:
                    raw_body = await request.body()
                    request_body = f"Raw body (length: {len(raw_body)}): {raw_body.decode('utf-8', errors='ignore')[:500]}"  # 限制显示长度
                except Exception as raw_e:
                    request_body = f"Failed to read body: {str(raw_e)}"

        # 继续执行后续接口逻辑，获取响应
        response = await call_next(request)

        # --------------------------
        # 第三步：请求处理后 - 打印响应耗时（可选）
        # --------------------------
        request_end_time = datetime.now()
        request_duration = (request_end_time - request_start_time).total_seconds() * 1000  # 转换为毫秒
        print(f"\n[请求结束] 耗时: {request_duration:.2f}ms | 结束时间: {request_end_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        print("=" * 80)

        return response

    def _log_request_details(self, request: Request, start_time: datetime) -> None:
        """格式化打印请求的所有关键信息"""
        # 1. 基础信息（时间、请求行、客户端）
        print("=" * 80)
        print(f"[请求开始] 时间: {start_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        print(f"请求行: {request.method} {request.url.path} {request.url.query if request.url.query else ''}")
        print(f"客户端: {request.client.host}:{request.client.port} (IP: {request.client.host}, 端口: {request.client.port})")
        print(f"完整URL: {str(request.url)}")

        # 2. 请求头信息
        print("\n[请求头信息]")
        headers: Dict[str, str] = dict(request.headers)
        for header_name, header_value in headers.items():
            # 敏感头信息（如Authorization）可选择性隐藏部分内容
            if header_name.lower() == "authorization" and header_value.startswith(("Bearer ", "Basic ")):
                print(f"  {header_name}: {header_value[:20]}... (已隐藏部分内容)")
            else:
                print(f"  {header_name}: {header_value}")

        # 3. 查询参数
        query_params: Dict[str, str] = dict(request.query_params)
        if query_params:
            print("\n[查询参数]")
            for param_name, param_value in query_params.items():
                print(f"  {param_name}: {param_value}")

        # 4. 路径参数（若有，如 /users/{user_id}）
        path_params: Dict[str, str] = dict(request.path_params)
        if path_params:
            print("\n[路径参数]")
            for param_name, param_value in path_params.items():
                print(f"  {param_name}: {param_value}")

        # 5. Cookie信息（若有）
        cookies: Dict[str, str] = dict(request.cookies)
        if cookies:
            print("\n[Cookie信息]")
            for cookie_name, cookie_value in cookies.items():
                print(f"  {cookie_name}: {cookie_value[:20]}... (已隐藏部分内容)")

        # 6. 请求体（已在dispatch中提前读取并缓存，此处直接打印）
        # 注：请求体的实际内容会在dispatch中单独处理并赋值，此处仅占位提示
        print("\n[请求体信息] (下方将在读取后打印)")

    async def _read_request_body(self, request: Request) -> Optional[str]:
        """安全读取请求体，避免阻塞和编码错误"""
        try:
            body = await request.body()
            if not body:
                return "Empty body"
            # 尝试按UTF-8解码，失败则用忽略错误模式
            return body.decode("utf-8", errors="ignore")
        except Exception as e:
            return f"Failed to read body: {str(e)}"