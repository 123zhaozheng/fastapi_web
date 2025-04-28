from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

# Import DifyService and DifyApiException
from app.services.dify import DifyService, DifyApiException
from app.database import get_db
from app.models.agent import Agent, AgentPermission, AgentPermissionType
from app.models.user import User
from app.models.role import Role
from app.models.department import Department
from app.schemas import agent as schemas
from app.core.deps import get_current_user, get_admin_user
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException, InvalidOperationException
from app.services.file_storage import FileStorageService
from loguru import logger

router = APIRouter(prefix="/agents", tags=["Agents"])


@router.get("", response_model=List[schemas.Agent])
async def get_agents(
    skip: int = 0,
    limit: int = 100,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    获取 Agent 列表 (管理员)

    获取系统中的 Agent 列表，支持分页和过滤（按名称、是否激活）。仅管理员可访问。

    Args:
        skip (int): 跳过的记录数 (分页)。
        limit (int): 返回的最大记录数 (分页)。
        name (Optional[str]): 按 Agent 名称过滤 (模糊匹配)。
        is_active (Optional[bool]): 按 Agent 激活状态过滤。

    Returns:
        List[schemas.Agent]: Agent 列表。
    """
    # Build query with filters
    query = db.query(Agent)
    
    if name:
        query = query.filter(Agent.name.ilike(f"%{name}%"))
    
    if is_active is not None:
        query = query.filter(Agent.is_active == is_active)
    
    # Execute query with pagination
    agents = query.offset(skip).limit(limit).all()
    
    return agents


@router.post("", response_model=schemas.Agent)
async def create_agent(
    agent_data: schemas.AgentCreate, # Renamed input schema variable
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建新 Agent (管理员)

    在系统中创建一个新的 Agent。创建时会使用提供的 Dify API 密钥和端点从 Dify 获取 Agent 的名称和描述。仅管理员可访问。

    Args:
        agent_data (schemas.AgentCreate): 包含新 Agent 信息（包括 Dify API 密钥和端点）的请求体。

    Returns:
        schemas.Agent: 创建成功的 Agent 信息。

    Raises:
        HTTPException: 如果无法从 Dify 获取 Agent 信息或 Dify 凭据无效。
        DuplicateResourceException: 如果 Agent 名称已存在。
        HTTPException: 数据库操作错误。
    """
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
                detail="Could not fetch 'name' from Dify /info endpoint. Please check API key and endpoint."
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
            detail=f"Failed to validate Dify credentials or fetch app info/parameters: {e.detail}"
        )
    finally:
        await temp_dify_service.close()

    # 2. Check if agent with the fetched name already exists locally
    if db.query(Agent).filter(Agent.name == fetched_name).first():
        raise DuplicateResourceException("Agent", "name", fetched_name)

    # 3. Create agent object using fetched info and request data
    db_agent = Agent(
        name=fetched_name, # Use fetched name
        description=fetched_description or agent_data.description, # Use fetched description, fallback to request if needed
        icon=agent_data.icon,
        is_active=agent_data.is_active,
        dify_app_id=agent_data.dify_app_id,
        api_endpoint=agent_data.api_endpoint,
        api_key=agent_data.api_key,
        config=dify_parameters # Store the fetched parameters JSON here
    )

    # 4. Add agent to database
    db.add(db_agent)

    # 5. Commit changes
    try:
        db.commit()
        db.refresh(db_agent)
        logger.info(f"Agent created: {db_agent.name} (ID: {db_agent.id}) using info and parameters from Dify")
        return db_agent
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Failed to create agent due to database integrity error: {str(e)}")
        # Check if it's specifically a unique constraint violation on name (though checked earlier, race condition possible)
        if "UNIQUE constraint failed: agents.name" in str(e):
             raise DuplicateResourceException("Agent", "name", fetched_name)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database error while creating agent"
        )


