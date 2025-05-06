import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Index
from sqlalchemy.orm import relationship

from app.database import Base
from app.models.user import User
from app.models.agent import Agent

# These enums are kept for reference and compatibility with existing code
class MessageRole(str, enum.Enum):
    """Enum for message sender roles"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class DocumentStatus(str, enum.Enum):
    """Enum for document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

# Note: All database models for conversations, messages, and documents
# have been removed as requested. These will be managed directly via
# the Dify API instead of being stored locally in the database.

class Conversation(Base):
    """
    Database model for storing user-agent conversation summaries.
    """
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(64), unique=True, index=True, nullable=False)
    final_query = Column(String(255), nullable=True)  # Ensure length is sufficient for truncated query
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")
    agent = relationship("Agent")

    # Add indexes for foreign keys
    __table_args__ = (
        Index('idx_conversations_user_id', 'user_id'),
        Index('idx_conversations_agent_id', 'agent_id'),
    )
