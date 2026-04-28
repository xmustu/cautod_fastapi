"""
测试后端 WebSocket 代理功能
该脚本测试 Docker 后端的 WebSocket 代理是否能正确转发消息到 Windows 主机的远程桌面服务
"""
import asyncio
import websockets
import json
import sys
from datetime import datetime

# 配置
BACKEND_WS_URL = "ws://127.0.0.1:8081/api/remote/ws/"  # 后端代理地址
BACKEND_HTTP_URL = "http://127.0.0.1:8081/api/remote/health"  # 后端健康检查

print("=" * 80)
print("WebSocket 代理测试脚本")
print("=" * 80)
print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"后端 WebSocket 地址: {BACKEND_WS_URL}")
print(f"后端健康检查: {BACKEND_HTTP_URL}")
print("=" * 80)


async def test_http_health():
    """测试 HTTP 健康检查"""
    print("\n[测试 1/3] HTTP 健康检查")
    print("-" * 80)
    
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(BACKEND_HTTP_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                status = resp.status
                data = await resp.json()
                
                print(f"✓ HTTP 响应成功")
                print(f"  状态码: {status}")
                print(f"  响应数据:")
                print(f"    {json.dumps(data, indent=4, ensure_ascii=False)}")
                
                if status == 200:
                    print(f"\n✓ 后端代理服务运行正常")
                    if data.get('remote_service', {}).get('status') == 'connected':
                        print(f"✓ 远程桌面服务连接正常")
                        return True
                    else:
                        print(f"✗ 远程桌面服务连接失败")
                        print(f"  详情: {data.get('remote_service', {})}")
                        return False
                else:
                    print(f"✗ 后端响应异常")
                    return False
    except Exception as e:
        print(f"✗ HTTP 健康检查失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_websocket_connection():
    """测试 WebSocket 连接建立"""
    print("\n[测试 2/3] WebSocket 连接")
    print("-" * 80)
    
    try:
        print(f"正在连接: {BACKEND_WS_URL}")
        async with websockets.connect(BACKEND_WS_URL, ping_interval=None) as ws:
            print(f"✓ WebSocket 连接成功")
            return ws
    except Exception as e:
        print(f"✗ WebSocket 连接失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_websocket_screenshot():
    """测试 WebSocket 截图功能"""
    print("\n[测试 3/3] WebSocket 截图数据传输")
    print("-" * 80)
    
    try:
        print(f"正在连接: {BACKEND_WS_URL}")
        async with websockets.connect(BACKEND_WS_URL, ping_interval=None) as ws:
            print(f"✓ WebSocket 连接已建立")
            
            # 发送截图请求
            print(f"\n发送消息: 'screenshot'")
            await ws.send("screenshot")
            print(f"✓ 截图请求已发送")
            
            # 等待响应
            print(f"\n等待响应...")
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=10.0)
                
                if isinstance(response, bytes):
                    print(f"✓ 收到二进制数据 (截图)")
                    print(f"  数据大小: {len(response)} 字节")
                    print(f"  数据大小: {len(response) / 1024:.2f} KB")
                    
                    # 验证是否是 JPEG 图片
                    if response[:2] == b'\xff\xd8':
                        print(f"✓ 数据格式验证: JPEG 图片")
                        
                        # 可选: 保存图片
                        try:
                            with open("test_screenshot.jpg", "wb") as f:
                                f.write(response)
                            print(f"✓ 截图已保存到: test_screenshot.jpg")
                        except Exception as e:
                            print(f"  (保存截图失败: {e})")
                        
                        return True
                    else:
                        print(f"✗ 数据格式验证失败: 不是 JPEG 图片")
                        print(f"  前 10 字节: {response[:10]}")
                        return False
                        
                elif isinstance(response, str):
                    print(f"✓ 收到文本消息:")
                    print(f"  {response[:200]}")
                    
                    # 检查是否是错误消息
                    if response.startswith("error:"):
                        print(f"✗ 收到错误消息")
                        try:
                            error_data = json.loads(response[6:])
                            print(f"  错误详情: {json.dumps(error_data, indent=4, ensure_ascii=False)}")
                        except:
                            pass
                        return False
                    elif response.startswith("warning:"):
                        print(f"⚠ 收到警告消息")
                        try:
                            warning_data = json.loads(response[8:])
                            print(f"  警告详情: {json.dumps(warning_data, indent=4, ensure_ascii=False)}")
                        except:
                            pass
                    return False
                else:
                    print(f"✗ 收到未知类型的响应: {type(response)}")
                    return False
                    
            except asyncio.TimeoutError:
                print(f"✗ 等待响应超时 (10秒)")
                return False
                
    except Exception as e:
        print(f"✗ WebSocket 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_websocket_mouse_event():
    """测试 WebSocket 鼠标事件"""
    print("\n[额外测试] 鼠标事件传输")
    print("-" * 80)
    
    try:
        async with websockets.connect(BACKEND_WS_URL, ping_interval=None) as ws:
            print(f"✓ WebSocket 连接已建立")
            
            # 发送鼠标移动事件
            mouse_event = "mouseMove:100,200"
            print(f"\n发送消息: '{mouse_event}'")
            await ws.send(mouse_event)
            print(f"✓ 鼠标事件已发送")
            
            # 等待可能的响应
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                print(f"收到响应: {response if isinstance(response, str) else f'{len(response)} bytes'}")
            except asyncio.TimeoutError:
                print(f"  (无响应 - 正常，鼠标事件通常不需要响应)")
            
            return True
            
    except Exception as e:
        print(f"✗ 鼠标事件测试失败: {type(e).__name__}: {e}")
        return False


async def main():
    """运行所有测试"""
    print("\n开始测试...")
    print("=" * 80)
    
    results = []
    
    # 测试 1: HTTP 健康检查
    result1 = await test_http_health()
    results.append(("HTTP 健康检查", result1))
    
    if not result1:
        print("\n" + "!" * 80)
        print("警告: HTTP 健康检查失败，后续测试可能也会失败")
        print("请确保:")
        print("  1. 后端服务正在运行 (http://127.0.0.1:8000)")
        print("  2. Windows 主机上的 optimize 服务正在运行 (http://127.0.0.1:9100)")
        print("!" * 80)
    
    # 测试 2: WebSocket 截图
    result2 = await test_websocket_screenshot()
    results.append(("WebSocket 截图传输", result2))
    
    # 测试 3: 鼠标事件
    result3 = await test_websocket_mouse_event()
    results.append(("鼠标事件传输", result3))
    
    # 显示测试结果
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status:8} | {test_name}")
    
    print("=" * 80)
    
    all_passed = all(result for _, result in results)
    if all_passed:
        print("\n🎉 所有测试通过!")
        print("\nWebSocket 代理功能正常工作:")
        print("  ✓ 后端代理可以访问")
        print("  ✓ 代理可以连接到远程服务")
        print("  ✓ 消息可以双向转发")
        print("  ✓ 截图数据可以正确传输")
        return 0
    else:
        print("\n❌ 部分测试失败")
        print("\n请检查:")
        print("  1. 后端服务是否运行: http://127.0.0.1:8000")
        print("  2. Optimize 服务是否运行: http://127.0.0.1:9100")
        print("  3. 网络连接是否正常")
        print("  4. 查看服务日志获取详细错误信息")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n测试脚本错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
