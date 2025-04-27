from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.department import Department
from app.models.user import User
from app.schemas import department as schemas
from app.core.deps import get_current_user, get_admin_user
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException, InvalidOperationException
from loguru import logger

router = APIRouter(prefix="/departments", tags=["Departments"])


@router.get("", response_model=List[schemas.Department])
async def get_departments(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取部门列表

    获取系统中的部门列表，支持分页和过滤（按名称、父部门 ID）。

    Args:
        skip (int): 跳过的记录数 (分页)。
        limit (int): 返回的最大记录数 (分页)。
        name (Optional[str]): 按部门名称过滤 (模糊匹配)。
        parent_id (Optional[int]): 按父部门 ID 过滤。

    Returns:
        List[schemas.Department]: 部门列表。
    """
    # Build query with filters
    query = db.query(Department)
    
    if name:
        query = query.filter(Department.name.ilike(f"%{name}%"))
    
    if parent_id is not None:
        query = query.filter(Department.parent_id == parent_id)
    
    # Execute query with pagination
    departments = query.offset(skip).limit(limit).all()
    
    return departments


@router.post("", response_model=schemas.Department)
async def create_department(
    department: schemas.DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建新部门 (管理员)

    在系统中创建一个新部门。仅管理员可访问。

    Args:
        department (schemas.DepartmentCreate): 包含新部门信息的请求体。

    Returns:
        schemas.Department: 创建成功的部门信息。

    Raises:
        DuplicateResourceException: 如果部门名称已存在。
        ResourceNotFoundException: 如果指定的父部门 ID 或经理用户 ID 不存在。
        HTTPException: 数据库操作错误。
    """
    # Check if department name exists
    if db.query(Department).filter(Department.name == department.name).first():
        raise DuplicateResourceException("Department", "name", department.name)
    
    # Validate parent department if specified
    if department.parent_id:
        parent = db.query(Department).filter(Department.id == department.parent_id).first()
        if not parent:
            raise ResourceNotFoundException("Parent Department", str(department.parent_id))
    
    # Validate manager if specified
    if department.manager_id:
        manager = db.query(User).filter(User.id == department.manager_id).first()
        if not manager:
            raise ResourceNotFoundException("Manager (User)", str(department.manager_id))
    
    # Create department object
    db_department = Department(
        name=department.name,
        description=department.description,
        parent_id=department.parent_id,
        manager_id=department.manager_id
    )
    
    # Add department to database
    db.add(db_department)
    
    # Commit changes
    try:
        db.commit()
        db.refresh(db_department)
        logger.info(f"Department created: {db_department.name} (ID: {db_department.id})")
        return db_department
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Failed to create department: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database error while creating department"
        )


