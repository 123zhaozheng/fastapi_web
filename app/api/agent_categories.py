from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from app.database import get_db
from app.models import Agent, AgentCategory, User
from app.schemas import agent_category as schemas # Renamed for clarity
from app.schemas.response import UnifiedResponseSingle, UnifiedResponsePaginated
from app.core.deps import get_current_user, get_admin_user
from app.core.exceptions import DuplicateResourceException, ResourceNotFoundException, InvalidOperationException
from loguru import logger

router = APIRouter(prefix="/agent-categories", tags=["Agent Categories"])

@router.post("", response_model=UnifiedResponseSingle[schemas.AgentCategory])
async def create_agent_category(
    category_in: schemas.AgentCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    创建新的 Agent 分类 (管理员)
    """
    try:
        db_category = AgentCategory(**category_in.model_dump())
        db.add(db_category)
        db.commit()
        db.refresh(db_category)
        logger.info(f"Agent category created: {db_category.name} (ID: {db_category.id}) by user {current_user.username}")
        return UnifiedResponseSingle(data=db_category)
    except IntegrityError:
        db.rollback()
        logger.warning(f"Failed to create agent category, name already exists: {category_in.name}")
        raise DuplicateResourceException(resource_name="Agent 分类", field_name="name", field_value=category_in.name)
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating agent category {category_in.name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="创建 Agent 分类失败")

@router.get("", response_model=UnifiedResponsePaginated[schemas.AgentCategory])
async def get_agent_categories(
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    name: Optional[str] = Query(None, description="按名称筛选（模糊匹配）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Changed to get_current_user as per plan
) -> Any:
    """
    获取 Agent 分类列表 (用户)
    """
    query = db.query(AgentCategory)
    if name:
        query = query.filter(AgentCategory.name.ilike(f"%{name}%"))

    total_count = query.count()
    skip = (page - 1) * page_size
    categories = query.order_by(AgentCategory.updated_at.desc()).offset(skip).limit(page_size).all()
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return UnifiedResponsePaginated(
        data=categories,
        total=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )

@router.get("/{category_id}", response_model=UnifiedResponseSingle[schemas.AgentCategory])
async def get_agent_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Changed to get_current_user as per plan
) -> Any:
    """
    获取指定 ID 的 Agent 分类 (用户)
    """
    db_category = db.query(AgentCategory).filter(AgentCategory.id == category_id).first()
    if not db_category:
        logger.warning(f"Agent category with ID {category_id} not found.")
        raise ResourceNotFoundException(resource_name="Agent 分类", id_value=str(category_id))
    return UnifiedResponseSingle(data=db_category)

@router.put("/{category_id}", response_model=UnifiedResponseSingle[schemas.AgentCategory])
async def update_agent_category(
    category_id: int,
    category_in: schemas.AgentCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> Any:
    """
    更新指定 ID 的 Agent 分类 (管理员)
    """
    db_category = db.query(AgentCategory).filter(AgentCategory.id == category_id).first()
    if not db_category:
        logger.warning(f"Agent category with ID {category_id} not found for update.")
        raise ResourceNotFoundException(resource_name="Agent 分类", id_value=str(category_id))

    update_data = category_in.model_dump(exclude_unset=True)
    
    try:
        for key, value in update_data.items():
            setattr(db_category, key, value)
        db.commit()
        db.refresh(db_category)
        logger.info(f"Agent category updated: {db_category.name} (ID: {db_category.id}) by user {current_user.username}")
        return UnifiedResponseSingle(data=db_category)
    except IntegrityError:
        db.rollback()
        logger.warning(f"Failed to update agent category {category_id}, name already exists: {category_in.name}")
        # Ensure category_in.name is not None before using it
        name_value = category_in.name if category_in.name is not None else db_category.name
        raise DuplicateResourceException(resource_name="Agent 分类", field_name="name", field_value=name_value)
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating agent category {category_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新 Agent 分类失败")


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_admin_user)
) -> None:
    """
    删除指定 ID 的 Agent 分类 (管理员)
    如果分类下有关联的 Agent，则不允许删除。
    """
    db_category = db.query(AgentCategory).filter(AgentCategory.id == category_id).first()
    if not db_category:
        logger.warning(f"Agent category with ID {category_id} not found for deletion.")
        raise ResourceNotFoundException(resource_name="Agent 分类", id_value=str(category_id))

    # 检查是否有 Agent 关联到此分类
    associated_agents_count = db.query(Agent).filter(Agent.agent_category_id == category_id).count()
    if associated_agents_count > 0:
        logger.warning(f"Attempted to delete agent category {db_category.name} (ID: {category_id}) which has {associated_agents_count} associated agents.")
        raise InvalidOperationException(detail=f"无法删除分类 '{db_category.name}'，因为它已关联 {associated_agents_count} 个 Agent。请先解除关联。")

    try:
        db.delete(db_category)
        db.commit()
        logger.info(f"Agent category deleted: {db_category.name} (ID: {db_category.id}) by user {current_user.username}")
        return None # FastAPI handles 204 No Content response
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting agent category {category_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="删除 Agent 分类失败")