# 历史记录端点测试说明

## 概述

本目录包含用于测试 `/history` 端点的测试脚本。该端点在 `apps/routes/chat.py` 中定义，用于获取用户对话历史记录。

## 测试文件

### 1. `test_chat_history.py` - 单元测试

使用 pytest 编写的完整单元测试套件，包含以下测试场景：

- ✅ 成功获取历史记录（包含多种消息格式）
- ✅ 空历史记录
- ✅ Redis 不可用的情况
- ✅ 格式错误的 JSON 数据
- ✅ 缺少时间戳字段
- ✅ Redis 操作异常
- ✅ 各种 SSE 格式变体
- ✅ JSON 格式但不包含 answer 字段
- ✅ 时间戳转换和格式化
- ✅ 默认任务类型

**运行方式：**
```bash
# 在项目根目录运行
cd cautod_fastapi
pytest test/test_chat_history.py -v

# 运行特定测试
pytest test/test_chat_history.py::test_get_history_success -v

# 显示详细输出
pytest test/test_chat_history.py -v -s
```

### 2. `test_history_endpoint_standalone.py` - 独立诊断脚本

可在生产环境中直接运行的诊断脚本，用于：

- 🔍 诊断实际生产环境中的问题
- 📊 分析 Redis 中的数据格式
- 🐛 定位具体的错误原因
- ✅ 验证修复是否有效

**运行方式：**
```bash
# 在项目根目录运行
cd cautod_fastapi
python test/test_history_endpoint_standalone.py

# 指定用户 ID
python test/test_history_endpoint_standalone.py --user-id 2

# 或使用 Python 模块方式
python -m test.test_history_endpoint_standalone --user-id 1
```

## 常见问题诊断

### 问题 1: JSON 解析错误

**症状：** `json.JSONDecodeError` 或 `KeyError`

**可能原因：**
- Redis 中存储的数据格式不正确
- `last_message` 字段包含无效的 JSON
- 缺少必需的字段（如 `last_timestamp`）

**诊断步骤：**
1. 运行独立诊断脚本查看原始数据
2. 检查 Redis 中 `user_tasks:{user_id}` 的数据格式
3. 验证每个任务的 JSON 是否有效

### 问题 2: 时间戳转换错误

**症状：** `ValueError` 或 `OSError` 在 `datetime.fromtimestamp()` 时

**可能原因：**
- `last_timestamp` 字段缺失
- `last_timestamp` 不是有效的数字
- 时间戳超出范围

**诊断步骤：**
1. 检查任务数据中是否包含 `last_timestamp` 字段
2. 验证时间戳是否为数字类型
3. 检查时间戳是否在合理范围内

### 问题 3: Redis 连接失败

**症状：** `Redis connection error` 或 `REDIS_AVAILABLE=False`

**可能原因：**
- Redis 服务未启动
- 配置错误（主机、端口、密码）
- 网络问题

**诊断步骤：**
1. 检查 `settings.REDIS_AVAILABLE` 是否为 `True`
2. 验证 Redis 服务是否运行
3. 测试 Redis 连接：`redis-cli -h {host} -p {port} ping`

### 问题 4: SSE 格式解析失败

**症状：** `IndexError` 在 `split('data: ')` 时

**可能原因：**
- `last_message` 不是标准的 SSE 格式
- 格式变体未处理（如多行、多余空格）

**诊断步骤：**
1. 查看 `last_message` 的实际内容
2. 检查是否符合 `event: message_end\ndata: {...}` 格式
3. 验证 JSON 部分是否有效

## 测试覆盖的场景

### 消息格式类型

1. **普通文本消息**
   ```json
   {
     "last_message": "这是一条普通文本消息"
   }
   ```

2. **JSON 格式消息（包含 answer）**
   ```json
   {
     "last_message": "{\"answer\": \"这是JSON格式的答案\"}"
   }
   ```

3. **SSE 格式消息**
   ```
   event: message_end
   data: {"answer": "这是SSE格式的答案"}
   ```

4. **无效格式**
   - 无效的 JSON: `"无效的JSON格式{"`
   - 空消息: `""`
   - 缺少字段的数据

## 修复建议

如果发现问题，可以：

1. **添加数据验证**
   - 在保存数据到 Redis 时验证格式
   - 添加数据迁移脚本修复现有数据

2. **增强错误处理**
   - 添加更详细的错误日志
   - 对无效数据使用默认值而不是抛出异常

3. **改进格式解析**
   - 支持更多 SSE 格式变体
   - 添加格式检测和自动修复

## 示例输出

### 独立诊断脚本输出示例

```
============================================================
🧪 历史记录端点诊断测试
============================================================
🔌 正在连接 Redis...
   Host: localhost
   Port: 6379
   DB: 0
   REDIS_AVAILABLE: True
✅ Redis 连接成功

📋 测试获取用户 1 的任务数据...
   Redis Key: user_tasks:1
   ✅ 成功获取数据，任务数量: 3

   📦 任务 ID: task_1
      ✅ JSON 解析成功
      - conversation_id: conv_1
      - task_type: 设计优化
      - last_timestamp: 1234567890.0
      - last_message 类型: <class 'str'>
      - last_message 长度: 25
      - last_message 预览: 这是一条普通文本消息...
      ℹ️  普通文本格式（非 JSON）

🔍 测试历史记录端点逻辑 (用户 ID: 1)...
   获取到 3 个任务
   ✅ 处理完成，共 3 条历史记录

============================================================
📊 测试结果摘要
============================================================
用户 ID: 1
历史记录总数: 3

历史记录列表:

  1. 任务 ID: task_3
     类型: 对话测试
     时间: 2024-01-01 12:00:00
     消息预览: 这是SSE格式的答案...

  2. 任务 ID: task_2
     类型: 几何生成
     时间: 2024-01-01 11:00:00
     消息预览: 这是JSON格式的答案...

  3. 任务 ID: task_1
     类型: 设计优化
     时间: 2024-01-01 10:00:00
     消息预览: 这是一条普通文本消息...

============================================================
✅ 测试完成
============================================================
```

## 注意事项

1. **生产环境测试**
   - 独立诊断脚本会连接到实际的 Redis
   - 确保不会影响生产数据
   - 建议在测试环境先运行

2. **依赖项**
   - 需要安装 pytest: `pip install pytest pytest-asyncio`
   - 需要 Redis 客户端: `pip install redis`

3. **环境变量**
   - 确保 `.env.prod` 或相应的环境配置文件正确设置
   - 特别是 Redis 相关配置

## 贡献

如果发现新的问题场景或需要添加新的测试用例，请：

1. 在 `test_chat_history.py` 中添加相应的测试
2. 更新本文档
3. 确保所有测试通过

