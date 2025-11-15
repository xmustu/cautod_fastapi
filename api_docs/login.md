# apps.routes.login 模块 API 文档

路由前缀：`/api/auth`  （来自 main.py 中 app.include_router(login_router, prefix="/api/auth")）

说明：此文档列出登录认证相关接口，包括 OAuth2 token 登录、密码重置、邮箱验证等功能。

---

## POST /login/access-token
- 方法：POST
- 路由：/login/access-token
- 完整 URL：`/api/auth/login/access-token`
- 描述：OAuth2 兼容的 token 登录接口
- 鉴权：公开
- 请求格式：`application/x-www-form-urlencoded` (OAuth2PasswordRequestForm)
  - username: 用户邮箱（必填）
  - password: 密码（必填）
- 响应模型：Token
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  }
  ```
- 备注：使用邮箱和密码登录，返回 JWT token 用于后续认证

---

## POST /login/test-token
- 方法：POST
- 路由：/login/test-token
- 完整 URL：`/api/auth/login/test-token`
- 描述：测试当前访问令牌是否有效
- 鉴权：需要登录（Bearer Token）
- 响应：
  ```json
  {
    "user_id": 1,
    "email": "user@example.com",
    "role": "user",
    "created_at": "2025-10-24T12:00:00"
  }
  ```
- 备注：用于验证 token 有效性并获取当前用户信息

---

## POST /password-recovery
- 方法：POST
- 路由：/password-recovery
- 完整 URL：`/api/auth/password-recovery`
- 描述：请求密码找回，发送重置邮件
- 鉴权：公开
- 请求模型：PasswordRecoveryRequest
  ```json
  {
    "email": "user@example.com"
  }
  ```
- 响应模型：Message
  ```json
  {
    "message": "If the email exists, a password recovery email has been sent"
  }
  ```
- 备注：
  - 即使邮箱不存在也返回成功（防止邮箱枚举攻击）
  - 重置链接有效期 24 小时

---

## POST /reset-password
- 方法：POST
- 路由：/reset-password
- 完整 URL：`/api/auth/reset-password`
- 描述：使用 token 重置密码
- 鉴权：公开（需要有效的 token）
- 请求模型：NewPassword
  ```json
  {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "new_password": "NewSecurePassword123!"
  }
  ```
- 响应模型：Message
  ```json
  {
    "message": "Password updated successfully"
  }
  ```
- 备注：token 来自密码重置邮件

---

## GET /password-recovery-html/{email}
- 方法：GET
- 路由：/password-recovery-html/{email}
- 完整 URL：`/api/auth/password-recovery-html/{email}`
- 描述：获取密码重置邮件的 HTML 内容预览（仅供测试）
- 鉴权：需要登录
- 路径参数：email (用户邮箱)
- 响应：HTMLResponse（邮件 HTML 内容）
- 备注：开发/测试时用于预览邮件模板效果

---

## POST /send-verification-email
- 方法：POST
- 路由：/send-verification-email
- 完整 URL：`/api/auth/send-verification-email`
- 描述：发送邮箱验证邮件
- 鉴权：需要登录
- 请求：无（使用当前登录用户）
- 响应模型：Message
  ```json
  {
    "message": "Verification email sent"
  }
  ```
- 备注：
  - 需要先登录
  - 验证链接有效期 48 小时

---

## POST /verify-email
- 方法：POST
- 路由：/verify-email
- 完整 URL：`/api/auth/verify-email`
- 描述：验证邮箱
- 鉴权：公开（需要有效的 token）
- 请求模型：EmailVerificationRequest
  ```json
  {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
  ```
- 响应模型：Message
  ```json
  {
    "message": "Email user@example.com verified successfully"
  }
  ```
- 备注：
  - token 来自验证邮件
  - 当前实现为占位功能（数据库模型暂无 email_verified 字段）
  - 如需启用需在 Users 模型添加 `email_verified = fields.BooleanField(default=False)`

---

## GET /verify-email-html/{token}
- 方法：GET
- 路由：/verify-email-html/{token}
- 完整 URL：`/api/auth/verify-email-html/{token}`
- 描述：邮箱验证成功后的展示页面
- 鉴权：公开（需要有效的 token）
- 路径参数：token (验证 token)
- 响应：HTMLResponse（成功或失败的展示页面）
- 备注：用户点击邮件中的验证链接后跳转到此页面

---

## 相关模块

### core/email_utils.py
邮件工具模块，提供：
- `generate_password_reset_token()` - 生成密码重置 token
- `verify_password_reset_token()` - 验证密码重置 token
- `generate_email_verification_token()` - 生成邮箱验证 token
- `verify_email_verification_token()` - 验证邮箱验证 token
- `send_email()` - 发送邮件（当前为模拟实现，需配置 SMTP）
- `render_email_template()` - 渲染邮件模板

### 邮件模板位置
`templates/email/`
- `reset_password.html` - 密码重置邮件模板
- `verify_email.html` - 邮箱验证邮件模板
- `new_account.html` - 新账户创建邮件模板
- `test_email.html` - 测试邮件模板

---

## 配置要求

要启用实际的邮件发送功能，需要在 `config.py` 中添加以下配置：

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # SMTP 邮件服务配置
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_TLS: bool = True
    SMTP_SSL: bool = False
    SMTP_USER: str = "your-email@gmail.com"
    SMTP_PASSWORD: str = "your-app-password"
    EMAILS_FROM_EMAIL: str = "noreply@cautod.com"
    EMAILS_FROM_NAME: str = "CAutoD Platform"
    
    # 前端地址（用于邮件中的链接）
    FRONTEND_HOST: str = "http://localhost:5173"
    
    # Token 有效期
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int = 24
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int = 48
```

并在 `requirements.txt` 中添加：
```
emails
```

---

## 使用示例

### 1. 登录获取 token
```bash
curl -X POST "http://localhost:8080/api/auth/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=yourpassword"
```

### 2. 使用 token 访问受保护接口
```bash
curl -X GET "http://localhost:8080/api/user/me" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 3. 请求密码重置
```bash
curl -X POST "http://localhost:8080/api/auth/password-recovery" \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

### 4. 重置密码
```bash
curl -X POST "http://localhost:8080/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "new_password": "NewSecurePassword123!"
  }'
```

---

## 安全提示

1. **HTTPS**: 生产环境必须使用 HTTPS
2. **密码强度**: 建议添加密码强度验证
3. **速率限制**: 建议对登录和密码重置接口添加速率限制
4. **Token 过期**: 已实现 token 过期机制
5. **敏感信息**: 邮件中不要包含明文密码（除新账户创建邮件外）