# Moved /available route before /{agent_id} to fix routing conflict
@router.get("/available", response_model=List[schemas.AgentListItem], operation_id="get_available_agents")
async def get_available_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取当前用户可用的 Agent 列表

    获取当前登录用户有权访问的 Agent 列表。管理员可以访问所有激活的 Agent。普通用户根据全局、角色或部门权限访问 Agent。

    Returns:
        List[schemas.AgentListItem]: 当前用户可用的 Agent 列表。
    """
    # Admin can access all active agents
    if current_user.is_admin:
        return db.query(Agent).filter(Agent.is_active == True).all()
    
    # Check for agents with global access
    global_agents = db.query(Agent).join(
        AgentPermission,
        AgentPermission.agent_id == Agent.id
    ).filter(
        Agent.is_active == True,
        AgentPermission.type == AgentPermissionType.GLOBAL
    ).all()
    
    # Get user's roles
    user_role_ids = [role.id for role in current_user.roles]
    
    # Get agents with role-based access for this user
    role_agents = db.query(Agent).join(
        AgentPermission,
        AgentPermission.agent_id == Agent.id
    ).filter(
        Agent.is_active == True,
        AgentPermission.type == AgentPermissionType.ROLE,
        AgentPermission.role_id.in_(user_role_ids)
    ).all()
    
    # Get agents with department-based access for this user
    dept_agents = []
    if current_user.department_id:
        dept_agents = db.query(Agent).join(
            AgentPermission,
            AgentPermission.agent_id == Agent.id
        ).filter(
            Agent.is_active == True,
            AgentPermission.type == AgentPermissionType.DEPARTMENT,
            AgentPermission.department_id == current_user.department_id
        ).all()
    
    # Combine all unique agents
    all_agents = {}
    for agent in global_agents + role_agents + dept_agents:
        if agent.id not in all_agents:
            all_agents[agent.id] = agent
    
    return list(all_agents.values())


@router.get("/{agent_id}", response_model=schemas.AgentWithPermissions)
async def get_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    按 ID 获取 Agent 及权限详情 (管理员)

    根据 Agent ID 获取指定 Agent 的详细信息，包括关联的权限详情（全局、角色、部门）。仅管理员可访问。

    Args:
        agent_id (int): 要获取的 Agent ID。

    Returns:
        schemas.AgentWithPermissions: 包含 Agent 详细信息和权限列表的响应模型。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
    """
    # Get agent
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise ResourceNotFoundException("Agent", str(agent_id))
    
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
        dify_app_id=agent.dify_app_id,
        api_endpoint=agent.api_endpoint,
        config=agent.config,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        permissions=agent.permissions,
        global_access=global_access
    )
    
    return result


@router.put("/{agent_id}", response_model=schemas.Agent)
async def update_agent(
    agent_id: int,
    agent_update: schemas.AgentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新 Agent (管理员)

    根据 Agent ID 更新指定 Agent 的信息。仅管理员可访问。

    Args:
        agent_id (int): 要更新的 Agent ID。
        agent_update (schemas.AgentUpdate): 包含要更新的 Agent 字段的请求体。

    Returns:
        schemas.Agent: 更新后的 Agent 信息。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
        DuplicateResourceException: 如果更新后的 Agent 名称已存在。
    """
    # Get agent
    db_agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not db_agent:
        raise ResourceNotFoundException("Agent", str(agent_id))
    
    # Check for name uniqueness if changing
    if agent_update.name and agent_update.name != db_agent.name:
        if db.query(Agent).filter(Agent.name == agent_update.name).first():
            raise DuplicateResourceException("Agent", "name", agent_update.name)
        db_agent.name = agent_update.name
    
    # Update other fields if provided
    if agent_update.description is not None:
        db_agent.description = agent_update.description # Corrected typo
    
    if agent_update.icon is not None:
        db_agent.icon = agent_update.icon
    
    if agent_update.is_active is not None:
        db_agent.is_active = agent_update.is_active
    
    if agent_update.dify_app_id is not None:
        db_agent.dify_app_id = agent_update.dify_app_id
    
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
                detail=f"Failed to validate new Dify credentials or fetch app parameters: {e.detail}"
            )
        finally:
            await temp_dify_service.close()

    # Commit changes
    db.commit()
    db.refresh(db_agent)

    logger.info(f"Agent updated: {db_agent.name} (ID: {db_agent.id})")
    return db_agent


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
        raise ResourceNotFoundException("Agent", str(agent_id))
    
    # Delete agent
    db.delete(agent)
    db.commit()
    
    logger.info(f"Agent deleted: {agent.name} (ID: {agent.id})")


# Apply the new response model here
@router.post("/{agent_id}/permissions", response_model=schemas.AgentPermissionsResponse)
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
        schemas.AgentPermissionsResponse: 包含更新后的 Agent ID、权限列表和全局访问状态的响应模型。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID、角色 ID 或部门 ID 不存在。
        HTTPException: 如果权限类型与提供的 ID 不匹配（例如，角色权限缺少 role_id）。
    """
    # Check if agent exists
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise ResourceNotFoundException("Agent", str(agent_id))
    
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
                        detail="Role ID is required for role type permission"
                    )
                
                # Verify role exists
                role = db.query(Role).filter(Role.id == perm.role_id).first()
                if not role:
                    raise ResourceNotFoundException("Role", str(perm.role_id))
                
                db.add(AgentPermission(
                    agent_id=agent_id,
                    type=AgentPermissionType.ROLE,
                    role_id=perm.role_id
                ))
                
            elif perm.type == AgentPermissionType.DEPARTMENT:
                if not perm.department_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Department ID is required for department type permission"
                    )
                
                # Verify department exists
                dept = db.query(Department).filter(Department.id == perm.department_id).first()
                if not dept:
                    raise ResourceNotFoundException("Department", str(perm.department_id))
                
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
    
    return {
        "agent_id": agent_id,
        "permissions": updated_permissions,
        "global_access": global_access
    }

