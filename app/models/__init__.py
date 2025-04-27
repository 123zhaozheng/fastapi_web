# Import models to ensure they are registered with SQLAlchemy
from app.models.user import User
from app.models.role import Role, RoleMenu, RoleButton
from app.models.department import Department
from app.models.menu import Menu, Button
from app.models.agent import Agent, AgentPermission
from app.models.chat import MessageRole, DocumentStatus
# Note: Conversation, Message, and Document models have been removed
# Now using Dify API directly for these features
