from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import DateTime

from app.database import Base


class Menu(Base):
    """Menu model for system navigation structure"""
    __tablename__ = "menus"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    path = Column(String(255))
    component = Column(String(255))
    redirect = Column(String(255))
    icon = Column(String(64))
    title = Column(String(64), nullable=False)
    is_hidden = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    
    # Self-referential relationship for hierarchical structure
    parent_id = Column(Integer, ForeignKey("menus.id", ondelete="CASCADE"), nullable=True)
    parent = relationship("Menu", remote_side=[id], backref="children")
    
    # Relationships
    buttons = relationship("Button", back_populates="menu", cascade="all, delete-orphan")
    role_permissions = relationship("RoleMenu", back_populates="menu", cascade="all, delete-orphan")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Menu {self.title}>"


class Button(Base):
    """Button model for action permissions within menus"""
    __tablename__ = "buttons"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(64), nullable=False)
    permission_key = Column(String(255), nullable=False, index=True)
    description = Column(Text)
    icon = Column(String(64))
    sort_order = Column(Integer, default=0)
    
    # Menu relationship
    menu_id = Column(Integer, ForeignKey("menus.id", ondelete="CASCADE"), nullable=False)
    menu = relationship("Menu", back_populates="buttons")
    
    # Permissions relationship
    role_permissions = relationship("RoleButton", back_populates="button", cascade="all, delete-orphan")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Button {self.name}>"