# Removed the original get_available_agents function from here
@router.get("/available", response_model=List[schemas.AgentListItem])
async def get_available_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    获取当前用户可用的 Agent 列表

    获取当前登录用户有权访问的 Agent 列表。管理员可以访问所有激活的 Agent。普通用户根据全局、角色或部门权限访问 Agent。

    Returns:
        List[schemas.AgentListItem]: 当前用户可用的 Agent 列表。
    """
    # Admin can access all active agents
    if current_user.is_admin:
        return db.query(Agent).filter(Agent.is_active == True).all()
    
    # Check for agents with global access
    global_agents = db.query(Agent).join(
        AgentPermission,
        AgentPermission.agent_id == Agent.id
    ).filter(
        Agent.is_active == True,
        AgentPermission.type == AgentPermissionType.GLOBAL
    ).all()
    
    # Get user's roles
    user_role_ids = [role.id for role in current_user.roles]
    
    # Get agents with role-based access for this user
    role_agents = db.query(Agent).join(
        AgentPermission,
        AgentPermission.agent_id == Agent.id
    ).filter(
        Agent.is_active == True,
        AgentPermission.type == AgentPermissionType.ROLE,
        AgentPermission.role_id.in_(user_role_ids)
    ).all()
    
    # Get agents with department-based access for this user
    dept_agents = []
    if current_user.department_id:
        dept_agents = db.query(Agent).join(
            AgentPermission,
            AgentPermission.agent_id == Agent.id
        ).filter(
            Agent.is_active == True,
            AgentPermission.type == AgentPermissionType.DEPARTMENT,
            AgentPermission.department_id == current_user.department_id
        ).all()
    
    # Combine all unique agents
    all_agents = {}
    for agent in global_agents + role_agents + dept_agents:
        if agent.id not in all_agents:
            all_agents[agent.id] = agent
    
    return list(all_agents.values())

@router.post("/{agent_id}/icon")
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
        Dict[str, Any]: 包含图标 URL 的字典。

    Raises:
        ResourceNotFoundException: 如果指定的 Agent ID 不存在。
        HTTPException: 如果上传的文件不是图片。
    """
    # Get agent
    db_agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not db_agent:
        raise ResourceNotFoundException("Agent", str(agent_id))

    # Validate file type (optional, but recommended for icons)
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image"
        )

    # Save icon using FileStorageService
    file_service = FileStorageService()
    icon_info = await file_service.save_agent_icon(file, agent_id)

    # Update agent icon URL
    db_agent.icon = icon_info["url"]
    db.commit()
    db.refresh(db_agent)

    logger.info(f"Agent icon updated for agent ID {agent_id}")

    return {"url": db_agent.icon}
