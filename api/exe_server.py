"""
source code from He Sicheng
"""
from fastmcp import FastMCP
import cadquery as cq
from math import sin, cos, pi, floor
import win32com.client as win32
import pythoncom

#-------------------------#

import os 
DIRECTORY = os.getenv("DIRECTORY")
                              
#-------------------------#                              
mcp = FastMCP("cadquery_exe_mcp", "mcp server example", port=8095)

# path = "D:\\work\\3D_models\\cadquery_out"

import os
import subprocess
import sys
from typing import Optional, Tuple

def save_python_string_to_file(
    code_string: str,
    file_name: str,
    directory: str = rf"{DIRECTORY}" #r"C:\Users\dell\Projects\cadquery_test\cadquery_test\mcp\mcp_out"
) -> Optional[str]:
    """
    将 Python 代码字符串保存为 .py 文件
    
    参数:
        code_string: 要保存的 Python 代码字符串
        file_name: 文件名 (无需扩展名，会自动添加 .py)
        directory: 保存目录路径
    
    返回:
        成功时返回文件的完整路径，失败时返回 None
    """
    try:
        # 确保文件名有 .py 扩展名
        if not file_name.endswith('.py'):
            file_name += '.py'
            
        # 创建完整路径
        full_path = os.path.join(directory, file_name)
        
        # 创建目录（如果不存在）
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # 写入文件
        with open(full_path, 'w', encoding='utf-8') as file:
            file.write(code_string)
            
        print(f"文件已成功保存到: {full_path}")
        return full_path
        
    except Exception as e:
        print(f"保存文件时出错: {str(e)}")
        return None

def execute_python_file(file_path: str) -> Tuple[bool, str]:
    """
    执行 Python 文件并捕获输出和错误
    
    参数:
        file_path: 要执行的 Python 文件路径
    
    返回:
        元组 (成功标志, 输出信息)
    """
    try:
        # 使用 subprocess 执行 Python 文件，捕获标准输出和错误
        result = subprocess.run(
            [sys.executable, file_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        # 返回执行结果
        return True, result.stdout.strip()
        
    except subprocess.CalledProcessError as e:
        # 执行失败，返回错误信息
        return False, e.stderr.strip()
    except Exception as e:
        # 其他错误
        return False, f"执行时发生意外错误: {str(e)}"
    
@mcp.tool()
def save_and_execute_python_code(
    code_string: str,
    file_name: str,
    # r"C:\Users\dell\Projects\cadquery_test\cadquery_test\mcp\mcp_out"
    directory: str = rf"{DIRECTORY}" #r"C:\Users\dell\Projects\CAutoD\cautod_fastapi\files\mcp_out"
) -> Tuple[bool, str, Optional[str]]:
    """
    保存 Python 代码并执行
    
    参数:
        code_string: 要保存的 Python 代码字符串
        file_name: 文件名
        directory: 保存目录路径
    
    返回:
        元组 (成功标志, 消息, 文件路径)
    """
    # 保存文件
    file_path = save_python_string_to_file(code_string, file_name, directory)

    text = "Hello, 世界！"
    file_path_example = os.path.join(os.getcwd(), "1.txt")
    with open(file_path_example, "w", encoding="utf-8") as f:
        f.write(text)
    if not file_path:
        return [False, "保存文件失败", None]
    
    # 执行文件
    success, output = execute_python_file(file_path)
    
    if success:
        return [True, f"执行成功\n输出:\n{output}", file_path]
    else:
        return [False, f"执行失败\n错误:\n{output}", file_path]

if __name__ == '__main__':
    mcp.run(transport="sse")