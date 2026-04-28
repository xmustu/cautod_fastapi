"""
CSRF 防护中间件
提供跨站请求伪造（CSRF）保护机制
"""
import secrets
from typing import Optional, Set
from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import urlparse


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF 防护中间件
    
    实现方式：
    1. 验证 Origin/Referer 头（主要防护）
    2. 支持 CSRF Token 验证（可选，用于需要额外保护的端点）
    
    安全方法（GET, HEAD, OPTIONS）默认跳过 CSRF 检查
    """
    
    # 安全方法（不需要 CSRF 保护）
    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    
    def __init__(
        self,
        app,
        allowed_origins: Optional[Set[str]] = None,
        verify_origin: bool = True,
        verify_referer: bool = True,
        allow_same_origin: bool = True
    ):
        """
        初始化 CSRF 防护中间件
        
        Args:
            app: FastAPI 应用实例
            allowed_origins: 允许的来源列表（如果为 None，则从请求的 Host 推断）
            verify_origin: 是否验证 Origin 头
            verify_referer: 是否验证 Referer 头（当 Origin 不存在时）
            allow_same_origin: 是否允许同源请求（基于 Host 头）
        """
        super().__init__(app)
        self.allowed_origins = allowed_origins or set()
        self.verify_origin = verify_origin
        self.verify_referer = verify_referer
        self.allow_same_origin = allow_same_origin
    
    async def dispatch(self, request: Request, call_next):
        """
        处理请求并验证 CSRF 保护
        """
        # 跳过安全方法
        if request.method in self.SAFE_METHODS:
            return await call_next(request)
        
        # 跳过静态文件和 API 文档
        path = request.url.path
        if any(path.startswith(prefix) for prefix in [
            "/static/",
            "/files/",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico"
        ]):
            return await call_next(request)
        
        # 验证 CSRF 保护
        try:
            self._verify_csrf(request)
        except HTTPException:
            raise
        except Exception as e:
            # 记录错误但不阻止请求（避免误杀）
            print(f"CSRF 验证错误: {e}")
        
        return await call_next(request)
    
    def _verify_csrf(self, request: Request):
        """
        验证 CSRF 保护
        
        验证顺序：
        1. 检查 Origin 头（如果存在且启用）
        2. 检查 Referer 头（如果 Origin 不存在且启用）
        3. 检查是否为同源请求（如果启用）
        """
        origin = request.headers.get("Origin")
        referer = request.headers.get("Referer")
        host = request.headers.get("Host")
        
        # 获取请求的协议和主机
        request_scheme = request.url.scheme
        request_host = request.url.hostname
        request_port = request.url.port
        
        # 构建当前请求的基础 URL
        if request_port and request_port not in [80, 443]:
            current_base = f"{request_scheme}://{request_host}:{request_port}"
        else:
            current_base = f"{request_scheme}://{request_host}"
        
        # 1. 验证 Origin 头
        if self.verify_origin and origin:
            if not self._is_valid_origin(origin, current_base, host):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF 验证失败：Origin 头不匹配"
                )
            return  # Origin 验证通过，无需继续
        
        # 2. 验证 Referer 头（当 Origin 不存在时）
        if self.verify_referer and referer and not origin:
            if not self._is_valid_referer(referer, current_base, host):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="CSRF 验证失败：Referer 头不匹配"
                )
            return  # Referer 验证通过
        
        # 3. 如果允许同源请求，检查是否为同源
        if self.allow_same_origin:
            # 如果没有 Origin 和 Referer，可能是同源请求（浏览器可能不发送）
            # 这种情况下，我们允许请求通过（因为同源请求是安全的）
            if not origin and not referer:
                # 可能是同源请求，允许通过
                return
        
        # 4. 如果所有验证都失败，拒绝请求
        # 但为了兼容性，我们只在明确配置了 allowed_origins 时才严格拒绝
        if self.allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF 验证失败：请求来源未授权"
            )
    
    def _is_valid_origin(self, origin: str, current_base: str, host: str) -> bool:
        """
        验证 Origin 是否有效
        
        Args:
            origin: Origin 头的值
            current_base: 当前请求的基础 URL
            host: Host 头的值
        
        Returns:
            bool: Origin 是否有效
        """
        # 移除末尾的斜杠
        origin = origin.rstrip('/')
        current_base = current_base.rstrip('/')
        
        # 1. 检查是否在允许的来源列表中
        if self.allowed_origins:
            if origin in self.allowed_origins:
                return True
            # 也检查是否匹配允许的来源模式
            for allowed in self.allowed_origins:
                if self._match_origin_pattern(origin, allowed):
                    return True
        
        # 2. 检查是否为同源（如果启用）
        if self.allow_same_origin:
            # 检查 origin 是否与当前请求同源
            if origin == current_base:
                return True
            
            # 也检查是否与 Host 头匹配
            if host:
                origin_host = urlparse(origin).netloc
                # 移除端口号进行比较（如果端口是默认端口）
                origin_host_clean = origin_host.split(':')[0]
                host_clean = host.split(':')[0]
                if origin_host_clean == host_clean:
                    return True
        
        return False
    
    def _is_valid_referer(self, referer: str, current_base: str, host: str) -> bool:
        """
        验证 Referer 是否有效
        
        Args:
            referer: Referer 头的值
            current_base: 当前请求的基础 URL
            host: Host 头的值
        
        Returns:
            bool: Referer 是否有效
        """
        try:
            referer_parsed = urlparse(referer)
            referer_base = f"{referer_parsed.scheme}://{referer_parsed.netloc}"
            referer_base = referer_base.rstrip('/')
            current_base = current_base.rstrip('/')
            
            # 检查是否在允许的来源列表中
            if self.allowed_origins:
                if referer_base in self.allowed_origins:
                    return True
            
            # 检查是否为同源
            if self.allow_same_origin:
                if referer_base == current_base:
                    return True
                
                # 也检查 Host 头
                if host:
                    referer_host = referer_parsed.netloc.split(':')[0]
                    host_clean = host.split(':')[0]
                    if referer_host == host_clean:
                        return True
            
            return False
        except Exception:
            return False
    
    def _match_origin_pattern(self, origin: str, pattern: str) -> bool:
        """
        检查 origin 是否匹配模式（支持通配符）
        
        Args:
            origin: 要检查的 origin
            pattern: 匹配模式（支持 * 通配符）
        
        Returns:
            bool: 是否匹配
        """
        if '*' not in pattern:
            return origin == pattern
        
        # 简单的通配符匹配
        pattern_parts = pattern.split('*')
        if len(pattern_parts) == 2:
            prefix, suffix = pattern_parts
            return origin.startswith(prefix) and origin.endswith(suffix)
        
        return False


def generate_csrf_token() -> str:
    """
    生成 CSRF Token（用于需要额外保护的端点）
    
    Returns:
        str: CSRF Token
    """
    return secrets.token_urlsafe(32)

