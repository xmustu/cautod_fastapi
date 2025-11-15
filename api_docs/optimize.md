# apps.optimize 模块 API 文档

路由前缀：`/api/optimize`  （来自 main.py 中 app.include_router(optimize, prefix="/api/optimize")）

说明：设计优化与算法服务交互相关接口与客户端封装。

## GET ""
- 方法：GET
- 路由：/ （Router 根路径下的空路径）
- 描述：优化模块首页
- 鉴权：公开

## POST /
- 方法：POST
- 路由：/
- 描述：设计优化接口（OptimizeRequest），接收模型与参数并返回优化结果（同步返回或流式）
- 鉴权：需要通过自定义 Header Authorization（函数 authenticate 验证）
- 请求模型：OptimizeRequest
- 响应模型：OptimizeResult
- 备注：文件中还有复杂的 optimize_stream_generator（SSE）和 AlgorithmClient 类，用于与外部算法服务进行异步交互、WebSocket 订阅、文件监控等

---

实现提示：AlgorithmClient 必须正确配置 settings.OPTIMIZE_API_URL，并处理 close/异常场景。