"""
安全响应头中间件
添加各种安全相关的 HTTP 响应头
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    安全响应头中间件
    
    添加以下安全响应头：
    - X-Content-Type-Options: 防止 MIME 类型嗅探
    - X-Frame-Options: 防止点击劫持
    - X-XSS-Protection: XSS 防护（旧浏览器）
    - Strict-Transport-Security: HSTS（HTTPS 环境）
    - Content-Security-Policy: CSP 策略
    - Referrer-Policy: 控制 Referer 头
    - Permissions-Policy: 控制浏览器功能权限
    """
    
    def __init__(self, app, enable_hsts: bool = False, csp_policy: str = None):
        """
        初始化安全响应头中间件
        
        Args:
            app: FastAPI 应用实例
            enable_hsts: 是否启用 HSTS（仅在 HTTPS 环境启用）
            csp_policy: Content-Security-Policy 策略字符串，如果为 None 则使用默认策略
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.csp_policy = csp_policy or self._get_default_csp()
    
    def _get_default_csp(self) -> str:
        """
        获取默认的 Content-Security-Policy 策略
        
        注意：这是一个相对宽松的策略，允许内联脚本和样式
        生产环境应根据实际需求调整
        """
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    
    def _get_swagger_csp(self) -> str:
        """
        获取 Swagger UI 专用的宽松 CSP 策略
        允许 Swagger UI 正常工作所需的所有资源
        """
        return (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob:; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https: blob:; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求并添加安全响应头
        """
        response = await call_next(request)
        
        # 添加安全响应头（FastAPI 的响应对象支持直接修改 headers）
        if hasattr(response, 'headers'):
            self._add_security_headers(response, request)
        
        return response
    
    def _add_security_headers(self, response, request: Request):
        """
        添加安全响应头到响应对象
        
        Args:
            response: FastAPI 响应对象（支持 headers 属性）
            request: FastAPI 请求对象
        """
        # 检查是否为 Swagger UI 相关路径
        path = request.url.path
        is_swagger_path = any(path.startswith(prefix) for prefix in [
            "/docs",
            "/openapi.json",
            "/redoc",
            "/swagger"
        ])
        
        # 1. X-Content-Type-Options: 防止 MIME 类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # 2. X-Frame-Options: 防止点击劫持
        # Swagger UI 需要允许在 iframe 中显示，所以使用 SAMEORIGIN
        if is_swagger_path:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        else:
            response.headers["X-Frame-Options"] = "DENY"
        
        # 3. X-XSS-Protection: XSS 防护（旧浏览器支持）
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # 4. Strict-Transport-Security: HSTS（仅在 HTTPS 环境启用）
        if self.enable_hsts and request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        
        # 5. Content-Security-Policy: CSP 策略
        # 为 Swagger UI 使用更宽松的策略
        if is_swagger_path:
            response.headers["Content-Security-Policy"] = self._get_swagger_csp()
        else:
            response.headers["Content-Security-Policy"] = self.csp_policy
        
        # 6. Referrer-Policy: 控制 Referer 头
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 7. Permissions-Policy: 控制浏览器功能权限
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "speaker=()"
        )
        
        # 8. X-Permitted-Cross-Domain-Policies: 防止 Flash/PDF 跨域策略
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        
        # 9. Clear-Site-Data: 清理站点数据（可选，根据需要启用）
        # response.headers["Clear-Site-Data"] = '"cache", "cookies", "storage"'

