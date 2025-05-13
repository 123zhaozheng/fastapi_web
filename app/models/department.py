from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.database import Base


class Department(Base):
    """Department model for organizational structure"""
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, index=True, nullable=False)
    description = Column(Text)
    
    # Self-referential relationship for hierarchical structure
    parent_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    parent = relationship("Department", remote_side=[id], backref="children")
    
    # Department manager
    manager_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    manager = relationship("User", foreign_keys=[manager_id], post_update=True)
    
    # Users in this department
    users = relationship("User", back_populates="department", foreign_keys="User.department_id")
    
    # Agent permissions
    agent_permissions = relationship("AgentPermission", back_populates="department", cascade="all, delete-orphan")
    
    # 数字人智能体
    digital_humans = relationship("Agent", back_populates="department", foreign_keys="Agent.department_id")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Department {self.name}>"
