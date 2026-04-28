
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from tortoise.contrib.fastapi import register_tortoise
import uvicorn

from apps.routes.router import router
from apps.routes.user import user
from apps.geometry import geometry
from apps.optimize import optimize
from apps.routes.tasks import router as tasks_router
from apps.routes.chat import router as chat_router
from apps.routes.login import router as login_router
from apps.routes.admin import admin_router
from apps.routes.remote import app as remote_touter
from core.middleware import (
    count_time_middleware,
    FullRequestLoggerMiddleware,
    RateLimitMiddleware,
)
from core.security_headers import SecurityHeadersMiddleware
from core.csrf_protection import CSRFProtectionMiddleware

from database.settings import TORTOISE_ORM_SQLITE, TORTOISE_ORM_MYSQL
from database.sql import register_sql
from database.redis import redis_connect
from database.models import Users, UserRole
from core.geometry import start_mcp, dify_api_port_forward
from core.hashing import Hasher
from core.authentication import create_token


from config import settings
from configs.celery_utils import create_celery

log_dir = Path("./logs")
log_dir.mkdir(parents=True, exist_ok=True)  # 创建目录（若不存在）

for name in ("app.log", "access.log"):
    (log_dir / name).touch(exist_ok=True)   # 创建空文件（若不存在）


