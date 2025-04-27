from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.department import Department
from app.schemas import user as schemas
from app.core.deps import get_current_user, get_admin_user, check_permission
from app.core.security import get_password_hash, verify_password
from app.services.file_storage import FileStorageService
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException, InvalidOperationException
from loguru import logger

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=schemas.UserProfile)
async def get_current_user_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取当前用户资料

    获取当前登录用户的详细资料信息。

    Returns:
        schemas.UserProfile: 当前用户的资料信息。
    """
    # Build role information
    role_ids = [role.id for role in current_user.roles]
    role_names = [role.name for role in current_user.roles]
    
    # Get department name if exists
    department_name = None
    if current_user.department:
        department_name = current_user.department.name
    
    # Create response
    result = schemas.UserProfile(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        avatar=current_user.avatar,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
        department_id=current_user.department_id,
        department_name=department_name,
        role_ids=role_ids,
        role_names=role_names,
        created_at=current_user.created_at,
        last_login=current_user.last_login
    )
    
    return result


@router.put("/profile", response_model=schemas.UserProfile)
async def update_user_profile(
    profile: schemas.UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    更新当前用户资料

    更新当前登录用户的个人资料信息，包括全名、电话和头像 URL。

    Args:
        profile (schemas.UserProfileUpdate): 包含要更新的用户资料字段的请求体。

    Returns:
        schemas.UserProfile: 更新后的用户资料信息。
    """
    # Update user fields
    if profile.full_name is not None:
        current_user.full_name = profile.full_name
    
    if profile.phone is not None:
        current_user.phone = profile.phone
    
    if profile.avatar is not None:
        current_user.avatar = profile.avatar
    
    # Save changes
    db.commit()
    db.refresh(current_user)
    
    # Build response
    role_ids = [role.id for role in current_user.roles]
    role_names = [role.name for role in current_user.roles]
    department_name = current_user.department.name if current_user.department else None
    
    return schemas.UserProfile(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        avatar=current_user.avatar,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
        department_id=current_user.department_id,
        department_name=department_name,
        role_ids=role_ids,
        role_names=role_names,
        created_at=current_user.created_at,
        last_login=current_user.last_login
    )


@router.post("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    上传用户头像

    为当前登录用户上传头像图片。

    Args:
        file (UploadFile): 要上传的头像文件。

    Returns:
        Dict[str, Any]: 包含头像 URL 和缩略图信息的字典。

    Raises:
        HTTPException: 如果上传的文件不是图片。
    """
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )
    
    # Save avatar
    file_service = FileStorageService()
    avatar_info = await file_service.save_avatar(file, current_user.id)
    
    # Update user avatar URL
    current_user.avatar = avatar_info["url"]
    db.commit()
    
    return {"url": avatar_info["url"], "thumbnails": avatar_info.get("thumbnails", {})}


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    password_data: schemas.UserPasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> None:
    """
    修改用户密码

    修改当前登录用户的密码。需要提供当前密码进行验证。

    Args:
        password_data (schemas.UserPasswordChange): 包含当前密码和新密码的请求体。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        HTTPException: 如果当前密码不正确。
    """
    # Verify current password
    if not verify_password(password_data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )
    
    # Update password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    
    logger.info(f"Password changed for user ID {current_user.id}")


@router.get("", response_model=List[schemas.User])
async def get_users(
    skip: int = 0,
    limit: int = 100,
    username: Optional[str] = None,
    email: Optional[str] = None,
    is_active: Optional[bool] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    获取用户列表 (管理员)

    获取系统中的用户列表，支持分页和过滤（按用户名、邮箱、是否激活、部门 ID）。仅管理员可访问。

    Args:
        skip (int): 跳过的记录数 (分页)。
        limit (int): 返回的最大记录数 (分页)。
        username (Optional[str]): 按用户名过滤 (模糊匹配)。
        email (Optional[str]): 按邮箱过滤 (模糊匹配)。
        is_active (Optional[bool]): 按用户激活状态过滤。
        department_id (Optional[int]): 按部门 ID 过滤。

    Returns:
        List[schemas.User]: 用户列表。
    """
    # Build query with filters
    query = db.query(User)
    
    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))
    
    if email:
        query = query.filter(User.email.ilike(f"%{email}%"))
    
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    
    if department_id:
        query = query.filter(User.department_id == department_id)
    
    # Execute query with pagination
    users = query.offset(skip).limit(limit).all()
    
    return users


