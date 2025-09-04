


def create_log_file():
    log_dir = Path("./logs")
    log_dir.mkdir(parents=True, exist_ok=True)  # 创建目录（若不存在）

    for name in ("app.log", "access.log"):
        (log_dir / name).touch(exist_ok=True)   # 创建空文件（若不存在）