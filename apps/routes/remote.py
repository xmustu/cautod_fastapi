"""
远程桌面 WebSocket 代理
该模块运行在 Docker 容器中，作为前端和 Windows 主机上远程桌面服务的桥梁
"""
import asyncio
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import aiohttp
import os

# 创建路由
app = APIRouter(tags=["远程控制代理"])

# 配置 Jinja2 模板
templates = Jinja2Templates(directory="templates")

from config import settings

# 从环境变量读取远程桌面服务地址
# OPTIMIZE_API_URL 格式: http://127.0.0.1:9100 或 http://host:port
OPTIMIZE_API_URL = settings.OPTIMIZE_API_URL

# 提取 host 和 port 用于 WebSocket 连接
# 移除协议部分 (http:// 或 https://)
if OPTIMIZE_API_URL.startswith("http://"):
    ws_protocol = "ws://"
    host_port = OPTIMIZE_API_URL[7:]  # 移除 "http://"
elif OPTIMIZE_API_URL.startswith("https://"):
    ws_protocol = "wss://"
    host_port = OPTIMIZE_API_URL[8:]  # 移除 "https://"
else:
    # 如果没有协议，假设是 http
    ws_protocol = "ws://"
    host_port = OPTIMIZE_API_URL

# 移除尾部的斜杠（如果有）
host_port = host_port.rstrip("/")

REMOTE_DESKTOP_HTTP_URL = f"{OPTIMIZE_API_URL.rstrip('/')}"
REMOTE_DESKTOP_WS_URL = f"{ws_protocol}{host_port}/remote/ws/remote"

print("=" * 80)
print(f"[远程桌面代理] 初始化配置:")
print(f"  - OPTIMIZE_API_URL: {OPTIMIZE_API_URL}")
print(f"  - HTTP 基础地址: {REMOTE_DESKTOP_HTTP_URL}")
print(f"  - WebSocket 地址: {REMOTE_DESKTOP_WS_URL}")
print(f"  - HTTP 健康检查: {REMOTE_DESKTOP_HTTP_URL}/remote/health")
print("=" * 80)


@app.get("/", response_class=HTMLResponse)
async def remote_desktop_test_page(request: Request):
    """
    返回远程桌面测试页面（主页）
    访问 /api/remote/ 可以看到远程桌面控制的测试界面
    保持与原来相同的路径，避免前端修改
    """
    print(f"[远程桌面代理] 收到测试页面请求")
    
    # 获取屏幕尺寸信息（从远程服务获取）
    screen_width = 1920
    screen_height = 1080
    screen_grab_available = True
    screen_grab_status = "代理模式：通过 Windows 主机远程桌面服务"
    
    try:
        # 尝试从远程服务获取实际屏幕尺寸
        async with aiohttp.ClientSession() as session:
            health_url = f"{REMOTE_DESKTOP_HTTP_URL}/remote/health"
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    health_data = await resp.json()
                    screen_size = health_data.get('screen_size', {})
                    screen_width = screen_size.get('width', 1920)
                    screen_height = screen_size.get('height', 1080)
    except Exception as e:
        print(f"[远程桌面代理] 获取远程屏幕信息失败: {e}")
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "screen_width": screen_width,
            "screen_height": screen_height,
            "screen_grab_available": screen_grab_available,
            "screen_grab_status": screen_grab_status
        }
    )


@app.get("/info")
async def remote_info():
    """获取远程桌面服务信息（API端点）"""
    print(f"[远程桌面代理] 收到服务信息请求")
    return {
        "service": "远程桌面代理",
        "remote_service": REMOTE_DESKTOP_WS_URL,
        "status": "running",
        "description": "该服务作为前端和 Windows 主机远程桌面服务之间的 WebSocket 代理"
    }


