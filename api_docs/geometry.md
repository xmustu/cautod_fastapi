# apps.geometry 模块 API 文档

路由前缀：`/api/geometry`  （来自 main.py 中 app.include_router(geometry, prefix="/api/geometry")）

说明：几何建模相关接口与流式生成器（与 Dify 集成）。

## GET /
- 方法：GET
- 路由：/
- 描述：Geometry 模块首页
- 鉴权：公开

## POST /conversation
- 方法：POST
- 路由：/conversation
- 描述：创建新会话（ConversationCreateRequest），分配 conversation_id 并在磁盘上创建对应目录
- 鉴权：需要登录
- 请求模型：ConversationCreateRequest
- 响应模型：ConversationResponse
- 备注：该模块实现了 geometry_stream_generator 用于流式返回建模结果（SSE），但该生成器不会单独暴露一个路由；tasks.execute 会调用 geometry_stream_generator

---

实现细节：Dify 客户端封装在 DifyClient 类中，提供 chat_stream 与 Next_Suggested_Questions。