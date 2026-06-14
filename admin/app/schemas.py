from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    password: str


class GroupCreate(BaseModel):
    name: str
    sort_order: Optional[int] = 0
    is_default: Optional[bool] = False


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_default: Optional[bool] = None


class GroupOut(BaseModel):
    id: int
    name: str
    sort_order: int
    is_default: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class LinkCreate(BaseModel):
    url: str
    title: Optional[str] = None
    group_id: int = 1
    icon: str = ""


class LinkUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    group_id: Optional[int] = None
    sort_order: Optional[int] = None
    enabled: Optional[bool] = None
    icon: Optional[str] = None


class LinkOut(BaseModel):
    id: int
    title: str
    url: str
    group_id: Optional[int] = None
    icon: str
    sort_order: int
    enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem]
