from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os

from apps.router import router
from apps.app01 import user
from apps.app02 import geometry
from apps.app03 import optimize
from apps.tasks import router as tasks_router
from apps.chat import router as chat_router
from core.middleware import count_time_middleware,FullRequestLoggerMiddleware
from tortoise.contrib.fastapi import register_tortoise
from settings import TORTOISE_ORM_sqlite, TORTOISE_ORM_mysql
from contextlib import asynccontextmanager
from database.redis import redis_connect
from core.geometry import start_mcp, dify_api_port_forward

from starlette.routing import Mount
from fastmcp import FastMCP
from fastapi_mcp import FastApiMCP
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from fastapi import Request
import time 
from fastmcp.server.middleware import Middleware, MiddlewareContext


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
    # 终止时执行的事件

    #关闭日志服务

    #关闭数据库连接
    await app.state.redis.close()  # 关闭 Redis 连接
    #退出第三方服务
    #print("stdout: ", mcp_process.stdout)
    #print("stderr: ", mcp_process.stderr)
    #mcp_process.terminate()
    dify_api_process.terminate()
    #其他
    


app = FastAPI()



#count_time_middleware(app)  # 计时中间件



# CORS 中间件配置
origins = [
    "http://localhost:5173",  # 允许 Vite 开发服务器的源
    "http://127.0.0.1:5173", # 有时浏览器会使用 127.0.0.1
    "http://localhost/",
    # 在生产环境中，应替换为你的前端域名
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],#allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(FullRequestLoggerMiddleware)
register_tortoise(
    app,
    config=TORTOISE_ORM_sqlite,  # 使用 MySQL 配置
    generate_schemas=True,  # 在应用启动时自动创建数据库表
    add_exception_handlers=True,
)

exclude_dirs = [
    "files\\mcp_out",
]


app.include_router(user, prefix="/api/user", tags=["用户部分", ])
app.include_router(geometry, prefix="/api/geometry", tags=["几何建模", ])
app.include_router(optimize, prefix="/api/optimize", tags=["设计优化", ])
app.include_router(tasks_router, prefix="/api/tasks") # 任务管理路由
app.include_router(router, prefix="/api", tags=["功能", ])
app.include_router(chat_router, prefix="/api/chat", tags=["对话管理"])


# --- 新增：挂载静态文件目录 ---
# 创建 files 目录（如果不存在）
os.makedirs("files", exist_ok=True)
app.mount("/files", StaticFiles(directory="files"), name="files")





# class LoggingMiddleware(Middleware):
#     """Middleware that logs all MCP operations."""
    
#     async def on_message(self, context: MiddlewareContext, call_next):
#         """Called for all MCP messages."""
#         print(f"Processing {context.method} from {context.source}")
        
#         result = await call_next(context)
        
#         print(f"Completed {context.method}")
#         return result
    
class RequestLoggerMiddleware(Middleware):
    """记录所有 MCP 请求的中间件"""
    
    async def on_message(self, context: MiddlewareContext, call_next):
        print(f"[START] {context.method} from {context.source}")
        print(f"Request : {context}")

        start_time = time.perf_counter()
        
        try:
            result = await call_next(context)
            duration = (time.perf_counter() - start_time) * 1000
            print(f"[END] {context.method} completed in {duration:.2f}ms")
            return result
        except Exception as e:
            duration = (time.perf_counter() - start_time) * 1000
            print(f"[ERROR] {context.method} failed in {duration:.2f}ms: {str(e)}")
            raise


# Create MCP server
mcp = FastMCP.from_fastapi(app=app, name="cadquery_exe_mcp")
mcp.add_middleware(RequestLoggerMiddleware())
# # Create an MCP server based on this app
# mcp = FastApiMCP(app)
# # Mount the MCP server directly to your app
# mcp.mount_http()


# 统一输出根目录
BASE_OUT = "C:\\\\Users\\\\dell\\\\Projects\\\\cadquery_test\\\\cadquery_test\\\\mcp_server\\\\mcp_output"

