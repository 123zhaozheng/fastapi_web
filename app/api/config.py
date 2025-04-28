from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import os

from app.database import get_db
from app.models.user import User
from app.core.deps import get_admin_user
from app.config import settings
from loguru import logger

router = APIRouter(prefix="/config", tags=["Config"])


@router.get("/dify") # Removed response_model
async def get_dify_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Dict[str, Any]: # Updated return type hint
    """
    获取 Dify API 配置 (管理员)

    获取当前系统的 Dify API 配置信息，包括 API URL、显示名称和描述。仅管理员可访问。

    Returns:
        Dict[str, Any]: 包含 Dify API 配置信息的字典。
    """
    # Get config from Redis or settings
    dify_config = {
        "api_url": redis_client.get("dify:api_url") or settings.DIFY_API_BASE_URL,
        "display_name": redis_client.get("dify:display_name") or "Dify AI Platform",
        "description": redis_client.get("dify:description") or "AI chat platform powered by Dify"
    }
    
    return dify_config


@router.put("/dify") # Removed response_model
async def update_dify_config(
    config: Dict[str, Any], # Changed request body type
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Dict[str, Any]: # Updated return type hint
    """
    更新 Dify API 配置 (管理员)

    更新系统的 Dify API 配置信息。可以更新 API URL、显示名称、描述和 API 密钥。仅管理员可访问。

    Args:
        config (Dict[str, Any]): 包含要更新的配置字段的请求体。

    Returns:
        Dict[str, Any]: 包含更新后的 Dify API 配置信息（不包含 API 密钥）的字典。
    """
    # Update Redis config
    if "api_url" in config and config["api_url"] is not None:
        redis_client.set("dify:api_url", config["api_url"])
    
    if "display_name" in config and config["display_name"] is not None:
        redis_client.set("dify:display_name", config["display_name"])
    
    if "description" in config and config["description"] is not None:
        redis_client.set("dify:description", config["description"])
    
    # Update API key if provided (store in environment or secure storage in real app)
    if "api_key" in config and config["api_key"] is not None:
        redis_client.set("dify:api_key", config["api_key"])
        logger.info("Dify API key updated")
    
    logger.info(f"Dify configuration updated by admin {current_user.username}")
    
    # Return updated config (without API key)
    return {
        "api_url": redis_client.get("dify:api_url") or settings.DIFY_API_BASE_URL,
        "display_name": redis_client.get("dify:display_name") or "Dify AI Platform",
        "description": redis_client.get("dify:description") or "AI chat platform powered by Dify"
    }


@router.get("/server-info")
async def get_server_info(
    current_user: User = Depends(get_admin_user)
) -> Dict[str, Any]:
    """
    获取服务器信息 (管理员)

    获取当前服务器的环境信息，包括环境类型、API 版本、数据库信息、Redis 连接状态和版本、Python 版本等。仅管理员可访问。

    Returns:
        Dict[str, Any]: 包含服务器信息的字典。
    """
    # Collect environment info
    info = {
        "environment": os.getenv("ENVIRONMENT", "development"),
        "api_version": "1.0.0",
        "database": {
            "type": "PostgreSQL",
            "version": get_db_version(next(get_db())),
        },
        "redis": {
            "connected": is_redis_connected(),
            "version": get_redis_version(),
        },
        "python_version": os.getenv("PYTHON_VERSION", "3.9+"),
    }
    
    return info


def is_redis_connected() -> bool:
    """Check if Redis is connected"""
    try:
        return redis_client.ping()
    except:
        return False


def get_redis_version() -> str:
    """Get Redis version"""
    try:
        info = redis_client.info()
        return info.get("redis_version", "Unknown")
    except:
        return "Unknown"


def get_db_version(db: Session) -> str:
    """Get database version"""
    try:
        result = db.execute("SELECT version();").scalar()
        return result
    except:
        return "Unknown"
