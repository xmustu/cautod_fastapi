# Authentication & Permissions 架构说明

## 文件定位与职责划分

### `core/authentication.py` - 身份认证层
**核心职责**：验证用户身份（Who you are）

#### 主要功能
1. **JWT Token 管理**
   - 生成 token (`create_token`)
   - 验证 token (`verify_token`)
   
2. **用户身份提取**
   - 从 token 中解析用户信息
   - 从数据库加载完整用户数据
   - 提供给后续权限检查使用

#### 核心函数关系图
```
HTTP Request
    ↓
oauth2_scheme (提取 Authorization header 中的 token)
    ↓
get_current_user(token) → verify_token → 解码 JWT → 从数据库查询用户
    ↓
返回 User(user_id, email, created_at, role)
    ↓
get_current_active_user (可扩展检查用户是否被禁用)
    ↓
传递给路由处理函数或权限依赖项
```

---

### `core/permissions.py` - 权限授权层
**核心职责**：验证用户权限（What you can do）

#### 主要功能
1. **路由级权限控制**（FastAPI 依赖项 - 推荐）
   - `require_admin` - 仅管理员可访问
   - `require_premium_or_admin` - 高级用户或管理员可访问
   - `get_user_with_role` - 获取用户及角色（用于条件逻辑）

2. **业务逻辑权限检查**（PermissionChecker 工具类）
   - `is_admin` / `is_premium_or_admin` - 布尔检查
   - `has_role` / `has_minimum_role` - 角色等级比较
   - `get_user_role` - 获取角色值

---

## 函数依赖关系

### 依赖链路
```
路由端点
    ↓
require_admin / require_premium_or_admin / get_user_with_role
    ↓ (Depends)
get_current_active_user (来自 authentication.py)
    ↓ (Depends)
get_current_user (来自 authentication.py)
    ↓
验证 token → 查询数据库 → 返回 User 对象（含 role 字段）
    ↓
permissions.py 中的函数再次查询数据库获取 UserRole 枚举
    ↓
进行权限验证（抛出 403 或通过）
```

### 为什么 permissions.py 需要再次查询数据库？
虽然 `authentication.py` 已经返回了包含 `role` 字段的 `User` 对象，但：
- `User` 是 Pydantic 模型，`role` 字段是字符串类型
- `permissions.py` 需要与 `UserRole` 枚举进行严格比较
- 为确保数据一致性和类型安全，从数据库重新获取 ORM 模型

**优化建议**：可以考虑在 `User` Pydantic 模型中直接使用 `UserRole` 枚举类型，避免二次查询。

---

## 使用场景对比

### 场景 1: 路由级强制权限（推荐）
**使用 FastAPI 依赖项**

```python
from core.permissions import require_admin

@router.put("/update-role")
async def update_user_role(
    request: UserRoleUpdateRequest,
    current_user: User = Depends(require_admin)  # 自动验证，非管理员抛出 403
):
    # 这里的代码只有管理员能执行
    target_user = await Users.get(user_id=request.user_id)
    target_user.role = request.role
    await target_user.save()
    return {"status": "success"}
```

**优点**：
- 声明式，清晰明了
- 自动集成到 OpenAPI/Swagger 文档
- 非授权用户直接返回 403，代码不会执行

---

### 场景 2: 条件逻辑（根据角色执行不同操作）
**使用 get_user_with_role**

```python
from core.permissions import get_user_with_role

@router.post("/list")
async def get_tasks(
    request_data: TaskListRequest,
    user_info: tuple = Depends(get_user_with_role)
):
    current_user, role = user_info
    
    # 根据角色构建不同的查询
    if role == UserRole.ADMIN:
        tasks_query = Tasks.all()  # 管理员看所有任务
    else:
        tasks_query = Tasks.filter(user_id=current_user.user_id)  # 普通用户只看自己的
    
    tasks = await tasks_query.offset(request_data.offset).limit(request_data.limit)
    return tasks
```

**优点**：
- 灵活处理不同角色的业务逻辑
- 不会直接拦截请求，允许所有登录用户访问

---

### 场景 3: 业务逻辑中的权限检查
**使用 PermissionChecker 工具类**

```python
from core.permissions import PermissionChecker

@router.post("/result_status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_active_user)
):
    # 业务逻辑中检查权限
    is_admin = await PermissionChecker.is_admin(current_user.email)
    
    task = await Tasks.get_or_none(task_id=task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 权限验证：管理员可以查看任何任务，普通用户只能查看自己的
    if not is_admin and task.user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="您没有权限查看此任务")
    
    return task
```

**优点**：
- 细粒度控制
- 可以结合资源所有权检查（如任务归属）
- 返回布尔值，不抛出异常，由业务代码决定如何处理

---

## 最佳实践建议

### 1. 优先使用 FastAPI 依赖项
```python
# ✅ 推荐：清晰、符合 FastAPI 哲学
@router.get("/admin/dashboard", dependencies=[Depends(require_admin)])
async def admin_dashboard():
    return {"data": "..."}

# ❌ 不推荐：手动检查，代码冗余
@router.get("/admin/dashboard")
async def admin_dashboard(current_user: User = Depends(get_current_active_user)):
    user = await Users.get(email=current_user.email)
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="...")
    return {"data": "..."}
```

### 2. 资源所有权检查使用 PermissionChecker
```python
# ✅ 推荐：管理员豁免 + 普通用户所有权检查
is_admin = await PermissionChecker.is_admin(current_user.email)
if not is_admin and resource.user_id != current_user.user_id:
    raise HTTPException(status_code=403, detail="无权访问")
```

### 3. 复杂角色逻辑使用 get_user_with_role
```python
# ✅ 推荐：需要根据角色分支处理时
user_info: tuple = Depends(get_user_with_role)
current_user, role = user_info
```

---

## 当前架构的优化空间

### 问题 1: 重复的数据库查询
**现状**：
- `authentication.py` 查询一次数据库获取 User
- `permissions.py` 再次查询数据库获取 UserRole

**优化方案**：
修改 `authentication.py` 中的 `User` Pydantic 模型：
```python
from database.models import UserRole

class User(BaseModel):
    user_id: int
    email: str
    created_at: datetime
    role: UserRole  # 直接使用枚举而非字符串
```

然后在 `get_current_user` 中：
```python
return User(
    user_id=user_orm.user_id,
    email=user_orm.email,
    created_at=user_orm.created_at,
    role=user_orm.role  # 直接传递枚举
)
```

这样 `permissions.py` 就可以直接使用 `current_user.role` 而无需再次查库。

### 问题 2: 职责边界模糊
**建议**：
- `authentication.py` 只负责"证明你是谁"（token 验证、用户提取）
- `permissions.py` 只负责"检查你能做什么"（角色验证、权限控制）
- 保持两个文件的职责单一，避免相互依赖过深

---

## 总结

| 文件 | 核心职责 | 主要输出 | 使用场景 |
|------|---------|---------|---------|
| `authentication.py` | 身份认证 | `User` 对象（含 role） | 所有需要登录的端点 |
| `permissions.py` | 权限授权 | 403 异常或角色信息 | 需要特定权限的端点 |

**依赖方向**：`permissions.py` 依赖 `authentication.py`（单向依赖，清晰）

**推荐使用模式**：
1. 简单权限控制 → FastAPI 依赖项 (`require_admin`)
2. 条件业务逻辑 → `get_user_with_role`
3. 细粒度检查 → `PermissionChecker` 工具类