async def init_admin_account():
    """
    初始化管理员账号
    如果系统中不存在管理员账号，则创建默认管理员
    """
    try:
        # 检查是否存在管理员账号
        admin_exists = await Users.filter(role=UserRole.ADMIN).exists()
        
        if not admin_exists:
            # 创建默认管理员账号
            admin_email = "Z.F.Zhang@i4ai.org"
            admin_username = "admin"
            admin_password = "i4AIi4AI"
            
            # 检查邮箱是否已被使用（可能是其他角色）
            existing_user = await Users.get_or_none(email=admin_email)
            
            if existing_user:
                # 如果用户存在但不是管理员，升级为管理员
                existing_user.role = UserRole.ADMIN
                existing_user.username = admin_username
                await existing_user.save()
                print(f"✓ 已将用户 {admin_email} 升级为管理员")
            else:
                # 创建新的管理员账号
                hashed_password = Hasher.get_password_hash(admin_password)
                await Users.create(
                    username=admin_username,
                    email=admin_email,
                    password_hash=hashed_password,
                    role=UserRole.ADMIN
                )
                print(f"✓ 默认管理员账号已创建")
                print(f"  邮箱: {admin_email}")
                print(f"  用户名: {admin_username}")
                print(f"  密码: {admin_password}")
                print(f"  提示: 请在首次登录后修改密码！")
        else:
            print("✓ 管理员账号已存在")
            
    except Exception as e:
        print(f"✗ 初始化管理员账号失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行的事件

    #启动日志服务
    
    #连接数据库
    app.state.redis = await redis_connect()  # 连接到 Redis 数据库
    print("redis")

    # 初始化管理员账号
    await init_admin_account()
    
    # 速率限制中间件已在应用创建后注册，会自动从 app.state.redis 获取连接
    if app.state.redis:
        print("✓ API速率限制中间件已启用（使用Redis）")
    else:
        print("⚠ Redis未连接，速率限制将使用内存模式（不推荐用于生产环境）")

    #获取动态配置

    #启用第三方的服务
    #mcp_process = await start_mcp()
    #print("执行过了吗")
    # dify_api_process = await dify_api_port_forward()

    #其他
    yield
    # async with register_sql(app):
    #     yield print("lifespan 启动数据库")
    # 终止时执行的事件

    #关闭日志服务

    #关闭数据库连接
    await app.state.redis.aclose()  # 关闭 Redis 连接
    #退出第三方服务
    #print("stdout: ", mcp_process.stdout)
    #print("stderr: ", mcp_process.stderr)
    #mcp_process.terminate()
    # dify_api_process.terminate()
    #其他
    


# app = FastAPI()





# 关键修复：使用相对路径 + 递归通配符，适配Windows系统
# 1. 相对路径模式（相对于当前工作目录）
# 2. ** 匹配所有子目录，* 匹配所有文件
exclude_patterns = [
    "files/*",          # 排除files根目录下的所有文件
    "files/**/*",       # 排除files所有子目录及文件（递归）
    "files\\*",         # Windows路径分隔符兼容（可选，确保覆盖）
    "files\\**\\*",    # Windows递归匹配（可选）
    "shared/*",          # 排除files根目录下的所有文件
    "shared/**/*",       # 排除files所有子目录及文件（递归）
    "shared\\*",         # Windows路径分隔符兼容（可选，确保覆盖）
    "shared\\**\\*"
]



# # gengerate the ASGI app for MCP
# mcp_app = mcp_cadquery(app)


# # Combine both lifespans
# @asynccontextmanager
# async def combined_lifespan(app: FastAPI):
#     # Run both lifespans
#     async with lifespan(app):
#         async with mcp_app.lifespan(app):
#             yield


# Key: Pass lifespan to FastAPI
app = FastAPI(
    lifespan=lifespan,
    title="CAutoD API",
    description="CAutoD 计算机辅助自动设计系统 API",
    version="1.0.0",
    swagger_ui_init_oauth={
        "clientId": "swagger-ui",
        "appName": "CAutoD API",
        "usePkceWithAuthorizationCodeGrant": True,
    }
)

# OAuth2 密码流配置 - 用于 Swagger UI 授权
@app.post("/login", tags=["认证"], summary="Swagger UI OAuth2 登录")
async def login_for_swagger(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 密码流登录端点
    用于 Swagger UI 的授权
    
    - **username**: 用户邮箱
    - **password**: 用户密码
    """
    # 查找用户（支持邮箱或用户名登录）
    user = await Users.get_or_none(email=form_data.username)
    if not user:
        user = await Users.get_or_none(username=form_data.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 验证密码
    if not Hasher.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 生成访问令牌
    access_token = create_token(data={"sub": user.email})
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

# Mount the MCP server
# app.mount("/analytics",mcp_app)

# --- 新增：挂载静态文件目录 ---
# 创建 files 目录（如果不存在）
os.makedirs("files", exist_ok=True)
app.mount(settings.STATIC_URL, StaticFiles(directory=settings.STATIC_DIR), name=settings.STATIC_NAME)

# CORS 中间件配置
origins = [
    # localhost (HTTP)
    "http://localhost",
    "http://localhost:80",
    "http://localhost:443",
    # localhost (HTTPS)
    "https://localhost",
    "https://localhost:443",
    "https://localhost:80",
    # 127.0.0.1 (HTTP)
    "http://127.0.0.1",
    "http://127.0.0.1:80",
    "http://127.0.0.1:443",
    # 127.0.0.1 (HTTPS)
    "https://127.0.0.1",
    "https://127.0.0.1:443",
    "https://127.0.0.1:80",
    # host.docker.internal (用于 Docker 容器访问宿主机)
    "http://host.docker.internal",
    "http://host.docker.internal:80",
    "http://host.docker.internal:443",
    "https://host.docker.internal",
    "https://host.docker.internal:443",
    "https://host.docker.internal:80",
    # 常见的开发端口 (localhost)
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:8080",
    "http://localhost:8081",
    "http://localhost:8000",
    "http://localhost:81",
    # 常见的开发端口 (127.0.0.1)
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8081",
    "http://127.0.0.1:8082",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:81",
    # 常见的开发端口 (host.docker.internal)
    "http://host.docker.internal:3000",
    "http://host.docker.internal:5173",
    "http://host.docker.internal:5174",
    "http://host.docker.internal:8080",
    "http://host.docker.internal:8081",
    "http://host.docker.internal:8000",
    "http://host.docker.internal:81",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加 CSRF 防护中间件（在 CORS 之后，验证请求来源）
# 注意：由于使用 JWT Token 认证，主要依赖 Origin/Referer 验证
app.add_middleware(
    CSRFProtectionMiddleware,
    allowed_origins=set(origins),  # 使用 CORS 允许的来源列表
    verify_origin=True,
    verify_referer=True,
    allow_same_origin=True
)

# 添加速率限制中间件（在 CORS 之后注册，这样速率限制会在请求处理前先检查）
# 中间件会在运行时从 app.state.redis 获取连接
app.add_middleware(RateLimitMiddleware)

# 添加安全响应头中间件（最后注册，确保所有响应都包含安全头）
# enable_hsts: 仅在 HTTPS 环境启用（生产环境设置为 True）
# app.add_middleware(
#     SecurityHeadersMiddleware,
#     enable_hsts=False,  # 开发环境设为 False，生产环境 HTTPS 时设为 True
#     csp_policy=None  # 使用默认 CSP 策略，可根据需要自定义
# )

# count_time_middleware(app)  # 计时中间件

# app.add_middleware(FullRequestLoggerMiddleware)
print(settings.SQLMODE)
if settings.SQLMODE == "MYSQL":
    config = TORTOISE_ORM_MYSQL
else:
    config = TORTOISE_ORM_SQLITE
register_tortoise(
    app,
    config=config,  # 使用 MySQL 配置
    generate_schemas=True,  # 在应用启动时自动创建数据库表
    add_exception_handlers=True,
)
print("daozhe ")



app.include_router(user, prefix="/api/user", tags=["用户部分", ])
app.include_router(login_router, prefix="/api/auth", tags=["登录认证"])
app.include_router(geometry, prefix="/api/geometry", tags=["几何建模", ])
app.include_router(optimize, prefix="/api/optimize", tags=["设计优化", ])
app.include_router(tasks_router, prefix="/api/tasks") # 任务管理路由
app.include_router(router, prefix="/api", tags=["功能", ])
app.include_router(chat_router, prefix="/api/chat", tags=["对话管理"])
app.include_router(admin_router, prefix="/api") # 管理员路由
app.include_router(remote_touter, prefix="/api/remote", tags=["远程控制"])
print("到这")
# 显式加载日志配置文件True
with open('./uvicorn_config.json', 'r', encoding='utf-8') as f:
    log_config = json.load(f)
    

celery = create_celery()
if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8082,  log_level="debug",reload=False, reload_excludes=exclude_patterns, workers=1)
