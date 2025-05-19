from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

class AgentCategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="分类名称")
    description: Optional[str] = Field(None, description="分类描述")

class AgentCategoryCreate(AgentCategoryBase):
    pass

class AgentCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64, description="分类名称")
    description: Optional[str] = Field(None, description="分类描述")

class AgentCategory(AgentCategoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True