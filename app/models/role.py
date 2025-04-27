from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.database import Base

# Association table for role-menu permissions
class RoleMenu(Base):
    """Association model for roles and menus with additional fields"""
    __tablename__ = "role_menu"
    
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    menu_id = Column(Integer, ForeignKey("menus.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    role = relationship("Role", back_populates="menu_permissions")
    menu = relationship("Menu", back_populates="role_permissions")


# Association table for role-button permissions
class RoleButton(Base):
    """Association model for roles and buttons with additional fields"""
    __tablename__ = "role_button"
    
    role_id = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    button_id = Column(Integer, ForeignKey("buttons.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    role = relationship("Role", back_populates="button_permissions")
    button = relationship("Button", back_populates="role_permissions")


class Role(Base):
    """Role model for RBAC system"""
    __tablename__ = "roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), unique=True, index=True, nullable=False)
    description = Column(Text)
    is_default = Column(Boolean, default=False)
    
    # Relationships
    users = relationship("User", secondary="user_role", back_populates="roles")
    menu_permissions = relationship("RoleMenu", back_populates="role", cascade="all, delete-orphan")
    button_permissions = relationship("RoleButton", back_populates="role", cascade="all, delete-orphan")
    agent_permissions = relationship("AgentPermission", back_populates="role", cascade="all, delete-orphan")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Role {self.name}>"
