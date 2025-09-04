import asyncio
import subprocess
import threading
import queue

output_queue = queue.Queue()  # 线程安全的队列

def read_subprocess_output(proc: subprocess.Popen, q: queue.Queue):
    """在独立线程中读取子进程输出"""
    # 读取stdout
    for line in iter(proc.stdout.readline, ''):
        if line:
            q.put(('stdout', line.strip()))

    # 读取stderr
    for line in iter(proc.stderr.readline, ''):
        if line:
            q.put(('stderr', line.strip()))

    proc.wait()
    q.put(('done', None))  # 发送结束信号


command = [r"C:\Users\dell\anaconda3\envs\sld\python.exe", r"C:\Users\dell\Projects\CAutoD\wenjian\sldwks.py"]

proc =  subprocess.Popen(
    command,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,          # 输出为字符串
    bufsize=1,          # 行缓冲
    universal_newlines=True
)
print("启动程序了吗")
full_answer = ""
# FILE_PATH = r"C:\Users\dell\Projects\CAutoD\wenjian\logdebug.txt"
# async with open(FILE_PATH, "rb") as f:
#     full_answer = await f.read().decode("utf-8")
# 启动读取线程
read_thread = threading.Thread(
    target=read_subprocess_output,
    args=(proc, output_queue),
    daemon=True
)
read_thread.start()
while True:
    # 非阻塞检查队列（避免阻塞事件循环）
    try:
        # 使用0.1秒超时，既保证实时性又不阻塞事件循环
        stream_type, line = output_queue.get(timeout=0.1)

        if stream_type == 'done':
            break  # 进程结束

        if line:
            print(f"[{stream_type}] {line}")
            # 发送到前端
            # 关键：将字符串中的 \n 转义符替换为真正的换行控制字符
            # chunk = line.replace("\\n", "\n")
            # text_chunk_data = SSETextChunk(text=chunk)
            # sse_chunk = f'event: text_chunk\ndata: {text_chunk_data.model_dump_json()}\n\n'
            # yield sse_chunk
            # await asyncio.sleep(0.05)  # 控制发送速度
    
            # 积累完整回答
            if stream_type == 'stdout':
                full_answer += line + "\n\n"
            else:  # stderr
                full_answer += f"[错误] {line}\n\n"

        output_queue.task_done()

    except queue.Empty:
    # 队列空时检查进程是否已意外终止
        if proc.poll() is not None and not read_thread.is_alive():
            break
        continue