@router.get("/tree", response_model=List[schemas.DepartmentNode])
async def get_department_tree(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取部门树形结构

    获取系统中的部门层级树形结构。

    Returns:
        List[schemas.DepartmentNode]: 部门树形结构的列表。
    """
    # Get all departments
    departments = db.query(Department).all()
    
    # Build department dictionary
    dept_dict = {dept.id: dept for dept in departments}
    
    # Helper function to build tree recursively
    def build_tree(parent_id=None):
        nodes = []
        for dept in departments:
            if dept.parent_id == parent_id:
                # Get manager name if exists
                manager_name = None
                if dept.manager:
                    manager_name = dept.manager.full_name or dept.manager.username
                
                # Create node
                node = schemas.DepartmentNode(
                    id=dept.id,
                    name=dept.name,
                    description=dept.description,
                    manager_id=dept.manager_id,
                    manager_name=manager_name,
                    children=build_tree(dept.id)
                )
                nodes.append(node)
        return nodes
    
    # Build tree starting from root departments (parent_id is None)
    tree = build_tree()
    
    return tree
@router.get("/{dept_id}", response_model=schemas.DepartmentDetail)
async def get_department(
    dept_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    按 ID 获取部门详情

    根据部门 ID 获取指定部门的详细信息，包括父部门名称、经理名称和部门下的用户数量。

    Args:
        dept_id (int): 要获取的部门 ID。

    Returns:
        schemas.DepartmentDetail: 包含部门详细信息的响应模型。

    Raises:
        ResourceNotFoundException: 如果指定的部门 ID 不存在。
    """
    # Get department
    department = db.query(Department).filter(Department.id == dept_id).first()
    if not department:
        raise ResourceNotFoundException("Department", str(dept_id))
    
    # Get parent name if exists
    parent_name = None
    if department.parent:
        parent_name = department.parent.name
    
    # Get manager name if exists
    manager_name = None
    if department.manager:
        manager_name = department.manager.full_name or department.manager.username
    
    # Count users in this department
    users_count = len(department.users)
    
    result = schemas.DepartmentDetail(
        id=department.id,
        name=department.name,
        description=department.description,
        parent_id=department.parent_id,
        parent_name=parent_name,
        manager_id=department.manager_id,
        manager_name=manager_name,
        created_at=department.created_at,
        updated_at=department.updated_at,
        users_count=users_count
    )
    
    return result


@router.put("/{dept_id}", response_model=schemas.Department)
async def update_department(
    dept_id: int,
    department_update: schemas.DepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新部门 (管理员)

    根据部门 ID 更新指定部门的信息。仅管理员可访问。

    Args:
        dept_id (int): 要更新的部门 ID。
        department_update (schemas.DepartmentUpdate): 包含要更新的部门字段的请求体。

    Returns:
        schemas.Department: 更新后的部门信息。

    Raises:
        ResourceNotFoundException: 如果指定的部门 ID、父部门 ID 或经理用户 ID 不存在。
        DuplicateResourceException: 如果更新后的部门名称已存在。
        InvalidOperationException: 如果尝试将部门设置为其自身的父部门或创建循环引用。
    """
    # Get department
    db_department = db.query(Department).filter(Department.id == dept_id).first()
    if not db_department:
        raise ResourceNotFoundException("Department", str(dept_id))
    
    # Check for name uniqueness if changing
    if department_update.name and department_update.name != db_department.name:
        if db.query(Department).filter(Department.name == department_update.name).first():
            raise DuplicateResourceException("Department", "name", department_update.name)
        db_department.name = department_update.name
    
    # Validate and update parent_id if provided
    if department_update.parent_id is not None:
        if department_update.parent_id == dept_id:
            raise InvalidOperationException("Department cannot be its own parent")
            
        if department_update.parent_id:
            parent = db.query(Department).filter(Department.id == department_update.parent_id).first()
            if not parent:
                raise ResourceNotFoundException("Parent Department", str(department_update.parent_id))
                
            # Check for circular reference
            current_parent = parent
            while current_parent:
                if current_parent.id == dept_id:
                    raise InvalidOperationException("Circular department reference detected")
                current_parent = current_parent.parent
                
        db_department.parent_id = department_update.parent_id
    
    # Validate and update manager_id if provided
    if department_update.manager_id is not None:
        if department_update.manager_id:
            manager = db.query(User).filter(User.id == department_update.manager_id).first()
            if not manager:
                raise ResourceNotFoundException("Manager (User)", str(department_update.manager_id))
        db_department.manager_id = department_update.manager_id
    
    # Update description if provided
    if department_update.description is not None:
        db_department.description = department_update.description
    
    # Commit changes
    db.commit()
    db.refresh(db_department)
    
    logger.info(f"Department updated: {db_department.name} (ID: {db_department.id})")
    return db_department


@router.delete("/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    dept_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    删除部门 (管理员)

    根据部门 ID 删除指定部门。如果该部门下有用户或子部门，默认不允许删除，除非设置 `force=true`。仅管理员可访问。

    Args:
        dept_id (int): 要删除的部门 ID。
        force (bool): 是否强制删除，即使该部门下有用户或子部门。

    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的部门 ID 不存在。
        InvalidOperationException: 如果部门下有用户或子部门且未强制删除。
    """
    # Get department
    department = db.query(Department).filter(Department.id == dept_id).first()
    if not department:
        raise ResourceNotFoundException("Department", str(dept_id))
    
    # Check if department has child departments
    child_departments = db.query(Department).filter(Department.parent_id == dept_id).count()
    if child_departments > 0 and not force:
        raise InvalidOperationException(
            f"Department has {child_departments} child departments. Use force=true to delete anyway."
        )
    
    # Check if department has users
    if department.users and not force:
        raise InvalidOperationException(
            f"Department has {len(department.users)} assigned users. Use force=true to delete anyway."
        )
    
    # Delete department
    db.delete(department)
    db.commit()
    
    logger.info(f"Department deleted: {department.name} (ID: {department.id})")


