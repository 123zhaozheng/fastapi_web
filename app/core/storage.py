# app/core/storage.py

import os
from abc import ABC, abstractmethod
from fastapi import UploadFile, HTTPException
import boto3
from botocore.exceptions import NoCredentialsError
import aiofiles
from loguru import logger
from pathlib import Path

# --- Configuration ---
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")

# 使用 pathlib 动态计算项目根目录下的 uploads 文件夹路径
# Path(__file__) -> 当前文件路径 (D:\...\app\core\storage.py)
# .parent -> app/core
# .parent -> app
# .parent -> 项目根目录 (D:\...\fastapi_web)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOADS_DIR = PROJECT_ROOT / "uploads" # 修正后的路径

os.makedirs(UPLOADS_DIR, exist_ok=True)

# --- S3 Configuration (only if using S3) ---
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
AWS_REGION = os.getenv("AWS_REGION")


class StorageInterface(ABC):
    """定义存储服务的抽象基类接口"""

    @abstractmethod
    async def save(self, file: UploadFile, filename: str) -> str:
        """保存文件并返回文件的可访问 URL"""
        pass

    @abstractmethod
    def get_url(self, filename: str) -> str:
        """获取已存储文件的 URL"""
        pass


class LocalStorage(StorageInterface):
    """本地文件存储实现"""
    def __init__(self, base_path: str, base_url: str = "/static/uploads"):
        self.base_path = base_path
        self.base_url = base_url
        os.makedirs(self.base_path, exist_ok=True)
        logger.info("Using Local Storage.")

    async def save(self, file: UploadFile, filename: str) -> str:
        file_path = os.path.join(self.base_path, filename)
        try:
            async with aiofiles.open(file_path, 'wb') as out_file:
                content = await file.read()
                await out_file.write(content)
            logger.info(f"File '{filename}' saved locally to '{file_path}'.")
            return self.get_url(filename)
        except Exception as e:
            logger.error(f"Failed to save file locally: {e}")
            raise HTTPException(status_code=500, detail=f"Could not save file: {e}")

    def get_url(self, filename: str) -> str:
        return f"/{filename}"


class S3Storage(StorageInterface):
    """S3 对象存储实现"""
    def __init__(self, bucket_name: str, region: str, endpoint_url: str | None, access_key: str, secret_key: str):
        if not all([bucket_name, access_key, secret_key]):
            raise ValueError("S3 bucket name, access key, and secret key must be provided.")
        self.bucket_name = bucket_name
        self.region = region
        self.endpoint_url = endpoint_url
        self.s3_client = boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region
        )
        logger.info(f"Using S3 Storage. Bucket: {self.bucket_name}")

    async def save(self, file: UploadFile, filename: str) -> str:
        try:
            self.s3_client.upload_fileobj(
                file.file,
                self.bucket_name,
                filename
            )
            logger.info(f"File '{filename}' uploaded to S3 bucket '{self.bucket_name}'.")
            return self.get_url(filename)
        except NoCredentialsError:
            logger.error("S3 credentials not available.")
            raise HTTPException(status_code=401, detail="Could not validate credentials for S3")
        except Exception as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise HTTPException(status_code=500, detail=f"Could not upload file to S3: {e}")

    def get_url(self, filename: str) -> str:
        if self.endpoint_url:
            return f"{self.endpoint_url}/{self.bucket_name}/{filename}"
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{filename}"


def get_storage_client() -> StorageInterface:
    """
    存储客户端工厂函数
    根据环境变量 STORAGE_TYPE 返回相应的存储客户端实例
    """
    if STORAGE_TYPE == "s3":
        return S3Storage(
            bucket_name=S3_BUCKET_NAME,
            region=AWS_REGION,
            endpoint_url=S3_ENDPOINT_URL,
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY
        )
    else: # 默认为 local
        # 注意: base_url 可能需要根据您的 FastAPI StaticFiles 配置进行调整
        return LocalStorage(base_path=UPLOADS_DIR, base_url="/static/uploads")

# 在应用启动时创建一个单例的存储客户端
storage_client = get_storage_client() 