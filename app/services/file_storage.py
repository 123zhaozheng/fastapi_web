import os
import shutil
from typing import Dict, Any, List
import uuid
from pathlib import Path
from fastapi import UploadFile
from PIL import Image

from app.config import settings
from app.utils.validators import get_file_extension


class FileStorageService:
    """
    Service for handling file storage operations
    """
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or settings.FILE_STORAGE_PATH
        self._ensure_storage_path()
    
    def _ensure_storage_path(self):
        """Ensure storage path exists"""
        os.makedirs(self.storage_path, exist_ok=True)
        
        # Create subdirectories for different file types
        for subdir in ["avatars", "documents", "temp"]:
            os.makedirs(os.path.join(self.storage_path, subdir), exist_ok=True)
    
    async def save_avatar(self, file: UploadFile, user_id: int) -> Dict[str, Any]:
        """
        Save user avatar and generate thumbnails
        
        Args:
            file: Uploaded avatar file
            user_id: User ID
            
        Returns:
            Dictionary with avatar paths and URLs
        """
        # Generate unique filename
        ext = get_file_extension(file.filename)
        filename = f"{user_id}_{uuid.uuid4()}.{ext}"
        avatar_dir = os.path.join(self.storage_path, "avatars")
        file_path = os.path.join(avatar_dir, filename)
        
        # Read file content
        content = await file.read()
        
        # Save original file
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Generate thumbnails if it's an image
        if ext.lower() in ["jpg", "jpeg", "png", "gif"]:
            try:
                thumbnail_paths = self._generate_avatar_thumbnails(file_path, filename)
            except Exception as e:
                # If thumbnail generation fails, still return the original
                thumbnail_paths = {}
        else:
            thumbnail_paths = {}
        
        # Return paths
        result = {
            "filename": filename,
            "path": file_path,
            "url": f"/avatars/{filename}",  # This would be handled by a static file server
            "thumbnails": thumbnail_paths
        }
        
        return result
    
    def _generate_avatar_thumbnails(self, file_path: str, filename: str) -> Dict[str, str]:
        """
        Generate avatar thumbnails of different sizes
        
        Args:
            file_path: Path to the original file
            filename: Filename for thumbnails
            
        Returns:
            Dictionary of thumbnail sizes and paths
        """
        thumbnail_sizes = {
            "small": (48, 48),
            "medium": (96, 96),
            "large": (192, 192)
        }
        
        thumbnail_paths = {}
        base_name, ext = os.path.splitext(filename)
        avatar_dir = os.path.join(self.storage_path, "avatars")
        
        # Open the image
        with Image.open(file_path) as img:
            # Generate thumbnails
            for size_name, dimensions in thumbnail_sizes.items():
                thumb_filename = f"{base_name}_{size_name}{ext}"
                thumb_path = os.path.join(avatar_dir, thumb_filename)
                
                # Create a copy of the image
                thumb_img = img.copy()
                thumb_img.thumbnail(dimensions)
                thumb_img.save(thumb_path)
                
                thumbnail_paths[size_name] = {
                    "path": thumb_path,
                    "url": f"/avatars/{thumb_filename}"
                }
        
        return thumbnail_paths
    
    async def save_document(self, file: UploadFile) -> Dict[str, Any]:
        """
        Save uploaded document
        
        Args:
            file: Uploaded document file
            
        Returns:
            Dictionary with document information
        """
        # Generate unique filename
        ext = get_file_extension(file.filename)
        filename = f"{uuid.uuid4()}.{ext}"
        doc_dir = os.path.join(self.storage_path, "documents")
        file_path = os.path.join(doc_dir, filename)
        
        # Save file
        with open(file_path, "wb") as f:
            # Move file pointer to beginning
            await file.seek(0)
            
            # Save in chunks
            while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                f.write(content)
        
        # Return document info
        return {
            "filename": filename,
            "original_filename": file.filename,
            "mimetype": file.content_type,
            "size": os.path.getsize(file_path),
            "path": file_path
        }
    
    async def save_temp_file(self, file: UploadFile) -> Dict[str, Any]:
        """
        Save a temporary file
        
        Args:
            file: Uploaded file
            
        Returns:
            Dictionary with file information
        """
        # Generate unique filename
        ext = get_file_extension(file.filename)
        filename = f"{uuid.uuid4()}.{ext}"
        temp_dir = os.path.join(self.storage_path, "temp")
        file_path = os.path.join(temp_dir, filename)
        
        # Save file
        with open(file_path, "wb") as f:
            # Move file pointer to beginning
            await file.seek(0)
            
            # Save in chunks
            while content := await file.read(1024 * 1024):  # Read in 1MB chunks
                f.write(content)
        
        # Return file info
        return {
            "filename": filename,
            "original_filename": file.filename,
            "mimetype": file.content_type,
            "size": os.path.getsize(file_path),
            "path": file_path
        }
    
    def delete_file(self, file_path: str) -> bool:
        """
        Delete a file
        
        Args:
            file_path: Path to file to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False
