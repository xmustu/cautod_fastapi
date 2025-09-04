import asyncio
# 定义一个异步的生成器
async def generator(name):
    for i in range(3):
        print(f"【{name}】-开始异步操作: {i},协程挂起2s")
        await asyncio.sleep(3)  # 这里模拟异步耗时操作（比如文件io，网络读取等），协程挂起3s
        print(f"【{name}】-异步操作完成，生成: {i}")
        yield i
 
# 定义一个异步函数来处理生成器
async def process_generator(name):
    # 进入协程处理
    print(f"【{name}】进入协程处理:")
    # 如果是普通的for循环，是同步执行，会在协程中全部执行完毕，再进入到后续处理
    # for item in range(0,2):
    #    print(f'【{name}】普通的生成器：{item}')
 
    # async for:异步迭代的语法，它允许你以异步的方式遍历异步迭代器。
    async for item in generator(name):
        yield print(f"【{name}】协程处理继续: 生成{item}")
        print(f"【{name}】协程处理继续: 即将进入下一个生成")
 
# 主函数
async def main_process():
    print('【主协程】进入main处理')
    print('【主协程】生成 协程 task1')
    task1 = asyncio.create_task(process_generator('task1')) #生成一个新的协程
    print('【主协程】生成 协程 task2')
    task2 = asyncio.create_task(process_generator('task2')) #生成一个新的协程
    print('【主协程】生成 协程 task3')
    task3 = asyncio.create_task(process_generator('task3')) #生成一个新的协程
 
    # 获取当前事件循环中的所有任务
    tasks = asyncio.all_tasks()
    print(f"【主协程】当前事件循环中有 {len(tasks)} 个任务（一个主协程+3个task协程）")
    # 等待所有任务完成
    print(f"【主协程】挂起，等待task1完成")
    yield await task1
    print(f"【主协程】挂起，等待task2完成")
    yield await task2
    print(f"【主协程】挂起，等待task3完成")
    yield await task3
    print('【主协程】全部完成')
 
# 启动事件循环(该事件循环用于协调所有协程的运行)，运行一个协程，执行main_process函数
asyncio.run(main_process())