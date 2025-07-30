from tortoise import fields, Model
from tortoise.fields.relational import ForeignKeyRelation

# 用户模型
class Users(Model):
    user_id = fields.IntField(pk=True, auto_increment=True)
    email = fields.CharField(max_length=255, unique=True)
    password_hash = fields.CharField(max_length=255)
    created_at = fields.DatetimeField(auto_now_add=True)

    # 任务关系（可选）
    #tasks: list["Tasks"] = fields.ReverseRelation["Tasks"]

    class Meta:
        table = "users"

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
    task_id = fields.IntField(pk=True)
    conversation = fields.ForeignKeyField(
        "models.Conversations", related_name="tasks", to_field="conversation_id"
    )
    user_id = fields.IntField()
    task_type = fields.CharField(max_length=50)  # 'geometry', 'part_retrieval', 'design_optimization'
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
    geometry_id = fields.IntField(pk=True)
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
    optimization_id = fields.IntField(pk=True)
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
