# 邮件服务配置指南

## 概述

项目已启用完整的邮件发送功能，支持：
- 密码重置邮件
- 邮箱验证邮件
- 新账户创建通知邮件

## 安装依赖

```bash
pip install emails
```

## 配置步骤

### 1. 在 `.env.dev` 或 `.env.prod` 中添加配置

参考 `.env.smtp.example` 文件，添加以下配置：

```env
# 启用邮件发送
EMAILS_ENABLED=True

# SMTP 服务器配置
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=True
SMTP_SSL=False
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password

# 发件人信息
EMAILS_FROM_EMAIL=noreply@cautod.com
EMAILS_FROM_NAME=CAutoD Platform

# 前端地址
FRONTEND_HOST=http://localhost:5173

# Token 有效期
EMAIL_RESET_TOKEN_EXPIRE_HOURS=24
EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS=48

# 项目名称
PROJECT_NAME=CAutoD
```

### 2. 常用邮箱服务商配置

#### Gmail
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_TLS=True
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=app-specific-password
```
**注意**：需要在 Google 账户中生成应用专用密码  
[生成应用密码指南](https://support.google.com/accounts/answer/185833)

#### QQ 邮箱
```env
SMTP_HOST=smtp.qq.com
SMTP_PORT=587  # 或 465
SMTP_TLS=True  # 587端口使用TLS
# SMTP_SSL=True  # 465端口使用SSL
SMTP_USER=your-qq@qq.com
SMTP_PASSWORD=authorization-code
```
**注意**：需要在 QQ 邮箱设置中开启 SMTP 服务并获取授权码

#### 163 邮箱
```env
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_SSL=True
SMTP_USER=your-email@163.com
SMTP_PASSWORD=authorization-code
```

#### Outlook/Hotmail
```env
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_TLS=True
SMTP_USER=your-email@outlook.com
SMTP_PASSWORD=your-password
```

### 3. 开发环境 vs 生产环境

#### 开发环境
建议设置 `EMAILS_ENABLED=False`，邮件内容会打印到日志中而不实际发送：

```env
EMAILS_ENABLED=False
```

#### 生产环境
设置 `EMAILS_ENABLED=True` 并配置正确的 SMTP 信息：

```env
EMAILS_ENABLED=True
SMTP_HOST=smtp.your-provider.com
SMTP_USER=production-email@domain.com
SMTP_PASSWORD=secure-password
```

## 测试邮件发送

### 方法 1: 使用 Swagger UI

1. 启动应用
2. 访问 http://localhost:8080/docs
3. 找到 `/api/auth/password-recovery` 接口
4. 输入一个已注册的邮箱地址
5. 执行请求
6. 检查邮箱是否收到密码重置邮件

### 方法 2: 使用 curl

```bash
curl -X POST "http://localhost:8080/api/auth/password-recovery" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

### 方法 3: 查看邮件 HTML 预览

访问 `/api/auth/password-recovery-html/{email}` 可以预览邮件模板效果（需要登录）

## 邮件模板

邮件模板位于 `templates/email/` 目录：

- `reset_password.html` - 密码重置邮件
- `verify_email.html` - 邮箱验证邮件
- `new_account.html` - 新账户创建邮件
- `test_email.html` - 测试邮件

可以根据需要自定义模板样式和内容。

## 故障排查

### 问题 1: 邮件未发送

**检查清单**：
1. ✅ 是否设置 `EMAILS_ENABLED=True`
2. ✅ 是否安装了 `emails` 库
3. ✅ SMTP 配置是否正确
4. ✅ SMTP 用户名和密码是否正确
5. ✅ 是否使用了应用专用密码（Gmail）或授权码（QQ/163）

**查看日志**：
```bash
# 日志中会显示邮件发送的详细信息
tail -f logs/app.log
```

### 问题 2: 连接超时

检查：
- SMTP 服务器地址是否正确
- 端口是否正确
- 防火墙是否允许 SMTP 连接
- TLS/SSL 设置是否正确

### 问题 3: 认证失败

检查：
- 用户名（通常是完整邮箱地址）
- 密码（应该是应用专用密码或授权码，不是账户登录密码）
- 是否在邮箱服务商处开启了 SMTP 服务

### 问题 4: 邮件进入垃圾箱

建议：
1. 使用专业的邮件服务（如 SendGrid, AWS SES, Mailgun）
2. 配置 SPF、DKIM、DMARC 记录
3. 使用企业邮箱而非个人邮箱
4. 确保发件人地址与 SMTP 账户一致

## 生产环境建议

### 使用专业邮件服务

对于生产环境，建议使用专业的邮件发送服务：

#### SendGrid
```env
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_TLS=True
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
```

#### AWS SES
```env
SMTP_HOST=email-smtp.region.amazonaws.com
SMTP_PORT=587
SMTP_TLS=True
SMTP_USER=your-aws-smtp-user
SMTP_PASSWORD=your-aws-smtp-password
```

#### 阿里云邮件推送
```env
SMTP_HOST=smtpdm.aliyun.com
SMTP_PORT=465
SMTP_SSL=True
SMTP_USER=your-aliyun-smtp-user
SMTP_PASSWORD=your-aliyun-smtp-password
```

### 安全建议

1. **密码安全**：
   - 使用环境变量存储 SMTP 密码
   - 不要将密码提交到版本控制

2. **速率限制**：
   - 对密码重置接口添加速率限制
   - 防止恶意请求

3. **监控**：
   - 监控邮件发送成功率
   - 设置告警机制

4. **日志**：
   - 记录邮件发送日志
   - 定期检查失败原因

## API 接口

相关 API 文档请查看：
- `api_docs/login.md` - 登录认证模块完整文档
- Swagger UI: http://localhost:8080/docs

## 相关文件

- `core/email_utils.py` - 邮件工具模块
- `apps/routes/login.py` - 登录认证路由
- `templates/email/` - 邮件模板目录
- `config.py` - 配置定义
- `.env.smtp.example` - SMTP 配置示例
