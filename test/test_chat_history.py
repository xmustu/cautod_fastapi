"""
测试 /history 端点
测试获取用户对话历史记录的功能，包括各种边界情况和错误处理
"""
import pytest
import json
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import Request
from fastapi.testclient import TestClient
from httpx import AsyncClient

from core.authentication import User


class MockRedis:
    """模拟 Redis 客户端"""
    def __init__(self, data=None):
        self.data = data or {}
        self.hgetall_called = False
        
    async def hgetall(self, key):
        """模拟 hgetall 操作"""
        self.hgetall_called = True
        self.last_key = key
        return self.data.get(key, {})
    
    async def ping(self):
        return True
    
    async def aclose(self):
        return True


@pytest.fixture
def mock_user():
    """创建模拟用户"""
    return User(user_id=1, email="test@example.com", created_at=datetime.utcnow())


@pytest.fixture
def mock_redis_empty():
    """创建空的 Redis mock"""
    return MockRedis()


@pytest.fixture
def mock_redis_with_data():
    """创建包含测试数据的 Redis mock"""
    import time
    current_time = time.time()
    
    # 测试数据：包含不同格式的 last_message
    task_data = {
        "task_1": json.dumps({
            "task_id": "task_1",
            "conversation_id": "conv_1",
            "task_type": "设计优化",
            "last_message": "这是一条普通文本消息",
            "last_timestamp": current_time - 100
        }),
        "task_2": json.dumps({
            "task_id": "task_2",
            "conversation_id": "conv_2",
            "task_type": "几何生成",
            "last_message": json.dumps({"answer": "这是JSON格式的答案"}),
            "last_timestamp": current_time - 50
        }),
        "task_3": json.dumps({
            "task_id": "task_3",
            "conversation_id": "conv_3",
            "task_type": "对话测试",
            "last_message": f"event: message_end\ndata: {json.dumps({'answer': '这是SSE格式的答案'})}",
            "last_timestamp": current_time
        }),
        "task_4": json.dumps({
            "task_id": "task_4",
            "conversation_id": "conv_4",
            "task_type": "未知类型",
            "last_message": "无效的JSON格式{",
            "last_timestamp": current_time - 200
        }),
        "task_5": json.dumps({
            "task_id": "task_5",
            "conversation_id": "conv_5",
            "task_type": "测试任务",
            "last_message": "",  # 空消息
            "last_timestamp": current_time - 10
        }),
    }
    
    redis_data = {
        "user_tasks:1": task_data
    }
    
    return MockRedis(redis_data)


@pytest.fixture
def mock_redis_malformed_data():
    """创建包含格式错误数据的 Redis mock"""
    import time
    current_time = time.time()
    
    # 包含无法解析的 JSON 数据
    task_data = {
        "task_1": "这不是有效的JSON字符串{",  # 无效的JSON
    }
    
    redis_data = {
        "user_tasks:1": task_data
    }
    
    return MockRedis(redis_data)


@pytest.fixture
def mock_redis_missing_timestamp():
    """创建缺少时间戳字段的数据"""
    import time
    current_time = time.time()
    
    task_data = {
        "task_1": json.dumps({
            "task_id": "task_1",
            "conversation_id": "conv_1",
            "task_type": "测试任务",
            "last_message": "测试消息",
            # 缺少 last_timestamp
        }),
    }
    
    redis_data = {
        "user_tasks:1": task_data
    }
    
    return MockRedis(redis_data)


