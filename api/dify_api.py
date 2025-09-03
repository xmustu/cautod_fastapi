"""
source code from He Sicheng
"""

import socket
import threading
from config import settings
def forward(source, destination):
    while True:
        try:
            data = source.recv(4096)
            if not data:
                break
            destination.sendall(data)
        except:
            break
    source.close()
    destination.close()

def handle_client(client_socket, target_host, target_port):
    try:
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 若目标服务使用默认端口，这里的target_port可省略（但实际仍会用默认值）
        target_socket.connect((target_host, target_port))
        
        threading.Thread(target=forward, args=(client_socket, target_socket)).start()
        threading.Thread(target=forward, args=(target_socket, client_socket)).start()
    
    except Exception as e:
        print(f"转发错误: {e}")
        client_socket.close()

def start_forwarder(listen_host, listen_port, target_host, target_port=80):  # 默认目标端口设为80
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((listen_host, listen_port))
    server_socket.listen(5)
    print(f"转发服务器已启动: {listen_host}:{listen_port} -> {target_host}:{target_port}")
    
    try:
        while True:
            client_socket, addr = server_socket.accept()
            threading.Thread(
                target=handle_client,
                args=(client_socket, target_host, target_port)
            ).start()
    except KeyboardInterrupt:
        print("服务器已停止")
    finally:
        server_socket.close()

if __name__ == "__main__":
    # 配置（目标端口未显式设置，使用默认80）
    LISTEN_HOST = settings.DIFY_LISTEN_HOST
    LISTEN_PORT = settings.DIFY_LISTEN_PORT  # 局域网访问端口
    TARGET_HOST = settings.DIFY_TARGET_HOST      # 本地服务地址
    TARGET_PORT = settings.DIFY_TARGET_PORT     # 被注释，使用函数默认值
    
    start_forwarder(LISTEN_HOST, LISTEN_PORT, TARGET_HOST, TARGET_PORT)
    