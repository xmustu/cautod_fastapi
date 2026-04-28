# 用户注册改进方案文档

## 📋 概述

本文档说明了用户注册系统的改进方案,包含用户名、密码、邮箱的完整验证规则和最佳实践。

---

## 🔐 改进内容

### 1. **用户名验证**

#### 验证规则
- ✅ **长度限制**: 3-50个字符
- ✅ **字符限制**: 仅允许字母、数字、下划线、中文
- ✅ **格式限制**: 不允许纯数字用户名
- ✅ **保留名称**: 禁止使用 `admin`, `root`, `system`, `test`, `guest` 等
- ✅ **自动处理**: 去除首尾空格
- ✅ **唯一性检查**: 防止重复注册

#### 示例
```python
# ✅ 有效的用户名
"alice"
"alice123"
"alice_bob"
"张三"
"user_王小明"

# ❌ 无效的用户名
"ab"              # 太短
"user@name"       # 包含特殊字符
"123456"          # 纯数字
"admin"           # 保留名称
"user name"       # 包含空格
```

---

### 2. **密码验证**

#### 验证规则
- ✅ **长度限制**: 8-128个字符
- ✅ **大写字母**: 至少1个 (A-Z)
- ✅ **小写字母**: 至少1个 (a-z)
- ✅ **数字**: 至少1个 (0-9)
- ✅ **特殊字符**: 至少1个 (!@#$%^&*等)
- ✅ **弱密码检测**: 防止常见弱密码
- ✅ **连续字符检测**: 禁止123、abc等连续字符

#### 示例
```python
# ✅ 有效的密码
"SecurePass123!"
"MyP@ssw0rd"
"C0mpl3x!Pass"

# ❌ 无效的密码
"Pass1!"           # 太短
"password123!"     # 无大写字母
"PASSWORD123!"     # 无小写字母
"SecurePass!"      # 无数字
"SecurePass123"    # 无特殊字符
"Password123!"     # 常见弱密码
"Pass123word!"     # 包含连续字符
```

#### 安全建议
```
推荐密码示例:
- MyP@ssw0rd2025
- Secure!P4ssW0rd
- C0mpl3x&St0ng!
- 2025@MySecureP@ss

避免使用:
- 生日、姓名等个人信息
- 连续字符(123、abc)
- 键盘排列(qwerty)
- 常见单词(password)
```

---

### 3. **邮箱验证**

#### 验证规则
- ✅ **格式验证**: 使用 Pydantic `EmailStr` 进行标准邮箱格式验证
- ✅ **唯一性检查**: 防止重复注册
- ✅ **自动处理**: 统一转换为小写存储
- ⚠️ **建议扩展**: 邮箱验证码确认(防止恶意注册)

#### 示例
```python
# ✅ 有效的邮箱
"user@example.com"
"test.user@example.com"
"user+tag@example.co.uk"

# ❌ 无效的邮箱
"notanemail"
"@example.com"
"user@"
"user space@example.com"
```

---

## 🚀 使用方法

### 方式1: 使用改进的Schema (推荐)

```python
from apps.schemas.user_improved import UserRegisterRequest
from fastapi import HTTPException, status

@app.post("/register")
async def register(request: UserRegisterRequest):
    # Pydantic会自动验证所有字段
    # 如果验证失败,会自动返回422错误和详细的错误信息
    
    # 检查用户名是否存在
    if await Users.filter(username=request.username).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "username_exists", "message": "该用户名已被注册"}
        )
    
    # 检查邮箱是否存在
    if await Users.filter(email=request.email).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "email_exists", "message": "该邮箱已被注册"}
        )
    
    # 创建用户
    hashed_password = Hasher.get_password_hash(request.password)
    user = await Users.create(
        username=request.username.strip(),
        email=request.email.lower(),
        password_hash=hashed_password
    )
    
    return {"status": "success", "user_id": user.user_id}
```

### 方式2: 直接使用改进的路由

```python
# 在 main.py 中引入改进的路由
from apps.routes.user_improved import user as user_improved

app.include_router(
    user_improved,
    prefix="/api/v2/users",  # 使用新的版本路径
    tags=["users-v2"]
)
```

---

## 📝 API接口

### 1. 用户注册

```http
POST /api/v2/users/register
Content-Type: application/json

{
  "username": "alice_wang",
  "email": "alice@example.com",
  "password": "SecurePass123!"
}
```

**成功响应 (200)**:
```json
{
  "user_id": 1,
  "username": "alice_wang",
  "email": "alice@example.com",
  "role": "user",
  "created_at": "2025-11-11T10:00:00Z"
}
```

**失败响应 (422)** - 验证错误:
```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "password"],
      "msg": "密码必须包含至少一个大写字母",
      "input": "password123!"
    }
  ]
}
```

**失败响应 (400)** - 用户名已存在:
```json
{
  "detail": {
    "error": "username_exists",
    "message": "该用户名已被注册",
    "field": "username"
  }
}
```

### 2. 用户登录

```http
POST /api/v2/users/login
Content-Type: application/json

{
  "email": "alice@example.com",
  "password": "SecurePass123!"
}
```

**成功响应 (200)**:
```json
{
  "status": "success",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "user_id": 1,
    "username": "alice_wang",
    "email": "alice@example.com",
    "role": "user"
  }
}
```

### 3. 修改密码

```http
PUT /api/v2/users/change-password
Authorization: Bearer <token>
Content-Type: application/json

{
  "old_password": "SecurePass123!",
  "new_password": "NewSecure456@"
}
```

---

## 🧪 测试

运行单元测试:

```bash
# 安装pytest
pip install pytest

# 运行测试
cd cautod_fastapi
pytest test/test_user_registration.py -v
```

测试覆盖:
- ✅ 用户名验证 (长度、格式、保留名)
- ✅ 密码验证 (长度、复杂度、弱密码)
- ✅ 邮箱验证 (格式)

---

## 🔧 集成到现有系统

### 步骤1: 安装依赖

```bash
pip install pydantic[email]
```

### 步骤2: 更新Schema文件

将 `user_improved.py` 的内容替换到现有的 `apps/schemas/user.py`:

```python
# apps/schemas/user.py
from apps.schemas.user_improved import *
```

### 步骤3: 更新路由

选择以下方式之一:

**方式A: 完全替换**
```python
# 将 user_improved.py 重命名为 user.py
mv apps/routes/user_improved.py apps/routes/user.py
```

**方式B: 共存使用**
```python
# main.py
from apps.routes.user import user  # 旧版本
from apps.routes.user_improved import user as user_v2  # 新版本

app.include_router(user, prefix="/api/v1/users", tags=["users-v1"])
app.include_router(user_v2, prefix="/api/v2/users", tags=["users-v2"])
```

### 步骤4: 数据库迁移(如需要)

如果需要对现有数据进行清理:

```python
# 脚本: cleanup_usernames.py
from database.models import Users

async def cleanup_usernames():
    """清理现有用户名(去除空格)"""
    users = await Users.all()
    for user in users:
        cleaned = user.username.strip()
        if cleaned != user.username:
            user.username = cleaned
            await user.save()
    print(f"清理完成,共处理 {len(users)} 个用户")
```

---

## 📊 对比

| 项目 | 旧版本 | 改进版 |
|------|--------|--------|
| **用户名验证** | 仅检查是否存在 | 长度/格式/保留名检查 |
| **密码验证** | 无限制 | 强密码策略(8位+大小写+数字+特殊字符) |
| **邮箱验证** | 基本格式检查 | EmailStr标准验证 |
| **输入方式** | Form表单 | Pydantic模型 |
| **错误提示** | 简单文本 | 结构化JSON,包含错误类型和字段 |
| **数据清理** | 无 | 自动去空格、统一小写 |
| **安全性** | 中 | 高 |

---

## ⚠️ 注意事项

1. **密码复杂度可能影响用户体验**
   - 建议在前端显示密码强度提示
   - 提供"显示密码"功能
   - 实时验证反馈

2. **保留用户名列表需定期更新**
   ```python
   reserved_usernames = [
       'admin', 'root', 'system', 'test', 'guest',
       'administrator', 'moderator', 'support'
   ]
   ```

3. **邮箱验证建议扩展**
   - 发送验证码
   - 防止临时邮箱
   - 限制注册频率

4. **性能考虑**
   - 用户名/邮箱存在性检查建议添加数据库索引
   - 密码哈希使用bcrypt(已在Hasher中实现)

---

## 🎯 未来扩展

### 1. 邮箱验证码
```python
from fastapi import BackgroundTasks
import random

async def send_verification_email(email: str, code: str):
    # 发送验证码邮件
    pass

@app.post("/register")
async def register(request: UserRegisterRequest, bg_tasks: BackgroundTasks):
    # 生成验证码
    code = str(random.randint(100000, 999999))
    
    # 异步发送邮件
    bg_tasks.add_task(send_verification_email, request.email, code)
    
    # 暂存用户信息(Redis),等待验证
    # ...
```

### 2. 密码找回功能
```python
@app.post("/forgot-password")
async def forgot_password(email: EmailStr):
    # 发送重置密码链接
    pass
```

### 3. 第三方登录集成
```python
# 已有GitHub/Google OAuth,可继续扩展
# - 微信登录
# - QQ登录
# - 企业微信
```

### 4. 多因素认证(2FA)
```python
# 使用TOTP(Time-based One-Time Password)
import pyotp

@app.post("/enable-2fa")
async def enable_2fa(current_user: User = Depends(get_current_active_user)):
    secret = pyotp.random_base32()
    # 存储secret到用户表
    # 返回QR码供用户扫描
    pass
```

---

## 📞 支持

如有问题,请:
1. 查看单元测试示例
2. 检查错误日志
3. 参考FastAPI官方文档
4. 查看Pydantic验证文档

---

## 📜 许可

本改进方案遵循项目原有许可协议。
