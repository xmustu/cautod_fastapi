from tortoise.models import Model
from tortoise import fields

class User(Model):

    __tablename__ = "users"

    user_id = fields.IntField(pk=True)
    name = fields.CharField(max_length=256, description="昵称")
    password_hash = fields.CharField(max_length=256, description="密码")
    created_at = fields.TimeField(description="注册时间")