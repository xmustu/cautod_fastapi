from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from apps.router import router
from apps.app01 import user
from apps.app02 import geometry
from apps.app03 import optimize
from apps.tasks import router as tasks_router

from core.middleware import count_time_middleware, request_response_middleware
from tortoise.contrib.fastapi import register_tortoise
from settings import TORTOISE_ORM_sqlite
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Start.")
    yield  
    print("End.")
    
app = FastAPI(lifespan=lifespan)

count_time_middleware(app)  # 计时中间件

# CORS 中间件配置
origins = [
    "http://localhost:5173",  # 允许 Vite 开发服务器的源
    "http://127.0.0.1:5173", # 有时浏览器会使用 127.0.0.1
    # 在生产环境中，应替换为你的前端域名
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_tortoise(
    app,
    config=TORTOISE_ORM_sqlite,
    generate_schemas=True,  # 在应用启动时自动创建数据库表
    add_exception_handlers=True,
)


app.include_router(user, prefix="/api/user", tags=["用户部分", ])
app.include_router(geometry, prefix="/api/geometry", tags=["几何建模", ])
app.include_router(optimize, prefix="/api/optimize", tags=["设计优化", ])
app.include_router(tasks_router, prefix="/api/tasks") # 任务管理路由
app.include_router(router, prefix="/api", tags=["功能", ])

if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8080,  reload=True)
