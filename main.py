import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from tortoise.contrib.fastapi import register_tortoise
import uvicorn

from apps.router import router
from apps.user import user
from apps.geometry import geometry
from apps.optimize import optimize
from apps.tasks import router as tasks_router
from apps.chat import router as chat_router
from core.middleware import count_time_middleware,FullRequestLoggerMiddleware

from database.settings import TORTOISE_ORM_SQLITE, TORTOISE_ORM_MYSQL
from database.sql import register_sql
from database.redis import redis_connect
from core.geometry import start_mcp, dify_api_port_forward
from api.mcp_server import mcp_cadquery
from config import settings
log_dir = Path("./logs")
log_dir.mkdir(parents=True, exist_ok=True)  # 创建目录（若不存在）

for name in ("app.log", "access.log"):
    (log_dir / name).touch(exist_ok=True)   # 创建空文件（若不存在）
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行的事件

    #启动日志服务
    
    #连接数据库
    app.state.redis = await redis_connect()  # 连接到 Redis 数据库
    #获取动态配置

    #启用第三方的服务
    #mcp_process = await start_mcp()
    #print("执行过了吗")
    dify_api_process = await dify_api_port_forward()

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
    dify_api_process.terminate()
    #其他
    


app = FastAPI()





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



# gengerate the ASGI app for MCP
mcp_app = mcp_cadquery(app)


# Combine both lifespans
@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    # Run both lifespans
    async with lifespan(app):
        async with mcp_app.lifespan(app):
            yield


# Key: Pass lifespan to FastAPI
app = FastAPI(lifespan=combined_lifespan)

# Mount the MCP server
app.mount("/analytics",mcp_app)

# --- 新增：挂载静态文件目录 ---
# 创建 files 目录（如果不存在）
os.makedirs("files", exist_ok=True)
app.mount(settings.STATIC_URL, StaticFiles(directory=settings.STATIC_DIR), name=settings.STATIC_NAME)

# CORS 中间件配置
origins = [
    "http://localhost:5173",  # 允许 Vite 开发服务器的源
    "http://127.0.0.1:5173", # 有时浏览器会使用 127.0.0.1
    "http://localhost/",
    # 在生产环境中，应替换为你的前端域名
    "http://frontend",

    # 添加 Dify 相关的来源
    "http://docker-web-1",        # Dify 前端容器
    "http://docker-api-1",        # Dify API 容器
    "http://docker-nginx-1",      # Dify nginx 容器（如果通过 nginx 转发）
    "http://docker-web-1:3000",   # 若 Dify 前端有端口，需包含端口
    "http://docker-api-1:5001"    # 若 Dify API 有端口，需包含端口
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,#allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# count_time_middleware(app)  # 计时中间件

# app.add_middleware(FullRequestLoggerMiddleware)
register_tortoise(
    app,
    config=TORTOISE_ORM_SQLITE,  # 使用 MySQL 配置
    generate_schemas=True,  # 在应用启动时自动创建数据库表
    add_exception_handlers=True,
)
app.include_router(user, prefix="/api/user", tags=["用户部分", ])
app.include_router(geometry, prefix="/api/geometry", tags=["几何建模", ])
app.include_router(optimize, prefix="/api/optimize", tags=["设计优化", ])
app.include_router(tasks_router, prefix="/api/tasks") # 任务管理路由
app.include_router(router, prefix="/api", tags=["功能", ])
app.include_router(chat_router, prefix="/api/chat", tags=["对话管理"])

# 显式加载日志配置文件
with open('./uvicorn_config.json', 'r', encoding='utf-8') as f:
    log_config = json.load(f)
    
if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", log_config=log_config, port=8080,  log_level="debug",reload=True, reload_excludes=exclude_patterns)
