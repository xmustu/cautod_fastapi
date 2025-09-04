from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import FastMCP  # 导入FastMCP库



# 3. 初始化FastMCP实例（注意：不要指定port，由FastAPI统一暴露端口）
mcp = FastMCP(
    name="cadquery_exe_mcp",
    # 不设置port参数，避免FastMCP单独占用端口
)



# 5. 启动FastAPI（统一使用8080端口）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(mcp.http_app(), host="0.0.0.0", port=8001, log_level="info")
