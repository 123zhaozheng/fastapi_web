from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.menu import Menu, Button
from app.models.user import User
from app.schemas import menu as schemas
from app.core.deps import get_current_user, get_admin_user, check_permission
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException, InvalidOperationException
from loguru import logger

router = APIRouter(prefix="/menus", tags=["Menus"])


@router.get("", response_model=List[schemas.Menu])
async def get_menus(
    skip: int = 0,
    limit: int = 100,
    title: Optional[str] = None,
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取菜单列表

    获取系统中的菜单列表，支持分页和过滤（按标题、父菜单 ID），并按排序字段排序。

    Args:
        skip (int): 跳过的记录数 (分页)。
        limit (int): 返回的最大记录数 (分页)。
        title (Optional[str]): 按菜单标题过滤 (模糊匹配)。
        parent_id (Optional[int]): 按父菜单 ID 过滤。

    Returns:
        List[schemas.Menu]: 菜单列表。
    """
    # Build query with filters
    query = db.query(Menu)
    
    if title:
        query = query.filter(Menu.title.ilike(f"%{title}%"))
    
    if parent_id is not None:
        query = query.filter(Menu.parent_id == parent_id)
    
    # Execute query with pagination
    menus = query.order_by(Menu.sort_order).offset(skip).limit(limit).all()
    
    return menus


@router.post("", response_model=schemas.Menu)
async def create_menu(
    menu: schemas.MenuCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建新菜单 (管理员)

    在系统中创建一个新菜单。仅管理员可访问。

    Args:
        menu (schemas.MenuCreate): 包含新菜单信息的请求体。

    Returns:
        schemas.Menu: 创建成功的菜单信息。

    Raises:
        ResourceNotFoundException: 如果指定的父菜单 ID 不存在。
        HTTPException: 数据库操作错误。
    """
    # Validate parent menu if specified
    if menu.parent_id:
        parent = db.query(Menu).filter(Menu.id == menu.parent_id).first()
        if not parent:
            raise ResourceNotFoundException("Parent Menu", str(menu.parent_id))
    
    # Create menu object
    db_menu = Menu(
        name=menu.name,
        path=menu.path,
        component=menu.component,
        redirect=menu.redirect,
        icon=menu.icon,
        title=menu.title,
        is_hidden=menu.is_hidden,
        sort_order=menu.sort_order,
        parent_id=menu.parent_id
    )
    
    # Add menu to database
    db.add(db_menu)
    
    # Commit changes
    try:
        db.commit()
        db.refresh(db_menu)
        logger.info(f"Menu created: {db_menu.title} (ID: {db_menu.id})")
        return db_menu
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Failed to create menu: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database error while creating menu"
        )


@router.get("/tree", response_model=List[schemas.MenuNode])
async def get_menu_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取菜单树形结构

    获取系统中的菜单层级树形结构，包含关联的按钮。

    Returns:
        List[schemas.MenuNode]: 菜单树形结构的列表。
    """
    # Get all menus
    menus = db.query(Menu).order_by(Menu.sort_order).all()
    
    # Helper function to build tree recursively
    def build_tree(parent_id=None):
        nodes = []
        for menu in menus:
            if menu.parent_id == parent_id:
                # Create node
                node = schemas.MenuNode(
                    id=menu.id,
                    name=menu.name,
                    path=menu.path,
                    component=menu.component,
                    redirect=menu.redirect,
                    icon=menu.icon,
                    title=menu.title,
                    is_hidden=menu.is_hidden,
                    sort_order=menu.sort_order,
                    buttons=menu.buttons,
                    children=build_tree(menu.id)
                )
                nodes.append(node)
        return nodes
    
    # Build tree starting from root menus (parent_id is None)
    tree = build_tree()
    
    return tree


@router.get("/user/permissions", response_model=schemas.UserPermissions)
async def get_user_permissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取当前用户权限

    获取当前登录用户有权访问的菜单树和按钮权限列表。管理员拥有所有权限。

    Returns:
        schemas.UserPermissions: 包含用户菜单树和按钮权限列表的响应模型。
    """
    if current_user.is_admin:
        # Admin gets all menus and buttons
        menus = db.query(Menu).filter(Menu.parent_id.is_(None)).order_by(Menu.sort_order).all()
        buttons = db.query(Button).all()
        
        # Build menu tree
        def build_admin_tree(parent_id=None):
            nodes = []
            query = db.query(Menu)
            if parent_id is None:
                query = query.filter(Menu.parent_id.is_(None))
            else:
                query = query.filter(Menu.parent_id == parent_id)
                
            for menu in query.order_by(Menu.sort_order).all():
                node = schemas.MenuNode(
                    id=menu.id,
                    name=menu.name,
                    path=menu.path,
                    component=menu.component,
                    redirect=menu.redirect,
                    icon=menu.icon,
                    title=menu.title,
                    is_hidden=menu.is_hidden,
                    sort_order=menu.sort_order,
                    buttons=menu.buttons,
                    children=build_admin_tree(menu.id)
                )
                nodes.append(node)
            return nodes
        
        menu_tree = build_admin_tree()
        button_permissions = [button.permission_key for button in buttons]
        
    else:
        # Regular user gets menus and buttons based on roles
        menu_ids = set()
        button_ids = set()
        
        # Collect menus and buttons from user roles
        for role in current_user.roles:
            for menu_perm in role.menu_permissions:
                menu_ids.add(menu_perm.menu_id)
            
            for button_perm in role.button_permissions:
                button_ids.add(button_perm.button_id)
        
        # Get menu details with parent chain
        menus_dict = {}
        all_menu_ids = set(menu_ids)
        
        # Include all parent menus in the menu chain
        menu_objects = db.query(Menu).filter(Menu.id.in_(menu_ids)).all()
        for menu in menu_objects:
            menus_dict[menu.id] = menu
            parent_id = menu.parent_id
            
            # Add all parents to the menu set
            while parent_id is not None:
                if parent_id not in all_menu_ids:
                    all_menu_ids.add(parent_id)
                    parent = db.query(Menu).filter(Menu.id == parent_id).first()
                    if parent:
                        menus_dict[parent.id] = parent
                        parent_id = parent.parent_id
                    else:
                        break
                else:
                    break
        
        # Get button details
        buttons = db.query(Button).filter(Button.id.in_(button_ids)).all()
        button_permissions = [button.permission_key for button in buttons]
        
        # Build menu tree
        def build_user_tree(parent_id=None):
            nodes = []
            for menu_id, menu in menus_dict.items():
                if menu.parent_id == parent_id:
                    # Only include buttons the user has permission for
                    menu_buttons = [b for b in menu.buttons if b.id in button_ids]
                    
                    node = schemas.MenuNode(
                        id=menu.id,
                        name=menu.name,
                        path=menu.path,
                        component=menu.component,
                        redirect=menu.redirect,
                        icon=menu.icon,
                        title=menu.title,
                        is_hidden=menu.is_hidden,
                        sort_order=menu.sort_order,
                        buttons=menu_buttons,
                        children=build_user_tree(menu.id)
                    )
                    nodes.append(node)
            
            # Sort by sort_order
            nodes.sort(key=lambda x: x.sort_order)
            return nodes
        
        menu_tree = build_user_tree(None)
    
    return schemas.UserPermissions(
        menus=menu_tree,
        buttons=button_permissions
    )
