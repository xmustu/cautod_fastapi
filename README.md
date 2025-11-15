# CAutoD FastAPI 服务

简体中文 README：本文件说明 `cautod_fastapi` 后端服务的背景、目录结构、技术栈、安装与运行、测试、开发与贡献等信息，帮助开发者快速上手和维护。

## 一、项目背景

CAutoD 是一个面向计算设计/自动化建模的系统，后端使用 FastAPI 提供一系列 API 接口，包含：用户认证、会话（conversation）管理、几何建模任务调度、文件上传/下载、与外部服务（如 Dify）通信、以及与 Celery 的任务队列集成。本仓库 `cautod_fastapi` 是后端服务的实现，负责接收前端请求并协调数据库、Redis、第三方服务与长时任务。

该服务适用于需要将对话式 AI（如 Dify）与 CAD/几何建模流程集成的场景，例如：基于自然语言发起建模任务、异步生成 CAD 文件并提供预览与下载等。

## 二、代码结构（重要目录说明）

仓库目录（本模块位于 `d:\CAutoD\cautod_fastapi`）：

- `main.py` — FastAPI 应用入口，定义 lifespan、挂载静态目录、路由注册、以及 Tortoise ORM 注册。
- `apps/` — 各业务子模块路由：
  - `router.py` — 项目的通用路由（文件上传/下载、会话/任务查询等）。
  - `user.py` — 用户认证、登录/注册、OAuth 回调。
  - `geometry.py` — 与几何建模相关的接口、SSE 流和 Dify client 封装。
  - `optimize.py`、`tasks.py`、`chat.py`、`retrieval.py` 等 — 其它业务逻辑路由。
- `core/` — 核心工具与中间件：鉴权、哈希、日志、请求中间件等。
- `database/` — 数据模型（Tortoise ORM）、数据库/Redis 相关连接与工具。
- `files/` — 应用读写的静态/临时文件目录（模型文件、预览图等）。
- `configs/` — Celery / 配置工具及集成逻辑。
- `test/` — pytest 测试用例与夹具（已包含 `conftest.py` 与若干测试）。
- `uvicorn_config.json`、`requirements.txt`、`pyproject.toml` 等 — 运行与依赖清单。

## 三、技术栈

- Python 3.10+（本仓库在 Conda 环境 `backend` 中测试通过）
- FastAPI — Web 框架
- Uvicorn — ASGI 服务器（开发/部署时使用）
- Tortoise ORM — 异步 ORM（SQLite/MySQL 配置可切换）
- Redis (redis-py asyncio) — 用于会话/消息缓存与短期存储
- Celery — 后台异步任务队列（与 broker/worker 协同）
- httpx / aiohttp — 与外部 HTTP 服务（如 Dify）交互
- Pytest — 单元/集成测试

其他：Jinja2（模板），以及若干常用库（见 `requirements.txt`）。

## 四、快速开始（开发者本地）

建议使用 Conda 创建并激活名为 `backend` 的环境（仓库中测试即在该环境）：

Windows（命令提示符或 PowerShell）示例：

```powershell
git clone https://github.com/xmustu/cautod.git
conda create -n backend python=3.10 -y
conda activate backend
python -m pip install -r d:\CAutoD\cautod_fastapi\requirements.txt
```

或使用现有虚拟环境并安装依赖：

```cmd
cd /d d:\CAutoD\cautod_fastapi
python -m pip install -r requirements.txt
```

运行服务（开发模式）：

```cmd
uvicorn main:app --reload --port 8081
```

配置点：请检查 `config.py` 与 `database/settings.py` 中的配置（数据库、Redis、STATIC_DIR 等）。可通过 `.env.dev` / `.env.prod` 设定环境变量。

## 五、测试

# CAutoD FastAPI 服务

简体中文 README：本文件说明 `cautod_fastapi` 后端服务的背景、目录结构、技术栈、安装与运行、测试、开发与贡献等信息，帮助开发者快速上手和维护。

## 一、项目背景

CAutoD 是一个面向计算设计/自动化建模的系统，后端使用 FastAPI 提供一系列 API 接口，包含：用户认证、会话（conversation）管理、几何建模任务调度、文件上传/下载、与外部服务（如 Dify）通信、以及与 Celery 的任务队列集成。本仓库 `cautod_fastapi` 是后端服务的实现，负责接收前端请求并协调数据库、Redis、第三方服务与长时任务。

该服务适用于需要将对话式 AI（如 Dify）与 CAD/几何建模流程集成的场景，例如：基于自然语言发起建模任务、异步生成 CAD 文件并提供预览与下载等。

## 二、代码结构（重要目录说明）

仓库目录：