@app.get("/health")
async def health_check():
    """健康检查并测试与远程服务的连接"""
    print(f"[远程桌面代理] 收到健康检查请求")
    try:
        # 尝试连接到远程服务的 HTTP 端点
        async with aiohttp.ClientSession() as session:
            health_url = f"{REMOTE_DESKTOP_HTTP_URL}/remote/health"
            print(f"[远程桌面代理] 正在连接远程健康检查端点: {health_url}")
            async with session.get(health_url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                print(f"[远程桌面代理] 远程服务响应状态码: {resp.status}")
                if resp.status == 200:
                    remote_health = await resp.json()
                    print(f"[远程桌面代理] 远程服务健康状态: {remote_health}")
                    return {
                        "status": "healthy",
                        "proxy": "running",
                        "remote_service": {
                            "status": "connected",
                            "details": remote_health
                        }
                    }
                else:
                    print(f"[远程桌面代理] 远程服务返回错误状态码: {resp.status}")
                    return {
                        "status": "degraded",
                        "proxy": "running",
                        "remote_service": {
                            "status": "error",
                            "message": f"远程服务返回状态码: {resp.status}"
                        }
                    }
    except asyncio.TimeoutError:
        print(f"[远程桌面代理] 连接远程服务超时")
        return {
            "status": "degraded",
            "proxy": "running",
            "remote_service": {
                "status": "timeout",
                "message": "连接远程服务超时",
                "url": f"{REMOTE_DESKTOP_HTTP_URL}/remote/health"
            }
        }
    except Exception as e:
        print(f"[远程桌面代理] 连接远程服务失败: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "degraded",
            "proxy": "running",
            "remote_service": {
                "status": "unreachable",
                "message": f"无法连接到远程服务: {str(e)}",
                "url": REMOTE_DESKTOP_WS_URL
            }
        }


@app.websocket("/ws/")
async def websocket_proxy(websocket: WebSocket):
    """
    WebSocket 代理端点
    将前端的 WebSocket 连接代理到 Windows 主机上的远程桌面服务
    """
    client_host = websocket.client.host if websocket.client else "unknown"
    print(f"\n{'='*80}")
    print(f"[远程桌面代理] 收到前端 WebSocket 连接请求")
    print(f"  - 客户端地址: {client_host}")
    print(f"  - 目标地址: {REMOTE_DESKTOP_WS_URL}")
    print(f"{'='*80}\n")
    
    await websocket.accept()
    print(f"[远程桌面代理] ✓ 前端 WebSocket 连接已建立")
    
    remote_ws = None
    connection_success = False
    
    try:
        # 连接到远程桌面服务
        print(f"[远程桌面代理] 正在连接到远程服务...")
        async with aiohttp.ClientSession() as session:
            try:
                print(f"[远程桌面代理] 尝试建立 WebSocket 连接: {REMOTE_DESKTOP_WS_URL}")
                remote_ws = await session.ws_connect(
                    REMOTE_DESKTOP_WS_URL,
                    timeout=aiohttp.ClientTimeout(total=10)
                )
                connection_success = True
                print(f"[远程桌面代理] ✓ 成功连接到远程服务")
                print(f"[远程桌面代理] 开始双向数据转发...")
                
                # 消息计数器
                msg_to_remote = 0
                msg_to_client = 0
                
                # 创建两个任务：一个从前端接收消息并转发到远程服务，另一个从远程服务接收消息并转发到前端
                async def forward_to_remote():
                    """从前端接收消息并转发到远程服务"""
                    nonlocal msg_to_remote
                    try:
                        while True:
                            data = await websocket.receive_text()
                            msg_to_remote += 1
                            
                            # 打印消息摘要
                            if data == "screenshot":
                                print(f"[前端→远程] #{msg_to_remote}: 请求截图")
                            elif data.startswith("mouse"):
                                print(f"[前端→远程] #{msg_to_remote}: 鼠标事件 - {data[:30]}")
                            elif data.startswith("key"):
                                print(f"[前端→远程] #{msg_to_remote}: 键盘事件 - {data[:30]}")
                            else:
                                print(f"[前端→远程] #{msg_to_remote}: {data[:50]}")
                            
                            await remote_ws.send_str(data)
                    except WebSocketDisconnect:
                        print(f"[远程桌面代理] ✗ 前端连接断开 (已转发 {msg_to_remote} 条消息)")
                    except Exception as e:
                        print(f"[远程桌面代理] ✗ 转发到远程时出错: {type(e).__name__}: {e}")
                        import traceback
                        traceback.print_exc()
                
                async def forward_to_client():
                    """从远程服务接收消息并转发到前端"""
                    nonlocal msg_to_client
                    try:
                        async for msg in remote_ws:
                            msg_to_client += 1
                            
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                print(f"[远程→前端] #{msg_to_client}: 截图数据 {len(msg.data)} 字节")
                                await websocket.send_bytes(msg.data)
                            elif msg.type == aiohttp.WSMsgType.TEXT:
                                print(f"[远程→前端] #{msg_to_client}: 文本消息 - {msg.data[:50]}")
                                await websocket.send_text(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                print(f"[远程桌面代理] ✗ 远程服务 WebSocket 错误")
                                break
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                print(f"[远程桌面代理] ✗ 远程服务关闭连接")
                                break
                    except Exception as e:
                        print(f"[远程桌面代理] ✗ 转发到前端时出错: {type(e).__name__}: {e}")
                        import traceback
                        traceback.print_exc()
                
                # 并行运行两个转发任务
                print(f"[远程桌面代理] 启动双向转发任务...")
                await asyncio.gather(
                    forward_to_remote(),
                    forward_to_client(),
                    return_exceptions=True
                )
                print(f"[远程桌面代理] 转发任务结束 (→远程: {msg_to_remote}, →前端: {msg_to_client})")
                
            except asyncio.TimeoutError:
                print(f"[远程桌面代理] ✗ 连接超时: {REMOTE_DESKTOP_WS_URL}")
                error_msg = json.dumps({
                    "type": "error",
                    "message": "连接远程桌面服务超时",
                    "suggestion": "请确保 Windows 主机上的远程桌面服务正在运行",
                    "url": REMOTE_DESKTOP_WS_URL
                }, ensure_ascii=False)
                await websocket.send_text(f"error:{error_msg}")
            except aiohttp.ClientError as e:
                print(f"[远程桌面代理] ✗ 连接失败: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                error_msg = json.dumps({
                    "type": "error",
                    "message": f"无法连接到远程桌面服务: {str(e)}",
                    "suggestion": "请检查 Windows 主机上的远程桌面服务是否正在运行，以及网络配置是否正确",
                    "url": REMOTE_DESKTOP_WS_URL
                }, ensure_ascii=False)
                await websocket.send_text(f"error:{error_msg}")
            
    except WebSocketDisconnect:
        print(f"[远程桌面代理] ✗ 前端 WebSocket 连接断开")
    except Exception as e:
        print(f"[远程桌面代理] ✗ WebSocket 代理错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        try:
            error_msg = json.dumps({
                "type": "error",
                "message": f"代理服务错误: {str(e)}"
            }, ensure_ascii=False)
            await websocket.send_text(f"error:{error_msg}")
        except:
            pass
    finally:
        if remote_ws and not remote_ws.closed:
            await remote_ws.close()
        print("[远程桌面代理] WebSocket 连接已清理")


@app.websocket("/ws/{user_id}")
async def websocket_endpoint_with_user(websocket: WebSocket, user_id: str):
    """
    带用户ID的 WebSocket 端点（保持向后兼容）
    """
    print(f"[远程桌面代理] 用户 {user_id} 正在连接")
    await websocket_proxy(websocket)


# 旧代码移除标记 - 以下是被移除的旧实现
# Windows 锁屏检测
# def _old_is_windows_locked():
#     """检测 Windows 系统是否处于锁屏状态
    
#     注意：这个方法不是100%准确，因为 Windows 锁屏检测比较复杂
#     更可靠的方法是通过截图检测黑屏
#     """
#     if platform.system() != "Windows":
#         return False
    
#     try:
#         import ctypes
        
#         # 使用 Windows API 检测
#         user32 = ctypes.windll.user32
        
#         try:
#             # 方法1: 检查是否有活动窗口
#             # 锁屏时通常没有活动窗口
#             hwnd = user32.GetForegroundWindow()
            
#             # 方法2: 检查桌面窗口是否存在
#             desktop_hwnd = user32.GetDesktopWindow()
            
#             # 如果都没有，可能是锁屏
#             # 但这不是100%准确，因为某些情况下也可能没有活动窗口
#             if hwnd == 0 and desktop_hwnd == 0:
#                 return True
                
#             return False
#         except Exception as e:
#             # 如果 API 调用失败，无法确定
#             return False
#     except ImportError:
#         # 如果 ctypes 不可用，无法检测
#         return False

# def detect_black_screen(image):
#     """检测截图是否是黑屏（可能是锁屏状态）
    
#     通过分析图片的像素值来判断是否是黑屏
#     返回 (is_black, black_percentage)
#     """
#     try:
#         width, height = image.size
        
#         # 采样检查（检查多个区域，避免只检查一个点）
#         sample_regions = [
#             (width // 4, height // 4, width // 2, height // 2),  # 中心区域
#             (0, 0, width // 4, height // 4),  # 左上角
#             (3 * width // 4, 3 * height // 4, width // 4, height // 4),  # 右下角
#         ]
        
#         total_pixels = 0
#         black_pixels = 0
        
#         for x, y, w, h in sample_regions:
#             # 在这个区域内采样
#             step = max(10, min(w, h) // 20)  # 采样步长
#             for px in range(x, x + w, step):
#                 for py in range(y, y + h, step):
#                     if px < width and py < height:
#                         r, g, b = image.getpixel((px, py))
#                         total_pixels += 1
#                         # 如果 RGB 值都很低（接近黑色，阈值设为20）
#                         if r < 20 and g < 20 and b < 20:
#                             black_pixels += 1
        
#         if total_pixels == 0:
#             return False, 0
        
#         black_percentage = (black_pixels / total_pixels) * 100
        
#         # 如果超过80%的像素是黑色，认为是黑屏
#         is_black = black_percentage > 80
        
#         return is_black, black_percentage
#     except Exception as e:
#         print(f"检测黑屏时出错: {e}")
#         return False, 0

# def unlock_windows_screen():
#     """尝试解锁 Windows 屏幕（需要管理员权限）"""
#     if platform.system() != "Windows":
#         return False
    
#     try:
#         # 方法1: 模拟按键（需要知道密码或使用其他方法）
#         # 注意：这通常不安全，不推荐
#         # pyautogui.press('enter')  # 如果有密码，这不会工作
        
#         # 方法2: 使用 Windows API 解锁（需要特殊权限）
#         # 这通常需要系统级权限，不推荐在远程控制中使用
        
#         # 实际上，解锁屏幕通常需要用户交互或系统级权限
#         # 这里只提供检测功能，不提供自动解锁
#         return False
#     except:
#         return False

# # 尝试导入替代截图库
# try:
#     import mss
#     MSS_AVAILABLE = True
# except ImportError:
#     MSS_AVAILABLE = False
#     print("[远程控制] mss 库未安装，将使用其他截图方法")

# # 创建一个新的 APIRouter 实例
# app = APIRouter(
#     tags=["远程控制"]
# )

# pyautogui.PAUSE = 0 # 设置无延迟
# # 获取屏幕尺寸（分辨率）
# screen_width, screen_height = pyautogui.size()

# # 对于远程控制场景，禁用 fail-safe 机制
# # 注意：这仅在远程控制场景下是安全的，因为用户通过 Web 界面控制
# pyautogui.FAILSAFE = False

# # 初始化鼠标位置变量
# mouse_x, mouse_y = 0, 0

# # 截图方法函数
# def capture_screen_method1_pil():
#     """方法1: 使用 PIL ImageGrab"""
#     return ImageGrab.grab()

# def capture_screen_method2_mss():
#     """方法2: 使用 mss 库（跨平台，性能更好）
#     注意：在 Windows 锁屏时，mss 可能也无法截取锁屏界面，会返回黑屏
#     """
#     if not MSS_AVAILABLE:
#         raise ImportError("mss 库未安装")
#     with mss.mss() as sct:
#         # 获取主显示器
#         monitor = sct.monitors[1]  # 0 是所有显示器，1 是主显示器
#         screenshot = sct.grab(monitor)
#         # 转换为 PIL Image
#         img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
#         return img

# def capture_screen_method3_pyautogui():
#     """方法3: 使用 pyautogui.screenshot"""
#     return pyautogui.screenshot()

# # 尝试所有截图方法，返回第一个可用的
# def capture_screen():
#     """尝试多种方法进行截图，返回第一个成功的方法"""
#     methods = [
#         ("PIL ImageGrab", capture_screen_method1_pil),
#         ("mss", capture_screen_method2_mss),
#         ("pyautogui", capture_screen_method3_pyautogui),
#     ]
    
#     last_error = None
#     for method_name, method_func in methods:
#         try:
#             screenshot = method_func()
#             return screenshot, method_name
#         except ImportError:
#             # 库未安装，跳过
#             continue
#         except Exception as e:
#             last_error = e
#             continue
    
#     # 所有方法都失败
#     raise Exception(f"所有截图方法都失败。最后错误: {str(last_error)}")

# # 检查屏幕抓取功能是否可用
# def check_screen_grab_available():
#     """检查屏幕抓取功能是否可用"""
#     try:
#         screenshot, method = capture_screen()
#         screenshot.close()
#         return True, f"屏幕抓取功能正常 (使用: {method})"
#     except Exception as e:
#         error_msg = str(e)
#         system = platform.system()
        
#         suggestions = []
#         if system == "Linux":
#             suggestions = [
#                 "Linux 系统需要图形界面支持",
#                 "请确保安装了以下之一:",
#                 "  - X11: sudo apt-get install python3-tk",
#                 "  - 或者使用虚拟显示: export DISPLAY=:0",
#                 "  - 或者使用 xvfb: xvfb-run python your_script.py",
#                 "  - 或者安装 mss: pip install mss"
#             ]
#         elif system == "Windows":
#             suggestions = [
#                 "Windows 系统截图方法:",
#                 "  1. 确保有图形界面",
#                 "  2. 安装 mss 库: pip install mss (推荐)",
#                 "  3. 检查 PIL/Pillow 是否正确安装",
#                 "  4. 检查是否有足够的权限"
#             ]
#         elif system == "Darwin":  # macOS
#             suggestions = [
#                 "macOS 系统需要屏幕录制权限",
#                 "请在系统设置中授予终端/应用的屏幕录制权限",
#                 "或者安装 mss: pip install mss"
#             ]
        
#         return False, f"屏幕抓取不可用: {error_msg}\n" + "\n".join(suggestions)

# # 在模块加载时检查
# screen_grab_available, screen_grab_status = check_screen_grab_available()
# print(f"[远程控制] 屏幕抓取状态: {screen_grab_status}")

# # WebSocket连接管理器
# class ConnectionManager:
#     def __init__(self):
#         self.activate_connections = set()

#     #接受连接并将连接对象添加到类实例的 active_connections 集合中
#     async def connect(self, websocket: WebSocket):
#         await websocket.accept()
#         self.activate_connections.add(websocket)

#     # 断开 WebSocket 连接
#     def disconnect(self, websocket: WebSocket):
#         self.activate_connections.remove(websocket)

#     async def send_screenshot(self, screenshot_data: bytes):
#         for connection in self.activate_connections:
#             await connection.send_bytes(screenshot_data)
#     # 鼠标移动
#     async def handle_mouse_move(self, data: str):
#         global mouse_x, mouse_y
#         try:
#             # 确保 fail-safe 已禁用
#             pyautogui.FAILSAFE = False
            
#             # 解析前端发送的鼠标位置信息
#             x, y = data.replace("mouseMove:", '').split(",")
#             x, y = int(float(x)), int(float(y))
            
#             # 边界检查：确保坐标在屏幕范围内
#             x = max(0, min(x, screen_width - 1))
#             y = max(0, min(y, screen_height - 1))
            
#             # 更新鼠标位置信息
#             mouse_x, mouse_y = x, y
#             # 在服务端电脑上模拟鼠标移动
#             pyautogui.moveTo(mouse_x, mouse_y, duration=0)
#         except Exception as e:
#             print(f"鼠标移动错误: {e}")
#             # 不抛出异常，避免断开连接

#     # 鼠标左键点击
#     async def handle_mouse_click(self, data: str):
#         global mouse_x, mouse_y
#         try:
#             # 确保 fail-safe 已禁用
#             pyautogui.FAILSAFE = False
            
#             # 解析前端发送的鼠标位置信息
#             x, y = data.replace("mouseClick:", '').split(",")
#             x, y = int(float(x)), int(float(y))
            
#             # 边界检查
#             x = max(0, min(x, screen_width - 1))
#             y = max(0, min(y, screen_height - 1))
            
#             # 更新鼠标位置信息
#             mouse_x, mouse_y = x, y
#             # 在服务端电脑上模拟鼠标左键点击
#             pyautogui.click(mouse_x, mouse_y)
#         except Exception as e:
#             print(f"鼠标点击错误: {e}")
#     # 鼠标左键放下
#     async def handle_mouse_down(self, data: str):
#         global mouse_x, mouse_y
#         try:
#             # 确保 fail-safe 已禁用
#             pyautogui.FAILSAFE = False
            
#             # 解析前端发送的鼠标位置信息
#             x, y = data.replace("mouseDown:", '').split(",")
#             x, y = int(float(x)), int(float(y))
            
#             # 边界检查
#             x = max(0, min(x, screen_width - 1))
#             y = max(0, min(y, screen_height - 1))
            
#             # 更新鼠标位置信息
#             mouse_x, mouse_y = x, y
#             # 在服务端电脑上模拟鼠标点击
#             pyautogui.mouseDown(mouse_x, mouse_y)
#         except Exception as e:
#             print(f"鼠标按下错误: {e}")


#     # 鼠标左键抬起
#     async def handle_mouse_up(self, data: str):
#         global mouse_x, mouse_y
#         try:
#             # 确保 fail-safe 已禁用
#             pyautogui.FAILSAFE = False
            
#             # 解析前端发送的鼠标位置信息
#             x, y = data.replace("mouseUp:", '').split(",")
#             x, y = int(float(x)), int(float(y))
            
#             # 边界检查
#             x = max(0, min(x, screen_width - 1))
#             y = max(0, min(y, screen_height - 1))
            
#             # 更新鼠标位置信息
#             mouse_x, mouse_y = x, y
#             # 在服务端电脑上模拟鼠标左键
#             pyautogui.mouseUp(mouse_x, mouse_y)
#         except Exception as e:
#             print(f"鼠标抬起错误: {e}")


#     # 鼠标右键点击
#     async def handle_mouse_right_click(self, data: str):
#         try:
#             # 确保 fail-safe 已禁用
#             pyautogui.FAILSAFE = False
            
#             # 解析前端发送的鼠标右键点击信息
#             x, y = data.replace("mouseRightClick:", '').split(",")
#             x, y = int(float(x)), int(float(y))
            
#             # 边界检查
#             x = max(0, min(x, screen_width - 1))
#             y = max(0, min(y, screen_height - 1))

#             # 在服务端电脑上模拟鼠标右键点击
#             pyautogui.rightClick(x, y)
#         except Exception as e:
#             print(f"鼠标右键点击错误: {e}")

#     # 鼠标滚轮操作
#     async def handle_mouse_scroll(self, data: str):
#         data = data.replace("mouseScroll:", "")
#         first = data.split(":")[0]
#         second = data.split(":")[1]
#         # 解析前端发送的鼠标滚动量信息
#         scroll_amount = int(float(second))
#         x = int(float(first.split(",")[0]))    
#         y = int(float(first.split(",")[1]))

#         # 在服务端电脑上模拟鼠标滚轮操作
#         pyautogui.scroll(scroll_amount)

#     # 键盘按下
#     async def handle_key_down(self, data: str):
#         # 解析前端发送的键盘按下信息
#         event, key = data.split(":")

#         # 在服务端电脑上模拟键盘按下
#         pyautogui.keyDown(key)

#     # 键盘释放
#     async def handle_key_up(self, data: str):
#         # 解析前端发送的键盘松开信息
#         event, key = data.split(":")

#         # 在服务端电脑上模拟键盘松开
#         pyautogui.keyUp(key)
        
# manager = ConnectionManager()

# @app.websocket("/ws/")
# async def websocket_endpoint(websocket: WebSocket):
#     # 确保 fail-safe 已禁用
#     pyautogui.FAILSAFE = False
#     print(f"[WebSocket] 连接建立，FAILSAFE={pyautogui.FAILSAFE}")
    
#     await manager.connect(websocket)

#     try:
#         while True:
#             data = await websocket.receive_text()

#             if data == "screenshot":
#                 try:
#                     print("screenshot")
                    
#                     # 检查 Windows 锁屏状态
#                     if platform.system() == "Windows":
#                         is_locked = is_windows_locked()
#                         if is_locked:
#                             print("[警告] 检测到 Windows 可能处于锁屏状态")
#                             # 发送警告信息给客户端
#                             try:
#                                 warning_msg = {
#                                     "type": "warning",
#                                     "message": "系统可能处于锁屏状态，截图可能显示黑屏",
#                                     "suggestion": "请解锁屏幕以确保正常截图"
#                                 }
#                                 await websocket.send_text(f"warning:{json.dumps(warning_msg, ensure_ascii=False)}")
#                             except:
#                                 pass
                    
#                     # 尝试多种方法进行截图
#                     screenshot, method = capture_screen()
#                     print(f"截图成功，使用方法: {method}, 尺寸: {screenshot.size}")
                    
#                     # 检测是否是黑屏（可能是锁屏）
#                     if platform.system() == "Windows":
#                         is_black, black_percentage = detect_black_screen(screenshot)
#                         if is_black:
#                             print(f"[警告] 检测到黑屏（黑色像素占比: {black_percentage:.1f}%），可能是锁屏状态")
#                             # 发送警告信息给客户端
#                             try:
#                                 warning_msg = {
#                                     "type": "warning",
#                                     "message": f"检测到黑屏（黑色像素占比: {black_percentage:.1f}%），系统可能处于锁屏状态",
#                                     "suggestion": "请解锁屏幕以确保正常截图。如果使用远程桌面，请保持连接处于活动状态。"
#                                 }
#                                 await websocket.send_text(f"warning:{json.dumps(warning_msg, ensure_ascii=False)}")
#                             except:
#                                 pass
                    
#                     # 对截图进行压缩
#                     buffered_screenshot = io.BytesIO()
#                     screenshot.save(buffered_screenshot, format="JPEG", quality=90)
#                     screenshot_bytes = buffered_screenshot.getvalue()
#                     screenshot.close()  # 释放资源
#                     print(f"截图压缩后大小: {len(screenshot_bytes)} bytes")
                    
#                     # 发送压缩后的截图数据给前端
#                     await manager.send_screenshot(screenshot_bytes)
#                     print("截图已发送")
#                     await asyncio.sleep(0.01)
#                 except Exception as e:
#                     error_msg = f"屏幕抓取失败: {str(e)}"
#                     print(error_msg)
#                     print(f"系统信息: {platform.system()} {platform.release()}")
                    
#                     # 创建一个错误提示图片
#                     try:
#                         error_image = Image.new('RGB', (screen_width, screen_height), color='#2c3e50')
#                         draw = ImageDraw.Draw(error_image)
                        
#                         # 尝试加载字体
#                         font = None
#                         try:
#                             if platform.system() == "Windows":
#                                 font = ImageFont.truetype("arial.ttf", 24)
#                             elif platform.system() == "Darwin":  # macOS
#                                 font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
#                             else:  # Linux
#                                 font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
#                         except:
#                             try:
#                                 font = ImageFont.load_default()
#                             except:
#                                 font = None
                        
#                         # 绘制错误信息
#                         error_text = [
#                             "屏幕抓取失败",
#                             "",
#                             f"错误: {str(e)}",
#                             "",
#                             "可能的原因:",
#                             "1. 系统不支持屏幕抓取",
#                             "2. 缺少必要的图形库依赖",
#                             "3. 没有图形界面环境",
#                             "",
#                             "解决方案:",
#                             "- Windows: 确保有图形界面",
#                             "- Linux: 安装 X11 或 Wayland 支持",
#                             "- 检查 PIL/Pillow 是否正确安装"
#                         ]
                        
#                         y_offset = 50
#                         for line in error_text:
#                             draw.text((50, y_offset), line, fill='white', font=font)
#                             y_offset += 30
                        
#                         buffered_screenshot = io.BytesIO()
#                         error_image.save(buffered_screenshot, format="JPEG", quality=90)
#                         screenshot_bytes = buffered_screenshot.getvalue()
#                         await manager.send_screenshot(screenshot_bytes)
                        
#                         # 同时发送文本错误信息
#                         try:
#                             error_response = {
#                                 "type": "error",
#                                 "message": error_msg,
#                                 "system": platform.system(),
#                                 "suggestion": "请检查系统是否支持屏幕抓取，或尝试使用其他截图方法"
#                             }
#                             await websocket.send_text(f"error:{json.dumps(error_response, ensure_ascii=False)}")
#                         except:
#                             pass
#                     except Exception as img_error:
#                         print(f"创建错误图片失败: {img_error}")
#                         # 如果连错误图片都创建失败，至少发送文本错误
#                         try:
#                             await websocket.send_text(f"error:屏幕抓取失败: {str(e)}")
#                         except:
#                             pass

#             elif data.startswith("mouseMove:"):
#                 # 确保 fail-safe 已禁用
#                 pyautogui.FAILSAFE = False
#                 print(f"鼠标移动事件：{data}")
#                 await manager.handle_mouse_move(data)
#             elif data.startswith("mouseDown"):
#                 # 处理鼠标左键按下信息
#                 await manager.handle_mouse_down(data)
#             elif data.startswith("mouseUp"):
#                 # 处理鼠标左键抬起信息
#                 await manager.handle_mouse_up(data)
                

#             elif data.startswith('mouseRightClick'):
#                 print(f"鼠标右键点击事件：{data}")
#                 await manager.handle_mouse_right_click(data)

#             elif data.startswith('mouseClick'):
#                 print(f"鼠标左键点击事件：{data}")
#                 await manager.handle_mouse_click(data)
            
#             elif data.startswith('mouseScroll'):
#                 print(f"鼠标滚轮事件：{data}")
#                 await manager.handle_mouse_scroll(data)

#             elif data.startswith('keyDown'):
#                 print(f"键盘按下事件：{data}")

#                 if data.startswith('keyDown:ctrl_c'):  
#                     pyautogui.hotkey('ctrl', 'c')
#                 elif data.startswith('keyDown:ctrl_v'):  
#                     pyautogui.hotkey('ctrl', 'v')
#                 elif data.startswith('keyDown:ctrl_x'):  
#                     pyautogui.hotkey('ctrl', 'x')
#                 elif data.startswith('keyDown:ctrl_a'):  
#                     pyautogui.hotkey('ctrl', 'a')
#                 elif data.startswith('keyDown:ctrl_z'):  
#                     pyautogui.hotkey('ctrl', 'z')
#                 elif data.startswith('keyDown:ctrl_s'):  
#                     pyautogui.hotkey('ctrl', 's')
#                 else:
#                     await manager.handle_key_down(data)

#             elif data.startswith('keyUp'):
#                 print(f"键盘松开事件：{data}")

#                 await manager.handle_key_up(data)
#     except Exception as e:
#         print(f"WebSocket 连接错误: {str(e)}")
#         manager.disconnect(websocket)
#         raise HTTPException(status_code=500, detail=f"WebSocket 连接错误: {str(e)}")

# # 使用jinja2渲染HTML模板
# env = Environment(loader=FileSystemLoader("templates"))
# template = env.get_template("index.html")

# # 主页，返回一个简单的HTML页面作为客户端
# @app.get("/", response_class=HTMLResponse)
# async def read_root():
#     return template.render(
#         screen_width=screen_width, 
#         screen_height=screen_height,
#         screen_grab_available=screen_grab_available,
#         screen_grab_status=screen_grab_status
#     )



# @app.websocket("/ws/{user_id}")
# async def websocket_endpoint(websocket: WebSocket, user_id: str):
#     # WebSocket 连接的处理逻辑
#     await websocket.accept()
#     while True:
#         data = await websocket.receive_text()
#         # 处理从客户端接收到的数据
