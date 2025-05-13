from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func # Import func for count

# Import DifyService and DifyApiException
from app.services.dify import DifyService, DifyApiException
from app.database import get_db
from app.models.agent import Agent, AgentPermission, AgentPermissionType
from app.models.user import User
from app.models.role import Role
from app.models.department import Department
from app.schemas import agent as schemas
from app.schemas.response import UnifiedResponseSingle, UnifiedResponsePaginated # Import new response models
from app.core.deps import get_current_user, get_admin_user
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException, InvalidOperationException
from app.services.file_storage import FileStorageService
from loguru import logger

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=UnifiedResponsePaginated[schemas.Agent]) # Modified response_model
async def get_agents(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    name: Optional[str] = Query(None, description="按名称筛选（模糊匹配）"),
    is_active: Optional[bool] = Query(None, description="按激活状态筛选"),
    is_digital_human: Optional[bool] = Query(None, description="按是否为数字人筛选"),
    department_id: Optional[int] = Query(None, description="按部门ID筛选（仅数字人）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    获取 Agent 列表 (管理员，分页，按更新日期倒序)

    获取系统中的 Agent 列表，支持分页和过滤（按名称、是否激活、是否数字人、部门ID）。仅管理员可访问。

    Args:
        page (int): 页码，从1开始。
        page_size (int): 每页返回的数量。
        name (Optional[str]): 按 Agent 名称过滤 (模糊匹配)。
        is_active (Optional[bool]): 按 Agent 激活状态过滤。
        is_digital_human (Optional[bool]): 按是否为数字人过滤。
        department_id (Optional[int]): 按部门ID过滤（仅对数字人有效）。

    Returns:
        UnifiedResponsePaginated[schemas.Agent]: 包含 Agent 列表和分页信息的统一返回对象。
    """
    # Build query with filters
    query = db.query(Agent)
    
    if name:
        query = query.filter(Agent.name.ilike(f"%{name}%"))
    
    if is_active is not None:
        query = query.filter(Agent.is_active == is_active)
    
    if is_digital_human is not None:
        query = query.filter(Agent.is_digital_human == is_digital_human)
    
    if department_id is not None:
        # 检查部门是否存在
        department = db.query(Department).filter(Department.id == department_id).first()
        if not department:
            raise ResourceNotFoundException("部门", str(department_id))
        query = query.filter(Agent.department_id == department_id)
        
        # 如果筛选了部门，自动筛选为数字人
        if is_digital_human is None:
            query = query.filter(Agent.is_digital_human == True)
    
    # 计算 skip
    skip = (page - 1) * page_size

    # Get total count before pagination
    total_count = query.count()

    # Execute query with pagination and sorting
    agents = query.order_by(Agent.updated_at.desc()).offset(skip).limit(page_size).all() # Added sorting

    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    # Return data in UnifiedResponsePaginated format
    return UnifiedResponsePaginated(
        data=agents,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.post("", response_model=UnifiedResponseSingle[schemas.Agent]) # Modified response_model
async def create_agent(
    agent_data: schemas.AgentCreate, # Renamed input schema variable
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建新 Agent (管理员)

    在系统中创建一个新的 Agent。可以设置为普通智能体或数字人，数字人可关联到特定部门。
    创建时会使用提供的 Dify API 密钥和端点从 Dify 获取 Agent 的名称和描述。仅管理员可访问。

    Args:
        agent_data (schemas.AgentCreate): 包含新 Agent 信息的请求体，包括是否为数字人和部门ID（可选）。

    Returns:
        UnifiedResponseSingle[schemas.Agent]: 包含创建成功的 Agent 信息的统一返回对象。

    Raises:
        HTTPException: 如果无法从 Dify 获取 Agent 信息或 Dify 凭据无效。
        DuplicateResourceException: 如果 Agent 名称已存在。
        HTTPException: 数据库操作错误。
    """
    # 验证部门存在
    if agent_data.is_digital_human and agent_data.department_id:
        department = db.query(Department).filter(Department.id == agent_data.department_id).first()
        if not department:
            raise ResourceNotFoundException("部门", str(agent_data.department_id))
            
    # 1. Use provided endpoint and key to fetch info from Dify
    temp_dify_service = DifyService(api_key=agent_data.api_key, base_url=agent_data.api_endpoint)
    try:
        logger.info(f"Fetching Dify app info from {agent_data.api_endpoint}/info")
        dify_info = await temp_dify_service.get_app_info()
        fetched_name = dify_info.get("name")
        fetched_description = dify_info.get("description")
        
        if not fetched_name:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="从 Dify /info 端点获取 'name' 失败。请检查 API 密钥和端点。"
            )
            
        logger.info(f"Successfully fetched Dify app info: Name='{fetched_name}'")

        # Fetch Dify app parameters
        logger.info(f"Fetching Dify app parameters from {agent_data.api_endpoint}/parameters")
        dify_parameters = await temp_dify_service.get_app_parameters()
        logger.info("Successfully fetched Dify app parameters.")

    except DifyApiException as e:
        logger.error(f"Failed to fetch Dify app info or parameters: {e.detail}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"验证 Dify 凭据或获取应用信息/参数失败: {e.detail}"
        )
    finally:
        await temp_dify_service.close()

    # 2. Check if agent with the fetched name already exists locally
    if db.query(Agent).filter(Agent.name == fetched_name).first():
        raise DuplicateResourceException("智能体", "name", fetched_name)

    # 3. Create agent object using fetched info and request data
    db_agent = Agent(
        name=fetched_name, # Use fetched name
        description=fetched_description or agent_data.description, # Use fetched description, fallback to request if needed
        icon=agent_data.icon,
        is_active=agent_data.is_active,
        is_digital_human=agent_data.is_digital_human,
        department_id=agent_data.department_id,
        dify_app_id=agent_data.dify_app_id,
        api_endpoint=agent_data.api_endpoint,
        api_key=agent_data.api_key,
        config=dify_parameters # Store the fetched parameters JSON here
    )

    # 4. Add agent to database
    db.add(db_agent)
    
    # 5. 如果是数字人，自动添加全局权限
    if agent_data.is_digital_human:
        db.flush()  # 确保db_agent有id
        global_permission = AgentPermission(
            agent_id=db_agent.id,
            type=AgentPermissionType.GLOBAL
        )
        db.add(global_permission)

    # 6. Commit changes
    try:
        db.commit()
        db.refresh(db_agent)
        logger.info(f"Agent created: {db_agent.name} (ID: {db_agent.id}), Digital Human: {db_agent.is_digital_human}")
        return UnifiedResponseSingle(data=db_agent) # Wrapped in UnifiedResponseSingle
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Failed to create agent due to database integrity error: {str(e)}")
        # Check if it's specifically a unique constraint violation on name (though checked earlier, race condition possible)
        if "UNIQUE constraint failed: agents.name" in str(e):
             raise DuplicateResourceException("智能体", "name", fetched_name)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="创建智能体时数据库出错"
        )


