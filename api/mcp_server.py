from fastmcp import FastMCP
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from fastapi import Request
from fastapi import FastAPI
import time 
from fastmcp.server.middleware import Middleware, MiddlewareContext

from database.models_1 import OptimizationResults, Tasks, GeometryResults


async def obtain_work_dir(dify_conversation_id: str) -> Path:
    """获取与会话ID对应的任务的工作目录"""

    # 提取会话ID和任务ID
    try:
        task = await Tasks.get_or_none(dify_conversation_id=dify_conversation_id)
        task_id, conversation_id = task.task_id, task.conversation_id
        parent_dir = Path(os.getcwd())
        # 构建目标目录路径：上一级目录/files/会话ID
        task_dir = parent_dir / "files" / str(conversation_id) / str(task_id)
        print("任务目录: ", task_dir)
        relative_task_dir = task_dir.relative_to(Path(os.getcwd()))
        print("相对任务目录: ", relative_task_dir)
        return relative_task_dir
    except Exception as e:
        raise RuntimeError(f"无法获取Dify会话ID对应的任务信息: {str(e)}")

async def save_geometry_result(dify_conversation_id: str, work_dir: Path):
    """将最新的几何建模结果保存到数据库"""
    try: 
        task = await Tasks.get_or_none(dify_conversation_id=dify_conversation_id)

        geometry_result = await GeometryResults.get_or_none(task_id=task.task_id)
        print("找到建模结果吗？", geometry_result)
        update_data = {
            "cad_file_path": work_dir / "model.step",
            "code_file_path": work_dir / "script.py",
            "preview_image_path": work_dir / "Oblique_View.png"
        }
        if geometry_result:
            # 如果存在则更新
            await geometry_result.update_from_dict(update_data).save()
        else:

            geometry_result = await GeometryResults.create(
                task_id=task.task_id,
                **update_data
            )
            await geometry_result.save()
        
        print("优化结果: ", geometry_result)
       

    except Exception as e:
        raise RuntimeError(f"保存几何建模结果时出错: {str(e)}")
    

# ----------中间件--------------
class LoggingMiddleware(Middleware):
    """Middleware that logs all MCP operations."""
    
    async def on_message(self, context: MiddlewareContext, call_next):
        """Called for all MCP messages."""
        print(f"Processing {context.method} from {context.source}")
        
        result = await call_next(context)
        
        print(f"Completed {context.method}")
        return result

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


# # 依赖检查
# try:
#     import cadquery as cq
# except ImportError:
#     sys.exit("缺少 cadquery：pip install cadquery")



# # 统一输出根目录
# BASE_OUT = "C:\\\\Users\\\\dell\\\\Projects\\\\cadquery_test\\\\cadquery_test\\\\mcp_server\\\\mcp_output"


def mcp_cadquery(app: FastAPI):
    mcp = FastMCP.from_fastapi(app=app, name="cadquery_exe_mcp")
    mcp.add_middleware(RequestLoggerMiddleware())


        
    @mcp.tool
    async def run_cadquery(cadquery_code: str, conversation_id: str) -> dict:
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
        # 新增！根据dify conversation id to fin work directory 2025-8-25
        print("收到会话ID: ", conversation_id)
        work_dir = await obtain_work_dir(conversation_id)
        print("对应任务工作目录: ", work_dir)
        # 依赖检查
        try:
            import cadquery as cq
        except ImportError:
            sys.exit("缺少 cadquery：pip install cadquery")

        try:
            os.makedirs(work_dir,exist_ok=True)
            print(f"文件夹 '{work_dir}' 创建成功或已存在")
        except OSError as e:
            print(f"创建文件夹失败: {e}")
        script_py = work_dir / "script.py"
        model_step = work_dir / "model.step"
        error_txt = work_dir / "error.txt"
        image_png = work_dir / "Oblique_View.png"

        # 确保代码最终导出 STEP
        code = cadquery_code
        if "result.export" not in code:
            code += f"\nresult.export(r'{model_step}')"
            code += "\nfrom cadquery.vis import show"
            # code += "\nimport pyvista as pv  # cadquery的可视化依赖"
            # code += "\nfrom cadquery import exporters"
#             code += f'''
# exporters.export(
#     result,
#     r'{image_png}',  # 路径变量嵌入
#     exportType="png",
#     # 设置渲染参数（类似原 show 函数的视角）
#     opt={{
#         "width": 800,
#         "height": 600,
#         "roll": 10,
#         "elevation": -65,
#         "renderer": "matplotlib"  # 使用 matplotlib 后端（无需窗口）
#     }}
# )'''
            # code += "\npv.OFF_SCREEN = True  # 启用离线渲染模式"
            code += f"\nshow(result, title='斜视图', roll=10, elevation=-65, screenshot=r'{image_png}', interact=False)"
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

            # 新增！保存结果到数据库 2025-8-25
            await save_geometry_result(conversation_id, work_dir=work_dir)
            return {"success": True, "step_file": model_step}
        except Exception as e:
            with open(error_txt, 'w', encoding='utf-8') as f:
                f.write(f"{e}\n\n{traceback.format_exc()}")
            return {"success": False, "error": str(e), "error_file": error_txt}
        

        # Create ASGI app from MCP server
    mcp_app = mcp.http_app(transport="sse")  # 致命改动，吐血调半天，传递参数transport="sse",endpoint则附加/sse
    return mcp_app