@router.post("", response_model=schemas.User)
async def create_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建新用户 (管理员)

    在系统中创建一个新用户。仅管理员可访问。

    Args:
        user (schemas.UserCreate): 包含新用户信息的请求体。

    Returns:
        schemas.User: 创建成功的用户信息。

    Raises:
        DuplicateResourceException: 如果用户名或邮箱已存在。
        ResourceNotFoundException: 如果指定的部门 ID 或角色 ID 不存在。
        HTTPException: 数据库操作错误。
    """
    # Check if username exists
    if db.query(User).filter(User.username == user.username).first():
        raise DuplicateResourceException("User", "username", user.username)
    
    # Check if email exists
    if db.query(User).filter(User.email == user.email).first():
        raise DuplicateResourceException("User", "email", user.email)
    
    # Validate department if specified
    if user.department_id and not db.query(Department).filter(Department.id == user.department_id).first():
        raise ResourceNotFoundException("Department", str(user.department_id))
    
    # Create user object
    db_user = User(
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        avatar=user.avatar,
        is_active=user.is_active,
        is_admin=user.is_admin,
        department_id=user.department_id,
        hashed_password=get_password_hash(user.password)
    )
    
    # Add user to database
    db.add(db_user)
    db.flush()  # Flush to get ID but don't commit yet
    
    # Add roles if specified
    if user.role_ids:
        roles = db.query(Role).filter(Role.id.in_(user.role_ids)).all()
        if len(roles) != len(user.role_ids):
            # Some role IDs are invalid
            missing_ids = set(user.role_ids) - {role.id for role in roles}
            db.rollback()
            raise ResourceNotFoundException("Role", str(missing_ids))
        
        db_user.roles = roles
    
    # Commit changes
    try:
        db.commit()
        db.refresh(db_user)
        logger.info(f"User created: {db_user.username} (ID: {db_user.id})")
        return db_user
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Failed to create user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database error while creating user"
        )


@router.get("/{user_id}", response_model=schemas.User)
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    按 ID 获取用户 (管理员)

    根据用户 ID 获取指定用户的详细信息。仅管理员可访问。

    Args:
        user_id (int): 要获取的用户 ID。

    Returns:
        schemas.User: 指定用户的详细信息。

    Raises:
        ResourceNotFoundException: 如果指定的用户 ID 不存在。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ResourceNotFoundException("User", str(user_id))
    
    return user


@router.put("/{user_id}", response_model=schemas.User)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新用户 (管理员)

    根据用户 ID 更新指定用户的资料信息。仅管理员可访问。

    Args:
        user_id (int): 要更新的用户 ID。
        user_update (schemas.UserUpdate): 包含要更新的用户资料字段的请求体。

    Returns:
        schemas.User: 更新后的用户信息。

    Raises:
        ResourceNotFoundException: 如果指定的用户 ID 不存在。
        DuplicateResourceException: 如果更新后的用户名或邮箱已存在。
        InvalidOperationException: 如果尝试将部门设置为其自身的子部门（通过循环引用）。
    """
    # Get user
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise ResourceNotFoundException("User", str(user_id))
    
    # Check for username uniqueness if changing
    if user_update.username and user_update.username != db_user.username:
        if db.query(User).filter(User.username == user_update.username).first():
            raise DuplicateResourceException("User", "username", user_update.username)
        db_user.username = user_update.username
    
    # Check for email uniqueness if changing
    if user_update.email and user_update.email != db_user.email:
        if db.query(User).filter(User.email == user_update.email).first():
            raise DuplicateResourceException("User", "email", user_update.email)
        db_user.email = user_update.email
    
    # Update other fields if provided
    if user_update.full_name is not None:
        db_user.full_name = user_update.full_name
    
    if user_update.phone is not None:
        db_user.phone = user_update.phone
    
    if user_update.is_active is not None:
        db_user.is_active = user_update.is_active
    
    if user_update.department_id is not None:
        if user_update.department_id and not db.query(Department).filter(Department.id == user_update.department_id).first():
            raise ResourceNotFoundException("Department", str(user_update.department_id))
        db_user.department_id = user_update.department_id
    
    if user_update.is_admin is not None:
        db_user.is_admin = user_update.is_admin
    
    # Commit changes
    db.commit()
    db.refresh(db_user)
    
    logger.info(f"User updated: {db_user.username} (ID: {db_user.id})")
    return db_user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    删除用户 (管理员)

    根据用户 ID 删除指定用户。仅管理员可访问。

    Args:
        user_id (int): 要删除的用户 ID。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的用户 ID 不存在。
        InvalidOperationException: 如果尝试删除当前登录用户自己的账户。
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ResourceNotFoundException("User", str(user_id))

    # Prevent self-deletion
    if user.id == current_user.id:
        raise InvalidOperationException("Cannot delete your own account")

    # Delete user
    db.delete(user)
    db.commit()

    logger.info(f"User deleted: {user.username} (ID: {user.id})")


@router.post("/{user_id}/password-reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_password(
    user_id: int,
    password_data: schemas.UserPasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    重置用户密码 (管理员)

    根据用户 ID 重置指定用户的密码。仅管理员可访问。

    Args:
        user_id (int): 要重置密码的用户 ID。
        password_data (schemas.UserPasswordReset): 包含新密码的请求体。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的用户 ID 不存在。
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ResourceNotFoundException("User", str(user_id))
    
    # Update password
    user.hashed_password = get_password_hash(password_data.new_password)
    db.commit()
    
    logger.info(f"Password reset for user: {user.username} (ID: {user.id})")


@router.post("/{user_id}/roles")
async def assign_roles_to_user(
    user_id: int,
    role_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    为用户分配角色 (管理员)

    根据用户 ID 为指定用户分配一个或多个角色。仅管理员可访问。

    Args:
        user_id (int): 要分配角色的用户 ID。
        role_ids (List[int]): 要分配的角色 ID 列表。

    Returns:
        Dict[str, Any]: 包含用户 ID 和分配的角色 ID 列表的字典。

    Raises:
        ResourceNotFoundException: 如果指定的用户 ID 或角色 ID 不存在。
    """
    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ResourceNotFoundException("User", str(user_id))
    
    # Get roles
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
    if len(roles) != len(role_ids):
        # Some role IDs are invalid
        missing_ids = set(role_ids) - {role.id for role in roles}
        raise ResourceNotFoundException("Role", str(missing_ids))
    
    # Update user roles
    user.roles = roles
    db.commit()
    
    logger.info(f"Roles updated for user: {user.username} (ID: {user.id})")
    
    return {"user_id": user.id, "role_ids": [role.id for role in user.roles]}
