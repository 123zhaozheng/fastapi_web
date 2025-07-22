from datetime import datetime, timedelta
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.token import Token, RefreshToken
from app.schemas.user import UserLogin
from app.schemas.response import UnifiedResponseSingle
from app.core.security import (
    create_access_token,
    create_refresh_token,
    verify_password,
    get_password_hash,
    generate_secure_token,
)
from app.core.exceptions import InvalidCredentialsException
from jose import jwt, JWTError
from app.core.security import SECRET_KEY
from loguru import logger
from app.services.oa_sso import OASsoService, OASsoException
from app.models.role import Role
from app.config import settings
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token)
async def login(
    user_credentials: UserLogin,
    db: Session = Depends(get_db)
) -> Any:
    """
    用户登录接口 (JSON)

    通过用户名和密码进行身份验证，成功后返回访问令牌和刷新令牌。

    Args:
        user_credentials (UserLogin): 包含用户名和密码的请求体。
        db (Session): 数据库会话依赖。

    Returns:
        UnifiedResponseSingle[Token]: 包含访问令牌、刷新令牌和令牌类型的统一返回对象。

    Raises:
        InvalidCredentialsException: 如果提供的凭据无效或用户账户被禁用。
    """
    # Authenticate user
    user = db.query(User).filter(User.username == user_credentials.username).first()
    
    # 解码密码
    decoded_password = user_credentials.get_decoded_password()
    
    if not user or not verify_password(decoded_password, user.hashed_password):
        logger.warning(f"Login failed: Invalid credentials for user {user_credentials.username}")
        # 使用 exceptions.py 中定义的默认中文消息 "用户名或密码错误"
        raise InvalidCredentialsException()
    
    if not user.is_active:
        logger.warning(f"Login failed: Inactive user {user_credentials.username}")
        raise InvalidCredentialsException("账户已被禁用")
    
    # Update last login timestamp
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    logger.info(f"User {user.username} logged in successfully")
    
    result = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }
    
    return result


@router.post("/login/form", response_model=Token)
async def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> Any:
    """
    用户登录接口 (表单)

    通过 OAuth2 兼容的表单数据（用户名和密码）进行身份验证，成功后返回访问令牌和刷新令牌。

    Args:
        form_data (OAuth2PasswordRequestForm): 包含用户名和密码的表单数据依赖。
        db (Session): 数据库会话依赖。

    Returns:
        Token: 包含访问令牌、刷新令牌和令牌类型的统一返回对象。

    Raises:
        InvalidCredentialsException: 如果提供的凭据无效或用户账户被禁用。
    """
    logger.debug(f"Entering login_form for user: {form_data.username}")

    # Authenticate user
    logger.debug(f"Executing database query for user: {form_data.username}")
    user = db.query(User).filter(User.username == form_data.username).first()
    logger.debug(f"Database query result for user {form_data.username}: {'User found' if user else 'User not found'}")

    if not user or not verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Login failed: Invalid credentials for user {form_data.username}")
        # 使用 exceptions.py 中定义的默认中文消息 "用户名或密码错误"
        raise InvalidCredentialsException()

    if not user.is_active:
        logger.warning(f"Login failed: Inactive user {form_data.username}")
        raise InvalidCredentialsException("账户已被禁用")

    # Update last login timestamp
    user.last_login = datetime.utcnow()
    db.commit()
    logger.debug(f"Database commit successful for user: {user.username}")

    # Generate tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    logger.info(f"User {user.username} logged in successfully via form")
    logger.debug(f"Exiting login_form for user: {user.username}")

    result = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }
    
    return result


@router.post("/refresh", response_model=Token)
async def refresh_token_endpoint(
    refresh_token_data: RefreshToken,
    db: Session = Depends(get_db)
) -> Any:
    """
    刷新访问令牌接口

    使用有效的刷新令牌获取新的访问令牌和刷新令牌。

    Args:
        refresh_token_data (RefreshToken): 包含刷新令牌的请求体。
        db (Session): 数据库会话依赖。

    Returns:
        UnifiedResponseSingle[Token]: 包含新的访问令牌、刷新令牌和令牌类型的统一返回对象。

    Raises:
        HTTPException: 如果提供的刷新令牌无效或已过期。
    """
    try:
        # Decode refresh token
        payload = jwt.decode(
            refresh_token_data.refresh_token,
            SECRET_KEY,
            algorithms=["HS256"]
        )
        
        # Validate token type and expiration
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user ID from token
        user_id = int(payload.get("sub"))
        
        # Get user from database
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的刷新令牌或用户未激活",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Generate new tokens
        new_access_token = create_access_token(user.id)
        new_refresh_token = create_refresh_token(user.id)
        
        logger.info(f"Tokens refreshed for user {user.username}")
        
        result = {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }
        
        return result
        
    except JWTError:
        logger.warning("Token refresh failed: Invalid refresh token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/login/oa-sso", response_model=Token)
async def oa_sso_login(
    token_data: dict,  # expecting {"token": "..."}
    db: Session = Depends(get_db)
) -> Any:
    """OA SSO 登录接口

    前端提供 OA 颁发的 token，后端加密后调用 OA SSO 接口获取工号 (workcode)。
    如果工号对应的用户不存在，则自动创建。
    """
    token = token_data.get("token") if isinstance(token_data, dict) else None
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token 不能为空")

    sso_service = OASsoService()
    try:
        workcode = await sso_service.get_workcode(token)
    except OASsoException as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    finally:
        await sso_service.close()

    # Find or create user
    user = db.query(User).filter(User.username == workcode).first()
    if not user:
        # Auto-create user with placeholder values
        random_password = settings.DEFAULT_RESET_PASSWORD
        user = User(
            username=workcode,
            email=f"{workcode}@ksrcb.com",
            hashed_password=get_password_hash(random_password),
            full_name=workcode,
            is_active=True
        )

        # Assign default roles
        default_roles = db.query(Role).filter(Role.is_default == True).all()
        if default_roles:
            user.roles = default_roles
        db.add(user)
        db.commit()
        db.refresh(user)

    # Update last_login
    user.last_login = datetime.utcnow()
    db.commit()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }
