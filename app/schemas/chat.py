from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl
from enum import Enum


class MessageRoleEnum(str, Enum):
    """Enum for message sender roles"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class DocumentStatusEnum(str, Enum):
    """Enum for document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ResponseModeEnum(str, Enum):
    """Enum for chat response modes"""
    STREAMING = "streaming"
    BLOCKING = "blocking"


class FileTransferMethodEnum(str, Enum):
    """Enum for file transfer methods"""
    REMOTE_URL = "remote_url"
    LOCAL_FILE = "local_file"


class FileTypeEnum(str, Enum):
    """Enum for supported file types"""
    DOCUMENT = "document"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    CUSTOM = "custom"


# Schema for file in chat request
class ChatFile(BaseModel):
    type: FileTypeEnum
    transfer_method: FileTransferMethodEnum
    url: Optional[HttpUrl] = None
    upload_file_id: Optional[str] = None


# Schema for chat request
class ChatRequest(BaseModel):
    query: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    response_mode: ResponseModeEnum = ResponseModeEnum.STREAMING
    conversation_id: Optional[str] = None
    user: Optional[str] = None
    files: Optional[List[ChatFile]] = None
    auto_generate_name: bool = True


# Schema for deep thinking request
class DeepThinkingRequest(BaseModel):
    query: str
    agent_id: int
    inputs: Dict[str, Any] = Field(default_factory=dict)
    conversation_id: Optional[str] = None
    files: Optional[List[ChatFile]] = None


# Schema for stopping generation
class StopGenerationRequest(BaseModel):
    conversation_id: str
    task_id: str


# Schema for message
class Message(BaseModel):
    message_id: str
    # role: MessageRoleEnum
    content: str
    conversation_id: str # Added based on Dify API response
    query: Optional[str] = None # Added based on Dify API response
    tokens: Optional[int] = None
    # task_id: Optional[str] = None
    # metadata: Optional[Dict[str, Any]] = None
    created_at: datetime
    inputs: Optional[Dict[str, Any]] = None
    message_files: Optional[List[Dict[str, Any]]] = None # Consider defining a more detailed schema for files if needed
    feedback: Optional[Dict[str, Any]] = None # Consider defining a more detailed schema for feedback if needed
    retriever_resources: Optional[List[Dict[str, Any]]] = None # Consider defining a more detailed schema for retriever resources if needed

    class Config:
        from_attributes = True


# Schema for reading conversation data (used in history)
class ConversationRead(BaseModel):
    id: int
    conversation_id: str
    final_query: Optional[str] = None
    user_id: int
    agent_id: int
    created_at: datetime
    updated_at: datetime
    agent_name: Optional[str] = None # Added from relation
    agent_icon: Optional[str] = None # Added from relation

    class Config:
        from_attributes = True


# Schema for chat history search
class ChatHistorySearch(BaseModel):
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    keyword: Optional[str] = None
    agent_id: Optional[int] = None
    page: int = 1
    page_size: int = 20


# Schema for chat history response
class ChatHistoryResponse(BaseModel):
    items: List[ConversationRead] # Updated to use ConversationRead
    total: int
    page: int
    page_size: int
    total_pages: int


# Schema for usage information
class UsageInfo(BaseModel):
    prompt_tokens: int
    prompt_unit_price: str
    prompt_price_unit: str
    prompt_price: str
    completion_tokens: int
    completion_unit_price: str
    completion_price_unit: str
    completion_price: str
    total_tokens: int
    total_price: str
    currency: str
    latency: float


# Schema for retriever resource
class RetrieverResource(BaseModel):
    position: int
    dataset_id: str
    dataset_name: str
    document_id: str
    document_name: str
    segment_id: str
    score: float
    content: str


# Schema for chat completion response
class ChatCompletionResponse(BaseModel):
    event: str
    task_id: str
    id: str
    message_id: str
    conversation_id: str
    mode: str
    answer: str
    metadata: Dict[str, Any]
    usage: UsageInfo
    retriever_resources: List[RetrieverResource] = []
    created_at: int


# Schema for document upload response
class DocumentUploadResponse(BaseModel):
    upload_file_id: str
    filename: str
    size: int
    mimetype: str
    status: str


