# apps.router 模块 API 文档

路由前缀：`/api`  （来自 main.py 中 app.include_router(router, prefix="/api")）

说明：此模块包含文件传输、会话与权限相关的管理接口。

## GET /
- 方法：GET
- 路由：/
- 描述：返回主页模板（Jinja2 模板）
- 鉴权：公开（使用模板渲染）

## POST /model
- 方法：POST
- 路由：/model
- 描述：返回会话下模型文件的二进制（Response），验证 task 归属并检查文件类型为 .stl
- 鉴权：需要登录
- 请求模型：FileRequest
- 响应：Response (application/sla)，文件二进制

## POST /upload_file
- 方法：POST
- 路由：/upload_file
- 描述：上传文件并保存到磁盘
- 鉴权：需要登录
- 请求：multipart/form-data (file: UploadFile, conversation_id: str, task_id: int, path?: Optional[str])
- 响应：{"file_name":..., "content_type":..., "path":...}

## POST /download_file
- 方法：POST
- 路由：/download_file
- 描述：按 conversation_id/task_id 返回文件（FileResponse），验证任务归属
- 鉴权：需要登录
- 请求模型：FileRequest
- 响应：FileResponse (带正确的 MIME type)

## POST /result_status/{task_id}
- 方法：POST
- 路由：/result_status/{task_id}
- 描述：获取任务状态；管理员可查看任意任务，普通用户仅能查看自己的任务
- 鉴权：需要登录
- 响应：Tasks 对象

## POST /conversation/{conversation_id}
- 方法：POST
- 路由：/conversation/{conversation_id}
- 描述：获取单个会话（包含 tasks 预取）；管理员可查看任何会话，普通用户仅能查看自己的
- 鉴权：需要登录
- 响应模型：ConversationOut

## POST /conversation_all/{user_id}
- 方法：POST
- 路由：/conversation_all/{user_id}
- 描述：获取全部会话；管理员可查看指定用户或所有（user_id='all'），普通用户只能查看自己的会话（忽略 path 中 user_id）
- 鉴权：需要登录

## DELETE /conversation/{conversation_id}
- 方法：DELETE
- 路由：/conversation/{conversation_id}
- 描述：删除会话及其相关任务与 Redis 历史；管理员可删除任意会话，普通用户仅能删除自己的会话
- 鉴权：需要登录
- 响应：{"message": "会话及所有关联数据已成功删除"}

---

备注：该模块在删除会话时，若有 Redis 连接，会清理 user_tasks 哈希与 message 列表。