@pytest.mark.asyncio
async def test_get_history_success(mock_redis_with_data, mock_user):
    """测试成功获取历史记录"""
    from apps.routes.chat import get_user_history
    from config import settings
    
    # Mock settings
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        # 创建模拟请求
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis_with_data
        
        # Mock check_maintenance_mode 依赖
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            response = await get_user_history(
                request=mock_request,
                current_user=mock_user
            )
    
    # 验证响应
    assert response["user_id"] == 1
    assert "history" in response
    assert "total" in response
    assert response["total"] == 5
    
    # 验证历史记录按时间戳降序排序
    history = response["history"]
    timestamps = [h["last_timestamp"] for h in history]
    assert timestamps == sorted(timestamps, reverse=True)
    
    # 验证不同格式的消息都被正确处理
    task_1 = next((h for h in history if h["task_id"] == "task_1"), None)
    assert task_1 is not None
    assert task_1["last_message"] == "这是一条普通文本消息"
    
    task_2 = next((h for h in history if h["task_id"] == "task_2"), None)
    assert task_2 is not None
    assert task_2["last_message"] == "这是JSON格式的答案"
    
    task_3 = next((h for h in history if h["task_id"] == "task_3"), None)
    assert task_3 is not None
    assert task_3["last_message"] == "这是SSE格式的答案"
    
    task_4 = next((h for h in history if h["task_id"] == "task_4"), None)
    assert task_4 is not None
    # 无效JSON应该保持原样
    assert task_4["last_message"] == "无效的JSON格式{"
    
    task_5 = next((h for h in history if h["task_id"] == "task_5"), None)
    assert task_5 is not None
    assert task_5["last_message"] == ""


@pytest.mark.asyncio
async def test_get_history_empty(mock_redis_empty, mock_user):
    """测试空历史记录"""
    from apps.routes.chat import get_user_history
    from config import settings
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis_empty
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            response = await get_user_history(
                request=mock_request,
                current_user=mock_user
            )
    
    assert response["user_id"] == 1
    assert response["history"] == []
    assert response["total"] == 0


@pytest.mark.asyncio
async def test_get_history_redis_unavailable(mock_user):
    """测试 Redis 不可用的情况"""
    from apps.routes.chat import get_user_history
    from fastapi import HTTPException
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = False
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = None
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            with pytest.raises(NotImplementedError):
                await get_user_history(
                    request=mock_request,
                    current_user=mock_user
                )


@pytest.mark.asyncio
async def test_get_history_malformed_json(mock_redis_malformed_data, mock_user):
    """测试处理格式错误的 JSON 数据"""
    from apps.routes.chat import get_user_history
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis_malformed_data
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            # 应该抛出异常，因为无法解析 JSON
            with pytest.raises((json.JSONDecodeError, KeyError, TypeError)):
                await get_user_history(
                    request=mock_request,
                    current_user=mock_user
                )


@pytest.mark.asyncio
async def test_get_history_missing_timestamp(mock_redis_missing_timestamp, mock_user):
    """测试缺少时间戳字段的情况"""
    from apps.routes.chat import get_user_history
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis_missing_timestamp
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            # 应该抛出 KeyError，因为缺少 last_timestamp
            with pytest.raises((KeyError, TypeError)):
                await get_user_history(
                    request=mock_request,
                    current_user=mock_user
                )


@pytest.mark.asyncio
async def test_get_history_redis_exception(mock_user):
    """测试 Redis 操作抛出异常的情况"""
    from apps.routes.chat import get_user_history
    from fastapi import HTTPException
    
    # 创建会抛出异常的 Redis mock
    mock_redis = AsyncMock()
    mock_redis.hgetall = AsyncMock(side_effect=Exception("Redis connection error"))
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            with pytest.raises(HTTPException) as exc_info:
                await get_user_history(
                    request=mock_request,
                    current_user=mock_user
                )
            
            assert exc_info.value.status_code == 500
            assert "获取用户历史失败" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_history_sse_format_variations(mock_user):
    """测试各种 SSE 格式变体"""
    from apps.routes.chat import get_user_history
    import time
    
    current_time = time.time()
    
    # 测试不同的 SSE 格式
    test_cases = [
        {
            "name": "标准 SSE 格式",
            "message": f"event: message_end\ndata: {json.dumps({'answer': '标准答案'})}",
            "expected": "标准答案"
        },
        {
            "name": "SSE 格式带换行",
            "message": f"event: message_end\n\ndata: {json.dumps({'answer': '带换行答案'})}",
            "expected": "带换行答案"
        },
        {
            "name": "SSE 格式带多余空格",
            "message": f"event: message_end\ndata:   {json.dumps({'answer': '带空格答案'})}  ",
            "expected": "带空格答案"
        },
    ]
    
    for test_case in test_cases:
        task_data = {
            "test_task": json.dumps({
                "task_id": "test_task",
                "conversation_id": "conv_test",
                "task_type": "测试",
                "last_message": test_case["message"],
                "last_timestamp": current_time
            })
        }
        
        redis_data = {
            "user_tasks:1": task_data
        }
        
        mock_redis = MockRedis(redis_data)
        
        with patch('apps.routes.chat.settings') as mock_settings:
            mock_settings.REDIS_AVAILABLE = True
            
            mock_request = MagicMock(spec=Request)
            mock_request.app.state.redis = mock_redis
            
            with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
                response = await get_user_history(
                    request=mock_request,
                    current_user=mock_user
                )
                
                assert response["total"] == 1
                assert response["history"][0]["last_message"] == test_case["expected"]


