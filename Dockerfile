# 使用多阶段构建来减小最终镜像大小
# 构建阶段
FROM python:3.10-slim as builder
# FROM python:3.13-windowsservercore-ltsc2025 as builder
# 设置工作目录
WORKDIR /app

# 复制所有项目文件
COPY . .

# 安装构建依赖
# RUN sed -i 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' /etc/apt/sources.list \
#     && apt-get update && apt-get install -y --no-install-recommends \
#     gcc \
#     g++ \
#     && rm -rf /var/lib/apt/lists/*

# RUN apt-get update && apt-get install ffmpeg libsm6 libxext6  -y
# 强制安装所有依赖（忽略setup.py中的环境判断）
# RUN pip install --user --no-cache-dir \
#     "cadquery-ocp>=7.8.1,<7.9" \
#     "ezdxf>=1.3.0" \
#     "multimethod>=1.11,<2.0" \
#     "nlopt>=2.9.0,<3.0" \
#     "typish" \
#     "casadi" \
#     "path" \
#     "trame" \
#     "trame-vtk" \
#     "typing_extensions"
# # 进入cadquery目录并安装
# WORKDIR /app/cadquery
# RUN pip install --user --no-cache-dir .

# # 进入cadquery-plugins/plugins/gear_generator目录并安装
# WORKDIR /app/cadquery-plugins/plugins/gear_generator
# RUN pip install --user --no-cache-dir -e .

# 返回到主工作目录
WORKDIR /app

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖到本地目录（排除已安装的cadquery）
RUN pip install --user --no-cache-dir -r requirements.txt

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