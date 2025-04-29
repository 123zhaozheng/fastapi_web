from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.role import Role, RoleMenu, RoleButton
from app.models.menu import Menu, Button
from app.models.user import User
from app.schemas import role as schemas
from app.schemas import user as user_schemas
from app.schemas.response import UnifiedResponseSingle, UnifiedResponsePaginated
from app.core.deps import get_current_user, get_admin_user
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException, InvalidOperationException
from loguru import logger

router = APIRouter(prefix="/roles", tags=["Roles"])


@router.get("", response_model=UnifiedResponsePaginated[schemas.Role])
async def get_roles(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    获取角色列表 (管理员，分页，按更新日期倒序)

    获取系统中的角色列表，支持分页和按名称过滤。仅管理员可访问。

    Args:
        page (int): 页码，从1开始。
        page_size (int): 每页返回的数量。
        name (Optional[str]): 按角色名称过滤 (模糊匹配)。

    Returns:
        UnifiedResponsePaginated[schemas.Role]: 包含角色列表和分页信息的统一返回对象。
    """
    # Build query with filters
    query = db.query(Role)
    
    if name:
        query = query.filter(Role.name.ilike(f"%{name}%"))
    
    # 计算 skip
    skip = (page - 1) * page_size

    # Get total count before pagination
    total_count = query.count()

    # Execute query with pagination and sorting
    roles = query.order_by(Role.updated_at.desc()).offset(skip).limit(page_size).all() # Added sorting

    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    # Return data in UnifiedResponsePaginated format
    return UnifiedResponsePaginated(
        data=roles,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("", response_model=UnifiedResponseSingle[schemas.Role])
async def create_role(
    role: schemas.RoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建新角色 (管理员)

    在系统中创建一个新角色，并可选择性地为其分配菜单和按钮权限。仅管理员可访问。

    Args:
        role (schemas.RoleCreate): 包含新角色信息和权限 ID 列表的请求体。

    Returns:
        UnifiedResponseSingle[schemas.Role]: 包含创建成功的角色信息的统一返回对象。

    Raises:
        DuplicateResourceException: 如果角色名称已存在。
        ResourceNotFoundException: 如果指定的菜单 ID 或按钮 ID 不存在。
        HTTPException: 数据库操作错误。
    """
    # Check if role name exists
    if db.query(Role).filter(Role.name == role.name).first():
        raise DuplicateResourceException("角色", "name", role.name)
    
    # Create role object
    db_role = Role(
        name=role.name,
        description=role.description,
        is_default=role.is_default
    )
    
    # Add role to database
    db.add(db_role)
    db.flush()  # Flush to get ID but don't commit yet
    
    # Add menu permissions if specified
    if role.menu_ids:
        menus = db.query(Menu).filter(Menu.id.in_(role.menu_ids)).all()
        if len(menus) != len(role.menu_ids):
            # Some menu IDs are invalid
            missing_ids = set(role.menu_ids) - {menu.id for menu in menus}
            db.rollback()
            raise ResourceNotFoundException("菜单", str(missing_ids))
        
        for menu in menus:
            db.add(RoleMenu(role_id=db_role.id, menu_id=menu.id))
    
    # Add button permissions if specified
    if role.button_ids:
        buttons = db.query(Button).filter(Button.id.in_(role.button_ids)).all()
        if len(buttons) != len(role.button_ids):
            # Some button IDs are invalid
            missing_ids = set(role.button_ids) - {button.id for button in buttons}
            db.rollback()
            raise ResourceNotFoundException("按钮", str(missing_ids))
        
        for button in buttons:
            db.add(RoleButton(role_id=db_role.id, button_id=button.id))
    
    # Commit changes
    try:
        db.commit()
        db.refresh(db_role)
        logger.info(f"Role created: {db_role.name} (ID: {db_role.id})")
        return UnifiedResponseSingle(data=db_role)
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Failed to create role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="创建角色时数据库出错" # This line was already correct, maybe the line number shifted? Let's try with the original English text search again.
        )


