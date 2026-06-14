from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, comment="分组名称")
    sort_order = Column(Integer, default=0, comment="排序权重")
    is_default = Column(Boolean, default=False, comment="是否为默认分组")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Link(Base):
    __tablename__ = "links"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, comment="显示名称")
    url = Column(String(1024), nullable=False, comment="网址")
    group = Column(String(50), default="public", comment="旧分组字段，保留兼容")
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, comment="分组ID")
    sort_order = Column(Integer, default=0, comment="排序权重")
    enabled = Column(Boolean, default=True, comment="是否显示")
    icon = Column(String(255), default="", comment="图标文件名")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    grp = relationship("Group", backref="links", foreign_keys=[group_id])