@router.get("/{menu_id}", response_model=schemas.MenuWithButtons)
async def get_menu(
    menu_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    按 ID 获取菜单及按钮

    根据菜单 ID 获取指定菜单的详细信息，包括关联的按钮。

    Args:
        menu_id (int): 要获取的菜单 ID。

    Returns:
        schemas.MenuWithButtons: 包含菜单详细信息和按钮列表的响应模型。

    Raises:
        ResourceNotFoundException: 如果指定的菜单 ID 不存在。
    """
    # Get menu
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise ResourceNotFoundException("Menu", str(menu_id))
    
    return menu


@router.put("/{menu_id}", response_model=schemas.Menu)
async def update_menu(
    menu_id: int,
    menu_update: schemas.MenuUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新菜单 (管理员)

    根据菜单 ID 更新指定菜单的信息。仅管理员可访问。

    Args:
        menu_id (int): 要更新的菜单 ID。
        menu_update (schemas.MenuUpdate): 包含要更新的菜单字段的请求体。

    Returns:
        schemas.Menu: 更新后的菜单信息。

    Raises:
        ResourceNotFoundException: 如果指定的菜单 ID 或父菜单 ID 不存在。
        InvalidOperationException: 如果尝试将菜单设置为其自身的父菜单或创建循环引用。
    """
    # Get menu
    db_menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not db_menu:
        raise ResourceNotFoundException("Menu", str(menu_id))
    
    # Validate and update parent_id if provided
    if menu_update.parent_id is not None:
        if menu_update.parent_id == menu_id:
            raise InvalidOperationException("Menu cannot be its own parent")
            
        if menu_update.parent_id:
            parent = db.query(Menu).filter(Menu.id == menu_update.parent_id).first()
            if not parent:
                raise ResourceNotFoundException("Parent Menu", str(menu_update.parent_id))
                
            # Check for circular reference
            current_parent = parent
            while current_parent:
                if current_parent.id == menu_id:
                    raise InvalidOperationException("Circular menu reference detected")
                current_parent = current_parent.parent
                
        db_menu.parent_id = menu_update.parent_id
    
    # Update other fields if provided
    if menu_update.name is not None:
        db_menu.name = menu_update.name
    
    if menu_update.path is not None:
        db_menu.path = menu_update.path
    
    if menu_update.component is not None:
        db_menu.component = menu_update.component
    
    if menu_update.redirect is not None:
        db_menu.redirect = menu_update.redirect
    
    if menu_update.icon is not None:
        db_menu.icon = menu_update.icon
    
    if menu_update.title is not None:
        db_menu.title = menu_update.title
    
    if menu_update.is_hidden is not None:
        db_menu.is_hidden = menu_update.is_hidden
    
    if menu_update.sort_order is not None:
        db_menu.sort_order = menu_update.sort_order
    
    # Commit changes
    db.commit()
    db.refresh(db_menu)
    
    logger.info(f"Menu updated: {db_menu.title} (ID: {db_menu.id})")
    return db_menu


@router.delete("/{menu_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_menu(
    menu_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    删除菜单 (管理员)

    根据菜单 ID 删除指定菜单。如果该菜单下有子菜单或关联按钮，默认不允许删除，除非设置 `force=true`。仅管理员可访问。

    Args:
        menu_id (int): 要删除的菜单 ID。
        force (bool): 是否强制删除，即使该菜单下有子菜单或关联按钮。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的菜单 ID 不存在。
        InvalidOperationException: 如果菜单下有子菜单或关联按钮且未强制删除。
    """
    # Get menu
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise ResourceNotFoundException("Menu", str(menu_id))
    
    # Check if menu has child menus
    child_menus = db.query(Menu).filter(Menu.parent_id == menu_id).count()
    if child_menus > 0 and not force:
        raise InvalidOperationException(
            f"Menu has {child_menus} child menus. Use force=true to delete anyway."
        )
    
    # Check if menu has buttons
    if menu.buttons and not force:
        raise InvalidOperationException(
            f"Menu has {len(menu.buttons)} buttons. Use force=true to delete anyway."
        )
    
    # Delete menu
    db.delete(menu)
    db.commit()
    
    logger.info(f"Menu deleted: {menu.title} (ID: {menu.id})")




@router.post("/{menu_id}/buttons", response_model=schemas.Button)
async def create_button(
    menu_id: int,
    button: schemas.ButtonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建菜单按钮 (管理员)

    为指定的菜单创建一个新的按钮。仅管理员可访问。

    Args:
        menu_id (int): 要创建按钮的菜单 ID。
        button (schemas.ButtonCreate): 包含新按钮信息的请求体。

    Returns:
        schemas.Button: 创建成功的按钮信息。

    Raises:
        ResourceNotFoundException: 如果指定的菜单 ID 不存在。
        DuplicateResourceException: 如果按钮的权限键已存在。
        HTTPException: 数据库操作错误。
    """
    # Check if menu exists
    menu = db.query(Menu).filter(Menu.id == menu_id).first()
    if not menu:
        raise ResourceNotFoundException("Menu", str(menu_id))
    
    # Check if permission key is unique
    if db.query(Button).filter(Button.permission_key == button.permission_key).first():
        raise DuplicateResourceException("Button", "permission_key", button.permission_key)
    
    # Create button object
    db_button = Button(
        name=button.name,
        permission_key=button.permission_key,
        description=button.description,
        icon=button.icon,
        sort_order=button.sort_order,
        menu_id=menu_id
    )
    
    # Add button to database
    db.add(db_button)
    
    # Commit changes
    try:
        db.commit()
        db.refresh(db_button)
        logger.info(f"Button created: {db_button.name} (ID: {db_button.id}) for menu {menu_id}")
        return db_button
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Failed to create button: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database error while creating button"
        )


@router.put("/buttons/{button_id}", response_model=schemas.Button)
async def update_button(
    button_id: int,
    button_update: schemas.ButtonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新按钮 (管理员)

    根据按钮 ID 更新指定按钮的信息。仅管理员可访问。

    Args:
        button_id (int): 要更新的按钮 ID。
        button_update (schemas.ButtonUpdate): 包含要更新的按钮字段的请求体。

    Returns:
        schemas.Button: 更新后的按钮信息。

    Raises:
        ResourceNotFoundException: 如果指定的按钮 ID 不存在。
        DuplicateResourceException: 如果更新后的按钮权限键已存在。
    """
    # Get button
    db_button = db.query(Button).filter(Button.id == button_id).first()
    if not db_button:
        raise ResourceNotFoundException("Button", str(button_id))
    
    # Check permission key uniqueness if changing
    if button_update.permission_key and button_update.permission_key != db_button.permission_key:
        if db.query(Button).filter(Button.permission_key == button_update.permission_key).first():
            raise DuplicateResourceException("Button", "permission_key", button_update.permission_key)
        db_button.permission_key = button_update.permission_key
    
    # Update other fields if provided
    if button_update.name is not None:
        db_button.name = button_update.name
    
    if button_update.description is not None:
        db_button.description = button_update.description
    
    if button_update.icon is not None:
        db_button.icon = button_update.icon
    
    if button_update.sort_order is not None:
        db_button.sort_order = button_update.sort_order
    
    # Commit changes
    db.commit()
    db.refresh(db_button)
    
    logger.info(f"Button updated: {db_button.name} (ID: {db_button.id})")
    return db_button


@router.delete("/buttons/{button_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_button(
    button_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    删除按钮 (管理员)

    根据按钮 ID 删除指定按钮。仅管理员可访问。

    Args:
        button_id (int): 要删除的按钮 ID。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的按钮 ID 不存在。
    """
    # Get button
    button = db.query(Button).filter(Button.id == button_id).first()
    if not button:
        raise ResourceNotFoundException("Button", str(button_id))
    
    # Delete button
    db.delete(button)
    db.commit()
    
    logger.info(f"Button deleted: {button.name} (ID: {button.id})")


