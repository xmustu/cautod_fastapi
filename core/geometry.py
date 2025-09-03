import subprocess
import sys
import os
from config import settings
from api.dify_api import start_forwarder
async def start_mcp():
    """启动 MCP 服务"""
    try:
        # 获取当前文件所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 构建exe_server.py的绝对路径
        exe_server_path = os.path.join(current_dir, "api", "exe_server.py")
        print("exe_server_path: ", exe_server_path)
        #cad环境的python解释器路径
        cad_env_python = r"C:\Users\dell\anaconda3\envs\cad\python.exe"
        print("cad_env_python: ", cad_env_python)
        env = os.environ.copy()  # 复制当前环境变量
        env["DIRECTORY"] = r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\mcp_out"
        print("环境变量： ", env)
        process = subprocess.Popen(
            [cad_env_python, exe_server_path],  # exe_server.py 是 MCP 服务的入口文件
            env=env,  # 新增环境变量
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"mcp服务（cad环境）已启动，执行文件：{exe_server_path}")
        return process
    except Exception as e:
        print(f"启动 MCP 服务失败: {e}")
        return None
    
async def dify_api_port_forward():
    """启动 Dify API 端口转发"""
    try:
        # 配置（目标端口未显式设置，使用默认80）
        LISTEN_HOST = settings.DIFY_LISTEN_HOST
        LISTEN_PORT = settings.DIFY_LISTEN_PORT  # 局域网访问端口
        TARGET_HOST = settings.DIFY_TARGET_HOST      # 本地服务地址
        TARGET_PORT = settings.DIFY_TARGET_PORT     # 被注释，使用函数默认值
        await start_forwarder(LISTEN_HOST, LISTEN_PORT, TARGET_HOST, TARGET_PORT)
    except Exception as e:
        print(f"启动 Dify API 端口转发服务失败: {e}")
        return None