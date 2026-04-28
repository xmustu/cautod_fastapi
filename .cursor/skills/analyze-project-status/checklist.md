# 项目现状分析检查清单（可复制使用）

> 目的：把“现状分析”做成可重复的流程，避免只输出泛泛建议。

## 1) 项目画像（10 分钟内完成）

- [ ] **语言/框架/运行时**：Python/Node/Java/Go…；FastAPI/Django/Nest/Spring…
- [ ] **入口**：主入口文件/服务启动脚本/容器入口
- [ ] **目录结构**：`apps/`、`core/`、`services/`、`models/`、`routes/` 等是否清晰
- [ ] **外部依赖**：DB/Redis/队列/对象存储/第三方 API/LLM
- [ ] **配置形态**：环境变量、`.env`、配置文件、K8s/Compose secrets

证据建议：
- README/启动脚本/`docker-compose.yml`/依赖清单（`requirements.txt`/`pyproject.toml`/`package.json`）

## 2) 可运行性与开发体验

- [ ] **一键启动**：是否存在明确命令（Makefile / scripts / compose）
- [ ] **环境隔离**：venv/poetry/conda；node 版本管理；容器化
- [ ] **初始化流程**：迁移/建表/seed 数据；首次启动是否会失败
- [ ] **本地与生产差异**：是否有分环境配置；是否能明确切换

风险信号：
- 启动依赖大量“手工步骤”、缺文档、配置散落各处

## 3) 安全基线

### 3.1 鉴权与授权
- [ ] 鉴权机制（JWT/session/OAuth）是否明确
- [ ] 权限模型（RBAC/ABAC）是否落地到路由/服务层
- [ ] Token 生命周期策略（过期/刷新/登出黑名单）

### 3.2 密钥与配置管理
- [ ] **禁止硬编码**：SECRET/KEY/TOKEN/密码不得在代码与文档明文出现
- [ ] secret 轮换机制（至少说明如何替换）
- [ ] 生产环境配置注入方式（env/secrets manager）

### 3.3 Web/API 安全
- [ ] CORS 策略是否最小化
- [ ] CSRF（若有 cookie/session）是否处理
- [ ] 输入校验（schema + 业务校验）与错误回显策略
- [ ] 安全响应头（CSP/HSTS/XFO/XCTO 等）是否合理，Swagger/Docs 是否特殊处理
- [ ] 速率限制/滥用保护（如登录/敏感接口）

### 3.4 依赖与供应链
- [ ] 依赖锁定与更新策略（lockfile/固定版本）
- [ ] 漏洞扫描（pip-audit/npm audit/SCA）是否在 CI

证据建议：
- `core/auth*`、`core/security*`、中间件、配置模块、CI 脚本、安全报告

## 4) 质量基线（可维护性）

- [ ] 测试：单测/集成测试是否存在，是否可运行
- [ ] 代码规范：lint/format（ruff/flake8/black/eslint/prettier）
- [ ] 类型：mypy/pyright/tsc 等（若适用）
- [ ] 错误处理：统一异常、错误码、可观测的失败路径
- [ ] 日志：结构化日志、请求 ID、敏感信息脱敏

风险信号：
- 只有“能跑”，没有质量门禁；或者测试存在但长期失效

## 5) 运维与交付

- [ ] 部署方式：Docker/K8s/脚本/CI-CD
- [ ] 环境分层：dev/staging/prod，是否有一致的变量约定
- [ ] 监控告警：metrics/logs/traces（至少日志可用）
- [ ] 备份恢复（涉及数据时）：策略是否明确

## 6) 文档与治理

- [ ] README：启动、配置、目录说明、常见问题
- [ ] 架构/ADR/路线图：是否与代码一致
- [ ] 安全/合规：安全报告是否“可执行”（对应代码与任务）

## 7) 输出回填（保证可执行）

对每个“风险与问题”至少填：

- 严重度（高/中/低）
- 影响范围（用户/数据/成本/稳定性）
- 证据（文件路径/片段/命令输出摘要）
- 修复建议（可落地步骤）
- Backlog 任务（带验收标准）