- `main.py` — FastAPI 应用入口，定义 lifespan、挂载静态目录、路由注册、以及 Tortoise ORM 注册。
- `apps/` — 各业务子模块路由：
  - `router.py` — 项目的通用路由（文件上传/下载、会话/任务查询等）。
  - `user.py` — 用户认证、登录/注册、OAuth 回调。
  - `geometry.py` — 与几何建模相关的接口、SSE 流和 Dify client 封装。
  - `optimize.py`、`tasks.py`、`chat.py`、`retrieval.py` 等 — 其它业务逻辑路由。
- `core/` — 核心工具与中间件：鉴权、哈希、日志、请求中间件等。
- `database/` — 数据模型（Tortoise ORM）、数据库/Redis 相关连接与工具。
- `files/` — 应用读写的静态/临时文件目录（模型文件、预览图等）。
- `configs/` — Celery / 配置工具及集成逻辑。
- `test/` — pytest 测试用例与夹具（已包含 `conftest.py` 与若干测试）。
- `uvicorn_config.json`、`requirements.txt`、`pyproject.toml` 等 — 运行与依赖清单。

## 三、技术栈

- Python 3.10+（建议使用与项目相同的虚拟环境/Conda 环境）
- FastAPI — Web 框架
- Uvicorn — ASGI 服务器（开发/部署时使用）
- Tortoise ORM — 异步 ORM（SQLite/MySQL 配置可切换）
- Redis (redis-py asyncio) — 用于会话/消息缓存与短期存储
- Celery — 后台异步任务队列（与 broker/worker 协同）
- httpx / aiohttp — 与外部 HTTP 服务（如 Dify）交互
- Pytest — 单元/集成测试

其他：Jinja2（模板），以及若干常用库（见 `requirements.txt`）。

## 四、快速开始（开发者本地）

建议使用虚拟环境或 Conda 创建并激活用于开发的环境：

示例：

```bash
git clone https://github.com/xmustu/cautod.git
cd cautod/cautod_fastapi
python -m venv .venv        # 或者使用 conda create -n backend python=3.10
source .venv/bin/activate   # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
```

运行服务（开发模式）：

```bash
uvicorn main:app --reload --port 8081
```

配置点：请检查 `config.py` 与 `database/settings.py` 中的配置（数据库、Redis、STATIC_DIR 等）。可通过 `.env.dev` / `.env.prod` 设定环境变量。

## 五、测试

项目已包含基础的 pytest 测试用例，放在 `test/` 目录。运行测试：

```bash
cd cautod_fastapi
pytest -q
```

注意：测试使用 `TestClient` 并通过 `conftest.py` 覆盖了外部依赖（如 Redis、鉴权），因此在本地无需启动 Redis 等服务即可运行基本用例。

## 六、开发与调试要点

- 数据库：项目使用 Tortoise ORM。开发时可切换 `settings.SQLMODE` 为 `SQLITE`（默认）或 `MYSQL`。若使用 MySQL，请在 `database/settings.py` 中配置连接字符串。
- 静态文件：应用将 `settings.STATIC_DIR` 挂载到 `settings.STATIC_URL`，并在启动时确保 `files/` 目录存在。
- 第三方服务：与 Dify 的集成在 `apps/geometry.py` 中有 `DifyClient` 的实现，运行集成测试或联调时请确保 Dify API Key 与 Base URL 在 `config.py` 中配置正确。
- 任务队列：Celery 配置位于 `configs/`，若使用 Celery worker，请确保 broker（如 RabbitMQ/Redis）可连通。

## 七、CI / 持续集成（建议）

建议在 CI 中运行以下步骤：

- 使用带缓存的 Python 环境安装依赖
- 运行 `pytest -q`，并在 PR 中阻止测试失败的合并
- 可选：在主分支上执行 lint（flake8/black/isort）、类型检查（mypy）和安全扫描

我可以为你生成一个基础的 GitHub Actions workflow，如果你需要我来添加 CI 文件请回复“添加 CI”。

## 八、贡献者指南

- 提交前请保证本地测试通过（`pytest -q`）
- 新特性或修复请在 feature 分支上开发，提交 PR 请求合并到 `server_dev` 或主分支
- 代码风格建议遵循 `black` 与 PEP8`；可配置 pre-commit 钩子以自动格式化

## 九、常见问题 & 排错

- TemplateNotFound 错误：若在测试或运行中遇到 jinja2 的 `TemplateNotFound`，请确保 `templates/` 目录存在且包含被引用的模板文件；测试套件已避免依赖模板的路由。
- Redis/DB 连接问题：检查环境变量与 `database/settings.py`，在单元测试中我们通过 `conftest.py` 做了连接替身以避免真实连接。

## 十、联系方式

如果需要我帮你：添加 CI、扩展测试覆盖或改进 Dify 集成，请在此 PR 或 issue 中说明优先级，我会接着帮你实现。

