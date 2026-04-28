"""
独立测试脚本：用于在生产环境中诊断 /history 端点的问题
可以直接运行：python test_history_endpoint_standalone.py
"""
import os
import sys
import json
import asyncio
import traceback
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到路径
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import redis.asyncio as aioredis
    from config import settings
    from apps.routes.chat import get_user_task_key
    from core.authentication import User
except ImportError as e:
    print(f"❌ 导入错误: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)


class HistoryEndpointTester:
    """历史记录端点测试器"""
    
    def __init__(self):
        self.redis_client = None
        self.test_results = []
        
    async def connect_redis(self):
        """连接到 Redis"""
        try:
            print("🔌 正在连接 Redis...")
            print(f"   Host: {settings.REDIS_HOST}")
            print(f"   Port: {settings.REDIS_PORT}")
            print(f"   DB: {settings.REDIS_DB}")
            print(f"   REDIS_AVAILABLE: {settings.REDIS_AVAILABLE}")
            
            if not settings.REDIS_AVAILABLE:
                print("⚠️  Redis 未启用 (REDIS_AVAILABLE=False)")
                return False
            
            self.redis_client = await aioredis.from_url(
                f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=False  # 保持字节模式以兼容现有代码
            )
            
            # 测试连接
            await self.redis_client.ping()
            print("✅ Redis 连接成功")
            return True
            
        except Exception as e:
            print(f"❌ Redis 连接失败: {e}")
            print(traceback.format_exc())
            return False
    
    async def disconnect_redis(self):
        """断开 Redis 连接"""
        if self.redis_client:
            await self.redis_client.aclose()
            print("🔌 Redis 连接已关闭")
    
    async def test_get_user_tasks(self, user_id: int):
        """测试获取用户任务数据"""
        print(f"\n📋 测试获取用户 {user_id} 的任务数据...")
        
        try:
            user_task_key = get_user_task_key(str(user_id))
            print(f"   Redis Key: {user_task_key}")
            
            tasks_data = await self.redis_client.hgetall(user_task_key)
            print(f"   ✅ 成功获取数据，任务数量: {len(tasks_data)}")
            
            if len(tasks_data) == 0:
                print("   ⚠️  该用户没有任务数据")
                return []
            
            # 分析每个任务的数据格式
            task_list = []
            for task_id, task_info in tasks_data.items():
                task_id_str = task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
                print(f"\n   📦 任务 ID: {task_id_str}")
                
                try:
                    # 解析 JSON
                    task_info_str = task_info.decode('utf-8') if isinstance(task_info, bytes) else task_info
                    task_data = json.loads(task_info_str)
                    
                    print(f"      ✅ JSON 解析成功")
                    print(f"      - conversation_id: {task_data.get('conversation_id', 'N/A')}")
                    print(f"      - task_type: {task_data.get('task_type', 'N/A')}")
                    print(f"      - last_timestamp: {task_data.get('last_timestamp', 'N/A')}")
                    
                    # 检查 last_message
                    last_message = task_data.get("last_message", "")
                    print(f"      - last_message 类型: {type(last_message)}")
                    print(f"      - last_message 长度: {len(str(last_message))}")
                    
                    # 尝试解析 last_message
                    self._analyze_last_message(last_message)
                    
                    task_list.append({
                        "task_id": task_id_str,
                        "task_data": task_data,
                        "raw_info": task_info_str
                    })
                    
                except json.JSONDecodeError as e:
                    print(f"      ❌ JSON 解析失败: {e}")
                    print(f"      Raw data: {task_info_str[:200]}...")
                    task_list.append({
                        "task_id": task_id_str,
                        "error": f"JSON解析失败: {str(e)}",
                        "raw_info": task_info_str
                    })
                except Exception as e:
                    print(f"      ❌ 处理任务数据时出错: {e}")
                    print(traceback.format_exc())
            
            return task_list
            
        except Exception as e:
            print(f"   ❌ 获取用户任务失败: {e}")
            print(traceback.format_exc())
            return []
    
    def _analyze_last_message(self, last_message_str: str):
        """分析 last_message 的格式"""
        if not last_message_str:
            print(f"      - last_message: (空)")
            return
        
        print(f"      - last_message 预览: {str(last_message_str)[:100]}...")
        
        # 检查是否是 SSE 格式
        if isinstance(last_message_str, str) and last_message_str.startswith('event: message_end'):
            print(f"      ✅ 检测到 SSE 格式")
            try:
                json_str = last_message_str.split('data: ', 1)[1].strip()
                message_content = json.loads(json_str)
                if 'answer' in message_content:
                    print(f"      ✅ 包含 answer 字段: {message_content['answer'][:50]}...")
                else:
                    print(f"      ⚠️  JSON 中不包含 answer 字段")
            except (json.JSONDecodeError, IndexError) as e:
                print(f"      ❌ SSE 格式解析失败: {e}")
        
        # 检查是否是普通 JSON
        elif isinstance(last_message_str, str):
            try:
                message_content = json.loads(last_message_str)
                print(f"      ✅ 检测到 JSON 格式")
                if 'answer' in message_content:
                    print(f"      ✅ 包含 answer 字段: {message_content['answer'][:50]}...")
                else:
                    print(f"      ⚠️  JSON 中不包含 answer 字段")
            except json.JSONDecodeError:
                print(f"      ℹ️  普通文本格式（非 JSON）")
    
    async def test_history_endpoint_logic(self, user_id: int):
        """测试历史记录端点的完整逻辑"""
        print(f"\n🔍 测试历史记录端点逻辑 (用户 ID: {user_id})...")
        
        try:
            history = []
            if settings.REDIS_AVAILABLE and self.redis_client:
                user_task_key = get_user_task_key(str(user_id))
                tasks_data = await self.redis_client.hgetall(user_task_key)
                
                print(f"   获取到 {len(tasks_data)} 个任务")
                
                for task_id, task_info in tasks_data.items():
                    try:
                        # 解码字节
                        task_id_str = task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
                        task_info_str = task_info.decode('utf-8') if isinstance(task_info, bytes) else task_info
                        
                        print(f"\n   📦 处理任务: {task_id_str}")
                        
                        task_data = json.loads(task_info_str)
                        
                        last_message_str = task_data.get("last_message", "")
                        display_message = last_message_str
                        
                        # 尝试解析 last_message
                        try:
                            if isinstance(last_message_str, str) and last_message_str.startswith('event: message_end'):
                                json_str = last_message_str.split('data: ', 1)[1].strip()
                                message_content = json.loads(json_str)
                                if 'answer' in message_content:
                                    display_message = message_content['answer']
                                    print(f"      ✅ SSE 格式解析成功")
                            else:
                                if isinstance(last_message_str, str):
                                    message_content = json.loads(last_message_str)
                                    if 'answer' in message_content:
                                        display_message = message_content['answer']
                                        print(f"      ✅ JSON 格式解析成功")
                        except (json.JSONDecodeError, IndexError, TypeError) as e:
                            print(f"      ⚠️  消息解析失败，使用原始消息: {e}")
                            display_message = last_message_str
                        
                        # 获取时间戳
                        last_timestamp = task_data.get("last_timestamp", "")
                        if not last_timestamp:
                            print(f"      ⚠️  缺少 last_timestamp")
                            last_timestamp = 0
                        
                        # 格式化时间
                        try:
                            last_time = datetime.fromtimestamp(last_timestamp).strftime("%Y-%m-%d %H:%M:%S")
                        except (ValueError, TypeError, OSError) as e:
                            print(f"      ❌ 时间戳转换失败: {e}")
                            last_time = "无效时间"
                        
                        history.append({
                            "task_id": task_id_str,
                            "conversation_id": task_data.get("conversation_id"),
                            "task_type": task_data.get("task_type", "未知类型"),
                            "last_message": display_message,
                            "last_timestamp": last_timestamp,
                            "last_time": last_time
                        })
                        
                        print(f"      ✅ 任务处理成功")
                        
                    except json.JSONDecodeError as e:
                        print(f"      ❌ JSON 解析失败: {e}")
                        print(f"      Raw data: {task_info_str[:200]}...")
                    except Exception as e:
                        print(f"      ❌ 处理任务时出错: {e}")
                        print(traceback.format_exc())
                
                # 按时间戳降序排序
                history.sort(key=lambda x: x.get('last_timestamp', 0), reverse=True)
                
                print(f"\n   ✅ 处理完成，共 {len(history)} 条历史记录")
                
                return {
                    "user_id": user_id,
                    "history": history,
                    "total": len(history)
                }
            else:
                print("   ❌ Redis 不可用")
                return None
                
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")
            print(traceback.format_exc())
            return None
    
    async def run_all_tests(self, user_id: int = 1):
        """运行所有测试"""
        print("=" * 60)
        print("🧪 历史记录端点诊断测试")
        print("=" * 60)
        
        # 连接 Redis
        if not await self.connect_redis():
            print("\n❌ 无法连接到 Redis，测试终止")
            return
        
        try:
            # 测试 1: 获取用户任务数据
            tasks = await self.test_get_user_tasks(user_id)
            
            # 测试 2: 测试完整端点逻辑
            result = await self.test_history_endpoint_logic(user_id)
            
            if result:
                print("\n" + "=" * 60)
                print("📊 测试结果摘要")
                print("=" * 60)
                print(f"用户 ID: {result['user_id']}")
                print(f"历史记录总数: {result['total']}")
                print("\n历史记录列表:")
                for i, item in enumerate(result['history'][:5], 1):  # 只显示前5条
                    print(f"\n  {i}. 任务 ID: {item['task_id']}")
                    print(f"     类型: {item['task_type']}")
                    print(f"     时间: {item['last_time']}")
                    print(f"     消息预览: {str(item['last_message'])[:50]}...")
                
                if result['total'] > 5:
                    print(f"\n  ... 还有 {result['total'] - 5} 条记录")
            
        finally:
            await self.disconnect_redis()
        
        print("\n" + "=" * 60)
        print("✅ 测试完成")
        print("=" * 60)


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='测试 /history 端点')
    parser.add_argument('--user-id', type=int, default=1, help='要测试的用户 ID (默认: 1)')
    args = parser.parse_args()
    
    tester = HistoryEndpointTester()
    await tester.run_all_tests(user_id=args.user_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生错误: {e}")
        print(traceback.format_exc())

