from pydantic import BaseModel
from typing import List, Optional
import datetime

class TaskOut(BaseModel):
    task_id: int
    task_type: str
    status: str
    created_at: datetime.datetime
    
    # The frontend TaskItem component also uses a 'summary' field, which is not in the Tasks model.
    # This might need to be addressed later if the summary is missing in the UI.
    # For now, focusing on the fields the user reported as missing.
    
    class Config:
        orm_mode = True

class ConversationOut(BaseModel):
    conversation_id: str
    user_id: int
    title: str
    created_at: datetime.datetime
    tasks: List[TaskOut] = []

    class Config:
        orm_mode = True