@pytest.mark.asyncio
async def test_get_history_json_without_answer(mock_user):
    """测试 JSON 格式但不包含 answer 字段的情况"""
    from apps.routes.chat import get_user_history
    import time
    
    current_time = time.time()
    
    task_data = {
        "task_1": json.dumps({
            "task_id": "task_1",
            "conversation_id": "conv_1",
            "task_type": "测试",
            "last_message": json.dumps({"content": "没有answer字段的JSON"}),
            "last_timestamp": current_time
        })
    }
    
    redis_data = {
        "user_tasks:1": task_data
    }
    
    mock_redis = MockRedis(redis_data)
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            response = await get_user_history(
                request=mock_request,
                current_user=mock_user
            )
            
            # 应该保持原始 JSON 字符串，因为没有 answer 字段
            assert response["total"] == 1
            assert "没有answer字段的JSON" in response["history"][0]["last_message"]


@pytest.mark.asyncio
async def test_get_history_timestamp_conversion(mock_user):
    """测试时间戳转换和格式化"""
    from apps.routes.chat import get_user_history
    import time
    
    test_timestamp = time.time()
    
    task_data = {
        "task_1": json.dumps({
            "task_id": "task_1",
            "conversation_id": "conv_1",
            "task_type": "测试",
            "last_message": "测试消息",
            "last_timestamp": test_timestamp
        })
    }
    
    redis_data = {
        "user_tasks:1": task_data
    }
    
    mock_redis = MockRedis(redis_data)
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            response = await get_user_history(
                request=mock_request,
                current_user=mock_user
            )
            
            history_item = response["history"][0]
            assert history_item["last_timestamp"] == test_timestamp
            assert "last_time" in history_item
            # 验证时间格式
            assert len(history_item["last_time"]) == 19  # "YYYY-MM-DD HH:MM:SS"
            assert history_item["last_time"].count("-") == 2
            assert history_item["last_time"].count(":") == 2


@pytest.mark.asyncio
async def test_get_history_task_type_default(mock_user):
    """测试默认任务类型"""
    from apps.routes.chat import get_user_history
    import time
    
    current_time = time.time()
    
    # 缺少 task_type 字段
    task_data = {
        "task_1": json.dumps({
            "task_id": "task_1",
            "conversation_id": "conv_1",
            "last_message": "测试消息",
            "last_timestamp": current_time
        })
    }
    
    redis_data = {
        "user_tasks:1": task_data
    }
    
    mock_redis = MockRedis(redis_data)
    
    with patch('apps.routes.chat.settings') as mock_settings:
        mock_settings.REDIS_AVAILABLE = True
        
        mock_request = MagicMock(spec=Request)
        mock_request.app.state.redis = mock_redis
        
        with patch('apps.routes.chat.check_maintenance_mode', return_value=mock_user):
            response = await get_user_history(
                request=mock_request,
                current_user=mock_user
            )
            
            assert response["total"] == 1
            assert response["history"][0]["task_type"] == "未知类型"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