@mcp.tool
def run_cadquery(cadquery_code: str, conversation_id: str) -> dict:
    """
    功能：执行CADQuery代码并生成3D模型相关文件
    
    该工具会完成一系列自动化操作：
    1. 创建唯一的临时工作目录
    2. 将输入的CADQuery代码写入脚本文件
    3. 自动补充模型导出代码（如未包含）
    4. 执行CADQuery代码生成3D模型
    5. 导出STEP格式模型文件和多角度视图图片
    6. 捕获并处理执行过程中的错误
    7. 返回包含执行结果的字典
    
    输入：
        cadquery_code (str): 符合CADQuery语法的Python代码字符串，应包含3D模型定义
                            并将最终模型赋值给'result'变量
    
    输出：
        dict: 包含执行结果的字典，有两种可能结构：
            - 成功时: {"success": True, "step_file": 生成的STEP文件路径}
            - 失败时: {"success": False, "error": 错误描述字符串, "error_file": 错误详情文件路径}
    """
    
    print("收到会话ID: ", conversation_id)
    # 依赖检查
    try:
        import cadquery as cq
    except ImportError:
        sys.exit("缺少 cadquery：pip install cadquery")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ws = BASE_OUT + f"\\\\{ts}"
    try:
        os.makedirs(ws,exist_ok=True)
        print(f"文件夹 '{ws}' 创建成功或已存在")
    except OSError as e:
        print(f"创建文件夹失败: {e}")
    script_py = ws + "\\\\script.py"
    model_step = ws + "\\\\model.step"
    error_txt = ws + "\\\\error.txt"
    image_png = ws + "\\\\Oblique_View.png"

    # 确保代码最终导出 STEP
    code = cadquery_code
    if "result.export" not in code:
        code += f"\nresult.export('{model_step}')"
        code += "\nfrom cadquery.vis import show"
        code += f"\nshow(result, title='斜视图', roll=10, elevation=-65, screenshot='{image_png}', interact=False)"
        # code += f"\nshow(result, title='主视图', roll=0, elevation=90, screenshot='{ws}\\\\front_view.png', interact=False)"
        # code += f"\nshow(result, title='侧视图', roll=90, elevation=90, screenshot='{ws}\\\\side_view.png', interact=False)"
        # code += f"\nshow(result, title='俯视图', roll=0, elevation=0, screenshot='{ws}\\\\top_view.png', interact=False)"

    # 保存脚本
    # script_py.write_text(code, encoding="utf-8")

    try:
       # 将字符串写入Python文件
        with open(script_py, 'w', encoding='utf-8') as f:
           f.write(code)
        print(f"已将代码保存到 {script_py}")
    except Exception as e:
        print(f"保存代码时出错: {e}")
    # 执行
    try:
        exec_globals = {"cq": cq, "result": None, "__file__": str(script_py)}
        exec(code, exec_globals)

        if not os.path.exists(model_step):
            raise RuntimeError("STEP 文件未生成")
        print(f"模型已导出到 {model_step}\n预览图已导出到{image_png}\n")
        return {"success": True, "step_file": model_step}

    except Exception as e:
        with open(error_txt, 'w', encoding='utf-8') as f:
            f.write(f"{e}\n\n{traceback.format_exc()}")
        return {"success": False, "error": str(e), "error_file": error_txt}


# Create ASGI app from MCP server
mcp_app = mcp.http_app(transport="sse")  # 致命改动，吐血调半天，传递参数transport="sse",endpoint则附加/sse

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



# CORS 中间件配置
origins = [
    "http://localhost:5173",  # 允许 Vite 开发服务器的源
    "http://127.0.0.1:5173", # 有时浏览器会使用 127.0.0.1
    "http://localhost/",
    # 在生产环境中，应替换为你的前端域名
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],#allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# app.add_middleware(FullRequestLoggerMiddleware)
register_tortoise(
    app,
    config=TORTOISE_ORM_sqlite,  # 使用 MySQL 配置
    generate_schemas=True,  # 在应用启动时自动创建数据库表
    add_exception_handlers=True,
)
app.include_router(user, prefix="/api/user", tags=["用户部分", ])
app.include_router(geometry, prefix="/api/geometry", tags=["几何建模", ])
app.include_router(optimize, prefix="/api/optimize", tags=["设计优化", ])
app.include_router(tasks_router, prefix="/api/tasks") # 任务管理路由
app.include_router(router, prefix="/api", tags=["功能", ])
app.include_router(chat_router, prefix="/api/chat", tags=["对话管理"])
if __name__ == '__main__':
    uvicorn.run("main:app", host="127.0.0.1", port=8080,  reload=True, reload_excludes=exclude_dirs)
