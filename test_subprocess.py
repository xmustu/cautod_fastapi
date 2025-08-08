import subprocess
import sys
import os
with subprocess.Popen(
    [r"C:\Users\dell\anaconda3\envs\cad\python.exe", r"c:\Users\dell\Projects\cadquery_test\cadquery_test\mcp\exe_server.py"],  # 示例命令
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True  # 转为字符串
) as proc:
    # 读取标准输出（字符串形式）
    stdout = proc.stdout.read()
    # 读取标准错误（字符串形式）
    stderr = proc.stderr.read()
    
    print("标准输出:", stdout)
    print("标准错误:", stderr)