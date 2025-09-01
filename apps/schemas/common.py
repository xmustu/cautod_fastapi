from pydantic import BaseModel, Field
from typing import Optional

class FileItem(BaseModel):
    """通用文件模型"""
    file_name: str = Field(..., description="文件名")
    file_url: str = Field(..., description="文件的URL")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")



class FileRequest(BaseModel):
    task_id: int
    conversation_id: str
    file_name: str