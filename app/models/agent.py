from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime, Enum
import enum

from app.database import Base


class AgentPermissionType(str, enum.Enum):
    """Enum for agent permission types"""
    ROLE = "role"
    DEPARTMENT = "department"
    GLOBAL = "global"


class Agent(Base):
    """AI Agent model representing integration with Dify or other AI platforms"""
    __tablename__ = "agents"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, index=True, nullable=False)
    description = Column(Text)
    icon = Column(String(255))
    is_active = Column(Boolean, default=True)
    
    # 数字人相关字段
    is_digital_human = Column(Boolean, default=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    
    # Dify integration settings
    dify_app_id = Column(String(255))
    api_endpoint = Column(String(255))
    api_key = Column(String(255))
    config = Column(JSON)  # Store additional configuration as JSON
    
    # Relationships
    permissions = relationship("AgentPermission", back_populates="agent", cascade="all, delete-orphan")
    department = relationship("Department", foreign_keys=[department_id])
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Agent {self.name}>"


class AgentPermission(Base):
    """Model for agent access permissions"""
    __tablename__ = "agent_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum(AgentPermissionType), nullable=False)
    
    # Optional foreign keys based on permission type
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=True)
    
    # Relationships
    agent = relationship("Agent", back_populates="permissions")
    role = relationship("Role", back_populates="agent_permissions", foreign_keys=[role_id])
    department = relationship("Department", back_populates="agent_permissions", foreign_keys=[department_id])
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<AgentPermission {self.id} - Type: {self.type}>"
