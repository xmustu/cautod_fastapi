# 使用多阶段构建来减小最终镜像大小
# 构建阶段
FROM python:3.10-slim as builder

# 设置工作目录
WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖到本地目录
RUN pip install --user --no-cache-dir -r requirements.txt && \
    pip install --user --no-cache-dir git+https://github.com/CadQuery/cadquery.git && \
    pip install --user --no-cache-dir -e "git+https://github.com/CadQuery/cadquery-plugins.git#egg=gear_generator&subdirectory=plugins/gear_generator"

# 生产阶段
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    ENVIRONMENT=production

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的Python包
COPY --from=builder /root/.local /root/.local

# 确保脚本可以找到已安装的包
ENV PATH=/root/.local/bin:$PATH

# 复制项目文件
COPY . .

# 替换gear_generator插件的main.py文件
RUN cp api/main.py src/gear-generator/plugins/gear_generator/gear_generator/main.py

# 创建必要的目录和文件
RUN mkdir -p files logs migrations && \
    touch logs/app.log logs/access.log && \
    chmod 755 logs && \
    chmod 644 logs/*.log

# 暴露端口
EXPOSE 8080

# 健康检查
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/docs || exit 1

# 启动命令 - 适配生产环境
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--log-config", "uvicorn_config.json", "--workers", "4"]
