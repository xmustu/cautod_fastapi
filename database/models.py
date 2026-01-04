from tortoise import fields, Model
from tortoise.fields.relational import ForeignKeyRelation
from enum import Enum

# 用户角色枚举
class UserRole(str, Enum):
    USER = "user"           # 普通用户
    PREMIUM = "premium"     # 高级用户
    ADMIN = "admin"         # 管理员

# 用户模型
class Users(Model):
    user_id = fields.IntField(pk=True, auto_increment=True)
    username = fields.CharField(max_length=255, unique=True)
    email = fields.CharField(max_length=255, unique=True)
    password_hash = fields.CharField(max_length=255)
    role = fields.CharEnumField(UserRole, default=UserRole.USER, description="用户角色：user-普通用户, premium-高级用户, admin-管理员")
    created_at = fields.DatetimeField(auto_now_add=True)
    #is_activate = fields.BooleanField(default=True)
    #role_id = fields.ForeignKeyField('models.Role', related_name='users',description="用户角色")
    # 任务关系（可选）
    #tasks: list["Tasks"] = fields.ReverseRelation["Tasks"]

    class Meta:
        table = "users"

class Role(Model):
    role_id = fields.IntField(pk=True, auto_increment=True)
    permissions = fields.CharField(max_length=255, default="read,write")
    user_id = fields.IntField(description="用户ID")

    class Meta:
        table = "roles"
# 会话模型
class Conversations(Model):
    conversation_id = fields.CharField(max_length=64, pk=True)
    user_id = fields.IntField()
    title = fields.CharField(max_length=255, default="新会话")
    created_at = fields.DatetimeField(auto_now_add=True)

    # 外部关系（逻辑关联）
    tasks: list["Tasks"] = fields.ReverseRelation["Tasks"]

    class Meta:
        table = "conversations"


# 任务模型
class Tasks(Model):
    task_id = fields.IntField(pk=True, auto_increment=True)
    conversation = fields.ForeignKeyField(
        "models.Conversations", related_name="tasks", to_field="conversation_id", on_delete=fields.CASCADE
    )
    user_id = fields.IntField()
    dify_conversation_id = fields.CharField(max_length=255, null=True)  # Dify 对话 ID
    task_type = fields.CharField(max_length=50)  # 'geometry', 'retrieval', 'optimize'
    status = fields.CharField(max_length=20, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    # 外部关系（逻辑关联）
    user: ForeignKeyRelation[Users] = None  # 逻辑关联
    # conversation: ForeignKeyRelation[Conversations] = None  # 逻辑关联 - This is now handled by the ForeignKeyField
    geometry_result: ForeignKeyRelation["GeometryResults"] = fields.ReverseRelation["GeometryResults"]
    optimization_result: ForeignKeyRelation["OptimizationResults"] = fields.ReverseRelation["OptimizationResults"]
    error_logs: list["ErrorLogs"] = fields.ReverseRelation["ErrorLogs"]

    class Meta:
        table = "tasks"
        #indexes = [
        #    ("idx_conversation_id", ["conversation_id"]),
        #    ("idx_user_id", ["user_id"])
        #]


# 几何建模结果模型
class GeometryResults(Model):
    geometry_id = fields.IntField(pk=True, auto_increment=True)
    task_id = fields.IntField()
    cad_file_path = fields.TextField(null=True)
    code_file_path = fields.TextField(null=True)
    preview_image_path = fields.TextField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    # 外部关系（逻辑关联）
    task: ForeignKeyRelation[Tasks] = None  # 逻辑关联

    class Meta:
        table = "geometry_results"
        #indexes = [("idx_task_id", ["task_id"])]


# 优化结果模型
class OptimizationResults(Model):
    optimization_id = fields.IntField(pk=True, auto_increment=True)
    task_id = fields.IntField()
    optimized_cad_file_path = fields.TextField(null=True)
    best_params = fields.JSONField(null=True)
    final_volume = fields.FloatField(null=True)
    final_stress = fields.FloatField(null=True)
    constraint_satisfied = fields.BooleanField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    # 外部关系（逻辑关联）
    task: ForeignKeyRelation[Tasks] = None  # 逻辑关联

    class Meta:
        table = "optimization_results"
        #indexes = [("idx_task_id", ["task_id"])]


# 错误日志模型
class ErrorLogs(Model):
    error_id = fields.IntField(pk=True, auto_increment=True)
    task_id = fields.IntField()
    error_message = fields.TextField()
    error_type = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    # 外部关系（逻辑关联）
    task: ForeignKeyRelation[Tasks] = None  # 逻辑关联

    class Meta:
        table = "error_logs"
        #indexes = [("idx_task_id", ["task_id"])]


# 系统配置模型（单例模式，只存储一条记录）
class SystemConfig(Model):
    config_id = fields.IntField(pk=True, auto_increment=True)
    max_tasks_per_user = fields.IntField(default=100, description="每个用户最大任务数")
    max_conversations_per_user = fields.IntField(default=50, description="每个用户最大会话数")
    enable_registration = fields.BooleanField(default=True, description="是否启用注册")
    enable_email_verification = fields.BooleanField(default=True, description="是否启用邮箱验证")
    enable_email_notifications = fields.BooleanField(default=True, description="是否启用邮件通知")
    maintenance_mode = fields.BooleanField(default=False, description="是否维护模式")
    max_file_size_mb = fields.IntField(default=100, description="最大上传文件大小(MB)")
    api_rate_limit = fields.IntField(default=100, description="API请求限制(次/分钟)")
    session_timeout_minutes = fields.IntField(default=60, description="会话超时时间(分钟)")
    default_user_role = fields.CharField(max_length=20, default="user", description="默认用户角色")
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "system_config"