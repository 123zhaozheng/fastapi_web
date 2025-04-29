from loguru import logger
from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.database import get_db
from app.models.user import User
from app.schemas.token import TokenPayload
from app.core.security import SECRET_KEY
from app.services.dify import DifyService

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"/api/auth/login/form") # Corrected URL for form-based login


def get_dify_service() -> DifyService:
    """
    Dependency to get Dify service
    
    Returns:
        DifyService instance
    """
    return DifyService()


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Get the current authenticated user
    """
    logger.debug("Entering get_current_user")
    try:
        # Log the received token (partially for security)
        token_start = token[:10] if token else "None"
        token_end = token[-10:] if token and len(token) > 20 else ""
        logger.debug(f"Received token: {token_start}...{token_end}")

        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        logger.debug(f"Decoded payload: {payload}") # Log decoded payload
        token_data = TokenPayload(**payload)
        logger.debug(f"Validated token data: {token_data}")
    except (JWTError, ValidationError) as e:
        logger.error(f"Token validation failed: {e}") # Log validation error
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法验证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug(f"Attempting to fetch user with ID: {token_data.sub}")
    user = db.query(User).filter(User.id == token_data.sub).first()
    logger.debug(f"Database query result for user ID {token_data.sub}: {'User found' if user else 'User not found'}")

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户未找到",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户未激活",
        )

    logger.debug(f"Exiting get_current_user with user: {user.id if user else 'None'}")
    return user


def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current active user (alias for get_current_user for clarity)
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User model instance
    """
    return current_user


def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Get the current admin user
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        User model instance if user is admin
        
    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户权限不足",
        )
    
    return current_user


def check_permission(
    permission_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> bool:
    """
    Check if user has specific button permission
    
    Args:
        permission_key: Button permission key to check
        db: Database session
        current_user: Current authenticated user
        
    Returns:
        True if user has permission, False otherwise
        
    Raises:
        HTTPException: If user doesn't have the permission
    """
    if current_user.is_admin:
        return True
    
    # Check if user has any role with this permission
    has_permission = False
    for role in current_user.roles:
        for button_perm in role.button_permissions:
            if button_perm.button.permission_key == permission_key:
                has_permission = True
                break
        if has_permission:
            break
    
    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"用户缺少权限: {permission_key}",
        )
    
    return True