@router.get("/{role_id}", response_model=UnifiedResponseSingle[schemas.RoleWithPermissions])
async def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    按 ID 获取角色及权限详情 (管理员)

    根据角色 ID 获取指定角色的详细信息，包括关联的菜单和按钮权限 ID 列表，以及拥有该角色的用户数量。仅管理员可访问。

    Args:
        role_id (int): 要获取的角色 ID。

    Returns:
        UnifiedResponseSingle[schemas.RoleWithPermissions]: 包含角色详细信息和权限列表的统一返回对象。

    Raises:
        ResourceNotFoundException: 如果指定的角色 ID 不存在。
    """
    # Get role with counts
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise ResourceNotFoundException("角色", str(role_id))
    
    # Get menu IDs for this role
    menu_ids = [rm.menu_id for rm in role.menu_permissions]
    
    # Get button IDs for this role
    button_ids = [rb.button_id for rb in role.button_permissions]
    
    # Count users in this role
    users_count = len(role.users)
    
    result = schemas.RoleWithPermissions(
        id=role.id,
        name=role.name,
        description=role.description,
        is_default=role.is_default,
        created_at=role.created_at,
        updated_at=role.updated_at,
        menu_ids=menu_ids,
        button_ids=button_ids,
        users_count=users_count
    )
    
    return UnifiedResponseSingle(data=result)


@router.put("/{role_id}", response_model=UnifiedResponseSingle[schemas.Role])
async def update_role(
    role_id: int,
    role_update: schemas.RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新角色 (管理员)

    根据角色 ID 更新指定角色的信息。仅管理员可访问。

    Args:
        role_id (int): 要更新的角色 ID。
        role_update (schemas.RoleUpdate): 包含要更新的角色字段的请求体。

    Returns:
        UnifiedResponseSingle[schemas.Role]: 包含更新后的角色信息的统一返回对象。

    Raises:
        ResourceNotFoundException: 如果指定的角色 ID 不存在。
        DuplicateResourceException: 如果更新后的角色名称已存在。
    """
    # Get role
    db_role = db.query(Role).filter(Role.id == role_id).first()
    if not db_role:
        raise ResourceNotFoundException("角色", str(role_id))
    
    # Check for name uniqueness if changing
    if role_update.name and role_update.name != db_role.name:
        if db.query(Role).filter(Role.name == role_update.name).first():
            raise DuplicateResourceException("角色", "name", role_update.name)
        db_role.name = role_update.name
    
    # Update other fields if provided
    if role_update.description is not None:
        db_role.description = role_update.description
    
    if role_update.is_default is not None:
        db_role.is_default = role_update.is_default
    
    # Commit changes
    db.commit()
    db.refresh(db_role)
    
    logger.info(f"Role updated: {db_role.name} (ID: {db_role.id})")
    return UnifiedResponseSingle(data=db_role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    删除角色 (管理员)

    根据角色 ID 删除指定角色。如果该角色下有用户，默认不允许删除，除非设置 `force=true`。仅管理员可访问。

    Args:
        role_id (int): 要删除的角色 ID。
        force (bool): 是否强制删除，即使该角色下有用户。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的角色 ID 不存在。
        InvalidOperationException: 如果角色下有用户且未强制删除。
    """
    # Get role
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise ResourceNotFoundException("角色", str(role_id))
    
    # Check if role has users
    if role.users and not force:
        raise InvalidOperationException(
            f"角色已分配给 {len(role.users)} 个用户。如需强制删除，请使用 force=true。"
        )
    
    # Delete role
    db.delete(role)
    db.commit()
    
    logger.info(f"Role deleted: {role.name} (ID: {role.id})")


@router.get("/{role_id}/users", response_model=UnifiedResponsePaginated[user_schemas.User])
async def get_users_by_role(
    role_id: int,
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    username: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    获取拥有指定角色的用户列表 (管理员，分页，按更新日期倒序)

    根据角色 ID 获取拥有该角色的用户列表，支持分页和按用户名过滤。仅管理员可访问。

    Args:
        role_id (int): 要查询用户的角色 ID。
        page (int): 页码，从1开始。
        page_size (int): 每页返回的数量。
        username (Optional[str]): 按用户名过滤 (模糊匹配)。

    Returns:
        UnifiedResponsePaginated[user_schemas.User]: 包含拥有指定角色的用户列表和分页信息的统一返回对象。

    Raises:
        ResourceNotFoundException: 如果指定的角色 ID 不存在。
    """
    # Check if role exists
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise ResourceNotFoundException("角色", str(role_id))
    
    # Query users with this role
    query = db.query(User).filter(User.roles.any(Role.id == role_id))
    
    # Apply username filter if provided
    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))
    
    # 计算 skip
    skip = (page - 1) * page_size

    # Get total count before pagination
    total_count = query.count()

    # Apply pagination and sorting
    users = query.order_by(User.updated_at.desc()).offset(skip).limit(page_size).all() # Added sorting

    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    # Return data in UnifiedResponsePaginated format
    return UnifiedResponsePaginated(
        data=users,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("/{role_id}/users", status_code=status.HTTP_204_NO_CONTENT)
async def add_users_to_role(
    role_id: int,
    user_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    为角色添加用户 (管理员)

    根据角色 ID 为指定的角色添加一个或多个用户。仅管理员可访问。

    Args:
        role_id (int): 要添加用户的角色 ID。
        user_ids (List[int]): 要添加到角色的用户 ID 列表。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的角色 ID 或用户 ID 不存在。
    """
    # Check if role exists
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise ResourceNotFoundException("角色", str(role_id))
    
    # Get users
    users = db.query(User).filter(User.id.in_(user_ids)).all()
    if len(users) != len(user_ids):
        # Some user IDs are invalid
        missing_ids = set(user_ids) - {user.id for user in users}
        raise ResourceNotFoundException("用户", str(missing_ids))
    
    # Add role to users
    for user in users:
        if role not in user.roles:
            user.roles.append(role)
    
    db.commit()
    
    logger.info(f"Added {len(users)} users to role: {role.name} (ID: {role.id})")


@router.post("/{role_id}/menus", status_code=status.HTTP_204_NO_CONTENT)
async def assign_menus_to_role(
    role_id: int,
    menu_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    为角色分配菜单权限 (管理员)

    根据角色 ID 为指定的角色分配菜单权限。此操作会覆盖该角色现有的菜单权限。仅管理员可访问。

    Args:
        role_id (int): 要分配菜单权限的角色 ID。
        menu_ids (List[int]): 要分配的菜单 ID 列表。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的角色 ID 或菜单 ID 不存在。
    """
    # Check if role exists
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise ResourceNotFoundException("角色", str(role_id))
    
    # Delete existing menu permissions
    db.query(RoleMenu).filter(RoleMenu.role_id == role_id).delete()
    
    # Get menus
    menus = db.query(Menu).filter(Menu.id.in_(menu_ids)).all()
    if len(menus) != len(menu_ids):
        # Some menu IDs are invalid
        missing_ids = set(menu_ids) - {menu.id for menu in menus}
        raise ResourceNotFoundException("菜单", str(missing_ids))
    
    # Add new menu permissions
    for menu in menus:
        db.add(RoleMenu(role_id=role_id, menu_id=menu.id))
    
    db.commit()
    
    logger.info(f"Assigned {len(menus)} menus to role: {role.name} (ID: {role.id})")


@router.post("/{role_id}/buttons", status_code=status.HTTP_204_NO_CONTENT)
async def assign_buttons_to_role(
    role_id: int,
    button_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    为角色分配按钮权限 (管理员)

    根据角色 ID 为指定的角色分配按钮权限。此操作会覆盖该角色现有的按钮权限。仅管理员可访问。

    Args:
        role_id (int): 要分配按钮权限的角色 ID。
        button_ids (List[int]): 要分配的按钮 ID 列表。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的角色 ID 或按钮 ID 不存在。
    """
    # Check if role exists
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise ResourceNotFoundException("角色", str(role_id))
    
    # Delete existing button permissions
    db.query(RoleButton).filter(RoleButton.role_id == role_id).delete()
    
    # Get buttons
    buttons = db.query(Button).filter(Button.id.in_(button_ids)).all()
    if len(buttons) != len(button_ids):
        # Some button IDs are invalid
        missing_ids = set(button_ids) - {button.id for button in buttons}
        raise ResourceNotFoundException("按钮", str(missing_ids))
    
    # Add new button permissions
    for button in buttons:
        db.add(RoleButton(role_id=role_id, button_id=button.id))
    
    db.commit()
    
    logger.info(f"Assigned {len(buttons)} buttons to role: {role.name} (ID: {role.id})")