@router.get("/available", response_model=UnifiedResponsePaginated[schemas.AgentListItem], operation_id="get_available_agents") # Modified response_model
async def get_available_agents(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    is_digital_human: Optional[bool] = Query(None, description="按是否为数字人筛选"),
    department_id: Optional[int] = Query(None, description="按部门ID筛选（仅数字人）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取当前用户可用的 Agent 列表 (分页，按更新日期倒序)

    获取当前登录用户有权访问的 Agent 列表，支持分页和过滤（按是否数字人、部门ID）。
    管理员可以访问所有激活的 Agent。普通用户根据全局、角色或部门权限访问 Agent。

    Args:
        page (int): 页码，从1开始。
        page_size (int): 每页返回的数量。
        is_digital_human (Optional[bool]): 按是否为数字人过滤。
        department_id (Optional[int]): 按部门ID过滤（仅对数字人有效）。

    Returns:
        UnifiedResponsePaginated[schemas.AgentListItem]: 包含当前用户可用的 Agent 列表和分页信息的统一返回对象。
    """
    # Build base query for active agents
    query = db.query(Agent).filter(Agent.is_active == True)
    
    # 添加数字人筛选
    if is_digital_human is not None:
        query = query.filter(Agent.is_digital_human == is_digital_human)
    
    # 添加部门ID筛选
    if department_id is not None:
        # 检查部门是否存在
        department = db.query(Department).filter(Department.id == department_id).first()
        if not department:
            raise ResourceNotFoundException("部门", str(department_id))
        query = query.filter(Agent.department_id == department_id)
        
        # 如果筛选了部门，自动筛选为数字人
        if is_digital_human is None:
            query = query.filter(Agent.is_digital_human == True)

    # Calculate skip
    skip = (page - 1) * page_size

    # Admin can access all active agents
    if current_user.is_admin:
        # Get total count for admin
        total_count = query.count()
        # Apply pagination and sorting
        agents = query.order_by(Agent.updated_at.desc()).offset(skip).limit(page_size).all() # Added sorting
    else:
        # For non-admin users, build a query based on permissions
        # Check for agents with global access
        global_agents_query = query.join(
            AgentPermission,
            AgentPermission.agent_id == Agent.id
        ).filter(
            AgentPermission.type == AgentPermissionType.GLOBAL
        )

        # Get user's roles
        user_role_ids = [role.id for role in current_user.roles]

        # Get agents with role-based access for this user
        role_agents_query = query.join(
            AgentPermission,
            AgentPermission.agent_id == Agent.id
        ).filter(
            AgentPermission.type == AgentPermissionType.ROLE,
            AgentPermission.role_id.in_(user_role_ids)
        )

        # Get agents with department-based access for this user
        dept_agents_query = None
        if current_user.department_id:
            dept_agents_query = query.join(
                AgentPermission,
                AgentPermission.agent_id == Agent.id
            ).filter(
                AgentPermission.type == AgentPermissionType.DEPARTMENT,
                AgentPermission.department_id == current_user.department_id
            )

        # Combine all unique agents using UNION (or equivalent logic)
        # SQLAlchemy's union_all is suitable here for combining query results before counting/paginating
        combined_query = global_agents_query.union_all(role_agents_query)
        if dept_agents_query:
             combined_query = combined_query.union_all(dept_agents_query)

        # Get total count of unique IDs
        # Need to select a distinct column, e.g., Agent.id
        combined_query_with_id = global_agents_query.with_entities(Agent.id).union_all(
            role_agents_query.with_entities(Agent.id)
        )
        if dept_agents_query:
             combined_query_with_id = combined_query_with_id.union_all(dept_agents_query.with_entities(Agent.id))

        # Get total count of unique IDs
        total_count = db.query(func.count()).select_from(combined_query_with_id.distinct().subquery()).scalar() or 0


        # Now, apply pagination to the actual agent objects.
        # We need to get the paginated IDs first, then fetch the full agent objects.
        # Apply sorting to the IDs query before pagination
        paginated_ids_query = combined_query_with_id.distinct().order_by(Agent.updated_at.desc()).offset(skip).limit(page_size) # Added sorting
        paginated_ids = [id_[0] for id_ in paginated_ids_query.all()]

        # Fetch the full agent objects for the paginated IDs, maintaining order might be tricky
        # For simplicity, we'll fetch and sort by ID, assuming that's acceptable.
        # If a specific order is needed, a more complex query involving the original combined query with pagination
        # and then joining to get full details would be required.
        if paginated_ids:
            # Fetch agents and sort them by updated_at in descending order
            agents = db.query(Agent).filter(Agent.id.in_(paginated_ids)).order_by(Agent.updated_at.desc()).all() # Added sorting
        else:
            agents = []


    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    # Return data in UnifiedResponsePaginated format
    return UnifiedResponsePaginated(
        data=agents,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.get("/digital-humans", response_model=UnifiedResponsePaginated[schemas.Agent])
async def get_digital_humans(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    department_id: Optional[int] = Query(None, description="部门ID筛选"),
    name: Optional[str] = Query(None, description="按名称筛选（模糊匹配）"),
    is_active: Optional[bool] = Query(None, description="按激活状态筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    获取数字人列表 (管理员)

    获取系统中所有数字人的列表。可以通过部门ID、名称和激活状态进行筛选。仅管理员可访问。

    Args:
        page (int): 页码，从1开始。
        page_size (int): 每页返回的数量。
        department_id (Optional[int]): 按部门ID筛选。
        name (Optional[str]): 按数字人名称筛选（模糊匹配）。
        is_active (Optional[bool]): 按激活状态筛选。

    Returns:
        UnifiedResponsePaginated[schemas.Agent]: 包含数字人列表和分页信息的统一返回对象。
    """
    query = db.query(Agent).filter(Agent.is_digital_human == True)
    
    # 按名称筛选
    if name:
        query = query.filter(Agent.name.ilike(f"%{name}%"))
    
    # 按激活状态筛选
    if is_active is not None:
        query = query.filter(Agent.is_active == is_active)
    
    # 按部门筛选
    if department_id:
        department = db.query(Department).filter(Department.id == department_id).first()
        if not department:
            raise ResourceNotFoundException("部门", str(department_id))
        query = query.filter(Agent.department_id == department_id)
    
    # 计算总数
    total = query.count()
    
    # 分页和排序
    agents = query.order_by(Agent.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    # 计算总页数
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return UnifiedResponsePaginated(
        data=agents,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.get("/{agent_id}", response_model=UnifiedResponseSingle[schemas.AgentWithPermissions]) # Modified response_model
async def get_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    按 ID 获取 Agent 及权限详情 (管理员)

    根据 Agent ID 获取指定 Agent 的详细信息，包括关联的权限详情（全局、角色、部门）
    以及是否为数字人和关联的部门ID。仅管理员可访问。

    Args:
        agent_id (int): 要获取的 Agent ID。

    Returns:
        UnifiedResponseSingle[schemas.AgentWithPermissions]: 包含 Agent 详细信息和权限列表的统一返回对象。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
    """
    # Get agent
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise ResourceNotFoundException("智能体", str(agent_id))
    
    # Check if agent has global access
    global_access = db.query(AgentPermission).filter(
        AgentPermission.agent_id == agent_id,
        AgentPermission.type == AgentPermissionType.GLOBAL
    ).first() is not None
    
    # Create response
    result = schemas.AgentWithPermissions(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        icon=agent.icon,
        is_active=agent.is_active,
        is_digital_human=agent.is_digital_human,
        department_id=agent.department_id,
        dify_app_id=agent.dify_app_id,
        api_endpoint=agent.api_endpoint,
        config=agent.config,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        permissions=agent.permissions,
        global_access=global_access
    )
    
    return UnifiedResponseSingle(data=result) # Wrapped in UnifiedResponseSingle


@router.put("/{agent_id}", response_model=UnifiedResponseSingle[schemas.Agent]) # Modified response_model
async def update_agent(
    agent_id: int,
    agent_update: schemas.AgentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新 Agent (管理员)

    根据 Agent ID 更新指定 Agent 的信息。可以设置为普通智能体或数字人，数字人可关联到特定部门。
    仅管理员可访问。

    Args:
        agent_id (int): 要更新的 Agent ID。
        agent_update (schemas.AgentUpdate): 包含要更新的 Agent 信息的请求体，包括是否为数字人和部门ID（可选）。

    Returns:
        UnifiedResponseSingle[schemas.Agent]: 包含更新后的 Agent 信息的统一返回对象。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
        HTTPException: 如果更新 Dify 凭据失败或无法获取 Dify 应用信息。
    """
    # 验证部门存在
    if agent_update.is_digital_human is not None and agent_update.is_digital_human and agent_update.department_id:
        department = db.query(Department).filter(Department.id == agent_update.department_id).first()
        if not department:
            raise ResourceNotFoundException("部门", str(agent_update.department_id))
    
    # Get agent
    db_agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not db_agent:
        raise ResourceNotFoundException("智能体", str(agent_id))
    
    # Check if name is being updated and is unique
    if agent_update.name is not None and agent_update.name != db_agent.name:
        name_exists = db.query(Agent).filter(Agent.name == agent_update.name).first()
        if name_exists:
            raise DuplicateResourceException("智能体", "name", agent_update.name)
    
    # Update fields from update request
    if agent_update.name is not None:
        db_agent.name = agent_update.name
    if agent_update.description is not None:
        db_agent.description = agent_update.description
    if agent_update.icon is not None:
        db_agent.icon = agent_update.icon
    if agent_update.is_active is not None:
        db_agent.is_active = agent_update.is_active
    if agent_update.is_digital_human is not None:
        db_agent.is_digital_human = agent_update.is_digital_human
    if agent_update.department_id is not None:
        db_agent.department_id = agent_update.department_id
    if agent_update.dify_app_id is not None:
        db_agent.dify_app_id = agent_update.dify_app_id
    
    # 如果从非数字人变为数字人，自动添加全局权限
    was_digital_human = db_agent.is_digital_human
    if agent_update.is_digital_human is not None and agent_update.is_digital_human and not was_digital_human:
        # 检查是否已有全局权限
        has_global_perm = db.query(AgentPermission).filter(
            AgentPermission.agent_id == agent_id, 
            AgentPermission.type == AgentPermissionType.GLOBAL
        ).first()
        
        if not has_global_perm:
            global_permission = AgentPermission(
                agent_id=agent_id,
                type=AgentPermissionType.GLOBAL
            )
            db.add(global_permission)
    
    if agent_update.api_endpoint is not None:
        db_agent.api_endpoint = agent_update.api_endpoint
    
    if agent_update.api_key is not None:
        db_agent.api_key = agent_update.api_key
    
    if agent_update.config is not None:
        db_agent.config = agent_update.config

    # Check if api_endpoint or api_key is being updated
    if agent_update.api_endpoint is not None or agent_update.api_key is not None:
        # Use the potentially new endpoint and key for the DifyService
        new_api_endpoint = agent_update.api_endpoint if agent_update.api_endpoint is not None else db_agent.api_endpoint
        new_api_key = agent_update.api_key if agent_update.api_key is not None else db_agent.api_key

        temp_dify_service = DifyService(api_key=new_api_key, base_url=new_api_endpoint)
        try:
            logger.info(f"Fetching Dify app parameters from {new_api_endpoint}/parameters for agent update")
            dify_parameters = await temp_dify_service.get_app_parameters()
            logger.info("Successfully fetched Dify app parameters for update.")
            # Update the config field
            db_agent.config = dify_parameters
        except DifyApiException as e:
            logger.error(f"Failed to fetch Dify app parameters during update: {e.detail}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"验证新的 Dify 凭据或获取应用参数失败: {e.detail}"
            )
        finally:
            await temp_dify_service.close()

    # Commit changes
    db.commit()
    db.refresh(db_agent)

    logger.info(f"Agent updated: {db_agent.name} (ID: {db_agent.id}), Digital Human: {db_agent.is_digital_human}")
    return UnifiedResponseSingle(data=db_agent) # Wrapped in UnifiedResponseSingle


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    删除 Agent (管理员)

    根据 Agent ID 删除指定 Agent。仅管理员可访问。

    Args:
        agent_id (int): 要删除的 Agent ID。
    
    Returns:
        None: 成功时不返回内容 (HTTP 204)。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
    """
    # Get agent
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise ResourceNotFoundException("智能体", str(agent_id))
    
    # Delete agent
    db.delete(agent)
    db.commit()
    
    logger.info(f"Agent deleted: {agent.name} (ID: {agent.id})")


@router.post("/{agent_id}/permissions", response_model=UnifiedResponseSingle[schemas.AgentPermissionsResponse]) # Modified response_model
async def set_agent_permissions(
    agent_id: int,
    permissions: schemas.AgentPermissions,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any: # Return type hint remains Any, FastAPI handles conversion based on response_model
    """
    设置 Agent 访问权限 (管理员)

    根据 Agent ID 设置指定 Agent 的访问权限。此操作会覆盖该 Agent 现有的权限设置。权限类型包括全局、角色和部门。仅管理员可访问。

    Args:
        agent_id (int): 要设置权限的 Agent ID。
        permissions (schemas.AgentPermissions): 包含权限设置信息的请求体。

    Returns:
        UnifiedResponseSingle[schemas.AgentPermissionsResponse]: 包含更新后的 Agent ID、权限列表和全局访问状态的统一返回对象。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID、角色 ID 或部门 ID 不存在。
        HTTPException: 如果权限类型与提供的 ID 不匹配（例如，角色权限缺少 role_id）。
    """
    # Check if agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise ResourceNotFoundException("智能体", str(agent_id))
    
    # Delete existing permissions
    db.query(AgentPermission).filter(AgentPermission.agent_id == agent_id).delete()
    
    # Set global access if specified
    if permissions.global_access:
        db.add(AgentPermission(
            agent_id=agent_id,
            type=AgentPermissionType.GLOBAL
        ))
    else:
        # Add new permissions
        for perm in permissions.permissions:
            # Validate according to type
            if perm.type == AgentPermissionType.ROLE:
                if not perm.role_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="角色类型权限需要角色 ID"
                    )
                
                # Verify role exists
                role = db.query(Role).filter(Role.id == perm.role_id).first()
                if not role:
                    raise ResourceNotFoundException("角色", str(perm.role_id))
                
                db.add(AgentPermission(
                    agent_id=agent_id,
                    type=AgentPermissionType.ROLE,
                    role_id=perm.role_id
                ))
                
            elif perm.type == AgentPermissionType.DEPARTMENT:
                if not perm.department_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="部门类型权限需要部门 ID"
                    )
                
                # Verify department exists
                dept = db.query(Department).filter(Department.id == perm.department_id).first()
                if not dept:
                    raise ResourceNotFoundException("部门", str(perm.department_id))
                
                db.add(AgentPermission(
                    agent_id=agent_id,
                    type=AgentPermissionType.DEPARTMENT,
                    department_id=perm.department_id
                ))
    
    # Commit changes
    db.commit()
    
    logger.info(f"Permissions updated for agent: {agent.name} (ID: {agent.id})")
    
    # Return updated permissions
    updated_permissions = db.query(AgentPermission).filter(AgentPermission.agent_id == agent_id).all()
    
    global_access = any(p.type == AgentPermissionType.GLOBAL for p in updated_permissions)
    
    result = {
        "agent_id": agent_id,
        "permissions": updated_permissions,
        "global_access": global_access
    }
    
    return UnifiedResponseSingle(data=result) # Wrapped in UnifiedResponseSingle


# Removed the original get_available_agents function from here
@router.post("/{agent_id}/icon", response_model=UnifiedResponseSingle[schemas.AgentIconUploadResponse]) # Modified response_model
async def upload_agent_icon(
    agent_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    上传 Agent 图标 (管理员)

    为指定的 Agent 上传图标图片。仅管理员可访问。

    Args:
        agent_id (int): 要上传图标的 Agent ID。
        file (UploadFile): 要上传的图标文件。

    Returns:
        UnifiedResponseSingle[schemas.AgentIconUploadResponse]: 包含图标 URL 的统一返回对象。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
        HTTPException: 如果上传的文件不是图片。
    """
    # Get agent
    db_agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not db_agent:
        raise ResourceNotFoundException("智能体", str(agent_id))

    # Validate file type (optional, but recommended for icons)
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的文件类型。只允许上传图片。"
        )

    # Save icon using FileStorageService
    file_service = FileStorageService()
    icon_info = await file_service.save_agent_icon(file, agent_id)

    # Update agent icon URL
    db_agent.icon = icon_info["url"]
    db.commit()
    db.refresh(db_agent)

    logger.info(f"Agent icon updated for agent ID {agent_id}")

    # Return UnifiedResponseSingle
    return UnifiedResponseSingle(data={"url": db_agent.icon})





@router.get("/available/digital-humans", response_model=UnifiedResponsePaginated[schemas.AgentListItem])
async def get_available_digital_humans(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    department_id: Optional[int] = Query(None, description="部门ID筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取当前用户可用的数字人列表 (分页，按更新日期倒序)

    获取当前登录用户有权访问的数字人列表，支持分页和部门筛选。
    管理员可以访问所有激活的数字人。普通用户根据全局、角色或部门权限访问数字人。

    Args:
        page (int): 页码，从1开始。
        page_size (int): 每页返回的数量。
        department_id (Optional[int]): 按部门ID筛选。

    Returns:
        UnifiedResponsePaginated[schemas.AgentListItem]: 包含当前用户可用的数字人列表和分页信息的统一返回对象。
    """
    # 构建查询基础：活跃的数字人
    query = db.query(Agent).filter(Agent.is_active == True, Agent.is_digital_human == True)
    
    # 按部门筛选
    if department_id:
        department = db.query(Department).filter(Department.id == department_id).first()
        if not department:
            raise ResourceNotFoundException("部门", str(department_id))
        query = query.filter(Agent.department_id == department_id)
    
    # 计算 skip
    skip = (page - 1) * page_size

    # Admin can access all active digital humans
    if current_user.is_admin:
        # Get total count for admin
        total_count = query.count()
        # Apply pagination and sorting
        agents = query.order_by(Agent.updated_at.desc()).offset(skip).limit(page_size).all()
    else:
        # For non-admin users, build a query based on permissions
        # Check for digital humans with global access
        global_agents_query = query.join(
            AgentPermission,
            AgentPermission.agent_id == Agent.id
        ).filter(
            AgentPermission.type == AgentPermissionType.GLOBAL
        )

        # Get user's roles
        user_role_ids = [role.id for role in current_user.roles]

        # Get digital humans with role-based access for this user
        role_agents_query = query.join(
            AgentPermission,
            AgentPermission.agent_id == Agent.id
        ).filter(
            AgentPermission.type == AgentPermissionType.ROLE,
            AgentPermission.role_id.in_(user_role_ids)
        )

        # Get digital humans with department-based access for this user
        dept_agents_query = None
        if current_user.department_id:
            dept_agents_query = query.join(
                AgentPermission,
                AgentPermission.agent_id == Agent.id
            ).filter(
                AgentPermission.type == AgentPermissionType.DEPARTMENT,
                AgentPermission.department_id == current_user.department_id
            )

        # Combine all unique digital humans
        combined_query = global_agents_query.union_all(role_agents_query)
        if dept_agents_query:
             combined_query = combined_query.union_all(dept_agents_query)

        # Get total count of unique IDs
        combined_query_with_id = global_agents_query.with_entities(Agent.id).union_all(
            role_agents_query.with_entities(Agent.id)
        )
        if dept_agents_query:
             combined_query_with_id = combined_query_with_id.union_all(dept_agents_query.with_entities(Agent.id))

        # Get total count of unique IDs
        total_count = db.query(func.count()).select_from(combined_query_with_id.distinct().subquery()).scalar() or 0

        # Apply pagination to the IDs query before fetching the full objects
        paginated_ids_query = combined_query_with_id.distinct().order_by(Agent.updated_at.desc()).offset(skip).limit(page_size)
        paginated_ids = [id_[0] for id_ in paginated_ids_query.all()]

        # Fetch the full digital human objects
        if paginated_ids:
            agents = db.query(Agent).filter(Agent.id.in_(paginated_ids)).order_by(Agent.updated_at.desc()).all()
        else:
            agents = []

    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    # Return data in UnifiedResponsePaginated format
    return UnifiedResponsePaginated(
        data=agents,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )
