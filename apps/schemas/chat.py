from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel
# 对话消息模型
class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    parts: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = "done" # 新增字段，默认为 'done'

