import re
from typing import List, Set, Dict, Any
import os
from fastapi import UploadFile

from app.core.exceptions import InvalidFileTypeException, FileTooLargeException
from app.config import settings


def validate_password_strength(password: str) -> bool:
    """
    Validate password strength
    
    Args:
        password: Password to validate
        
    Returns:
        True if password is strong enough, False otherwise
    """
    # Check length
    if len(password) < 8:
        return False
    
    # Check for at least one lowercase letter
    if not re.search(r'[a-z]', password):
        return False
    
    # Check for at least one uppercase letter
    if not re.search(r'[A-Z]', password):
        return False
    
    # Check for at least one digit
    if not re.search(r'\d', password):
        return False
    
    # Check for at least one special character
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    
    return True


def validate_upload_file(
    file: UploadFile, 
    allowed_types: List[str] = None, 
    max_size: int = None
) -> bool:
    """
    Validate uploaded file
    
    Args:
        file: File to validate
        allowed_types: List of allowed MIME types (defaults to common document types)
        max_size: Maximum file size in bytes, defaults to settings.MAX_UPLOAD_SIZE
        
    Returns:
        True if file is valid
        
    Raises:
        InvalidFileTypeException: If file type is not allowed
        FileTooLargeException: If file is too large
    """
    # Default allowed types - common document and media formats
    if allowed_types is None:
        allowed_types = [
            # Documents
            'application/pdf',
            'application/msword',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/vnd.ms-excel',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'text/plain',
            'text/csv',
            'text/html',
            'text/markdown',
            # Images
            'image/jpeg',
            'image/png',
            'image/gif',
            'image/webp',
            'image/svg+xml',
            # Audio
            'audio/mpeg',
            'audio/wav',
            'audio/ogg',
            # Video
            'video/mp4',
            'video/webm',
            'video/quicktime'
        ]
    
    # Validate file type
    if file.content_type not in allowed_types:
        raise InvalidFileTypeException(allowed_types)
    
    # Validate file size
    if not max_size:
        max_size = settings.MAX_UPLOAD_SIZE
    
    # Store file position
    pos = file.file.tell()
    
    # Move to end to get size
    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    
    # Restore position
    file.file.seek(pos)
    
    if size > max_size:
        raise FileTooLargeException(max_size)
    
    return True


def validate_json_structure(data: Dict[str, Any], required_keys: Set[str]) -> bool:
    """
    Validate JSON structure
    
    Args:
        data: JSON data to validate
        required_keys: Set of required keys
        
    Returns:
        True if JSON has all required keys, False otherwise
    """
    return required_keys.issubset(data.keys())


def get_file_extension(filename: str) -> str:
    """
    Get file extension from filename
    
    Args:
        filename: Filename with extension
        
    Returns:
        File extension without dot
    """
    return os.path.splitext(filename)[1][1:].lower()
