from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime

class Message(BaseModel):
    role: str
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    parts: Optional[List[Dict[str, Any]]] = None
    status: Optional[str] = "done" # 新增字段，默认为 'done'

