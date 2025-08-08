import subprocess
import sys
import os

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
        # 获取当前文件所在目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 构建dify_api.py的绝对路径
        dify_api_path = os.path.join(current_dir, "api", "dify_api.py")

        # 启动端口转发服务
        # 直接使用当前环境的Python解释器
        process = subprocess.Popen(
            [sys.executable, dify_api_path],  
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        print(f"Dify API 端口转发服务已启动，执行文件：{dify_api_path}")
        return process
    except Exception as e:
        print(f"启动 Dify API 端口转发服务失败: {e}")
        return None