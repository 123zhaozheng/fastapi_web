# Agent 分类功能实现计划

## 第一阶段：创建 Agent 分类基础模块

1.  **定义 AgentCategory 数据库模型 (`app/models/agent_category.py`)**
    *   创建 `AgentCategory` 表，包含以下字段：
        *   `id`: 主键, Integer
        *   `name`: 分类名称, String(64), nullable=False, unique=True, index=True
        *   `description`: 分类描述, Text, nullable=True
        *   `created_at`: 创建时间, DateTime
        *   `updated_at`: 更新时间, DateTime
    *   在 `app/models/__init__.py` 中导入 `AgentCategory`。

2.  **定义 AgentCategory Pydantic Schemas (`app/schemas/agent_category.py`)**
    *   `AgentCategoryBase`: 包含 `name` 和 `description`。
    *   `AgentCategoryCreate(AgentCategoryBase)`: 用于创建分类。
    *   `AgentCategoryUpdate(BaseModel)`: 用于更新分类，所有字段可选。
    *   `AgentCategory(AgentCategoryBase)`: 用于API返回，包含 `id`, `created_at`, `updated_at`。
        *   配置 `from_attributes = True`。
    *   在 `app/schemas/__init__.py` 中导入这些 schemas。

3.  **实现 AgentCategory API 接口 (`app/api/agent_categories.py`)**
    *   创建 FastAPI APIRouter，前缀为 `/agent-categories`，标签为 `Agent Categories`。
    *   实现以下接口：
        *   `POST /`: 创建 Agent 分类 (需要管理员权限)。
            *   请求体: `AgentCategoryCreate`
            *   响应体: `UnifiedResponseSingle[schemas.AgentCategory]`
            *   处理名称重复的异常。
        *   `GET /`: 获取 Agent 分类列表 (需要用户登录)。
            *   支持分页查询 (`page`, `page_size`)。
            *   支持按名称模糊查询 (`name`)。
            *   按 `updated_at` 降序排列。
            *   响应体: `UnifiedResponsePaginated[schemas.AgentCategory]`
        *   `GET /{category_id}`: 获取指定 ID 的 Agent 分类 (需要用户登录)。
            *   响应体: `UnifiedResponseSingle[schemas.AgentCategory]`
            *   处理分类不存在的异常。
        *   `PUT /{category_id}`: 更新指定 ID 的 Agent 分类 (需要管理员权限)。
            *   请求体: `AgentCategoryUpdate`
            *   响应体: `UnifiedResponseSingle[schemas.AgentCategory]`
            *   处理分类不存在和名称重复的异常。
        *   `DELETE /{category_id}`: 删除指定 ID 的 Agent 分类 (需要管理员权限)。
            *   响应状态码: `204 NO CONTENT`
            *   处理分类不存在的异常。
            *   **重要**: 需要考虑如果某个分类下已经有关联的 Agent，是否允许删除，或者如何处理。目前计划是：如果分类下有 Agent，则不允许删除，并返回错误提示。
    *   在 `app/main.py` 中注册这个新的 router。

## 第二阶段：将 Agent 分类集成到 Agent 模块

1.  **修改 Agent 数据库模型 (`app/models/agent.py`)**
    *   在 `Agent` 模型中添加 `agent_category_id` 字段:
        *   `agent_category_id = Column(Integer, ForeignKey("agent_categories.id", ondelete="SET NULL"), nullable=True)`
        *   `ondelete="SET NULL"` 表示如果一个分类被删除，关联到该分类的 Agent 的 `agent_category_id` 会被设为 NULL。
    *   添加与 `AgentCategory` 的关系:
        *   `category = relationship("AgentCategory", back_populates="agents")`
    *   在 `AgentCategory` 模型 (`app/models/agent_category.py`) 中添加反向关系:
        *   `agents = relationship("Agent", back_populates="category")`

2.  **修改 Agent Pydantic Schemas (`app/schemas/agent.py`)**
    *   在 `AgentBase`, `AgentCreate`, `AgentUpdate`, `Agent`, `AgentDetail`, `AgentListItem` 中添加 `agent_category_id: Optional[int] = None` 字段。
    *   在 `Agent`, `AgentDetail`, `AgentListItem` 中添加 `category: Optional[schemas.AgentCategory] = None` 字段，用于在返回 Agent 信息时带上分类详情。

3.  **修改 Agent API 接口 (`app/api/agents.py`)**
    *   **创建 Agent (`POST /agents`)**:
        *   在请求体 `schemas.AgentCreate` 中接收 `agent_category_id`。
        *   创建 Agent 对象时，如果提供了 `agent_category_id`，需要验证该分类是否存在。如果不存在，则返回错误。
    *   **更新 Agent (`PUT /agents/{agent_id}`)**:
        *   在请求体 `schemas.AgentUpdate` 中接收 `agent_category_id`。
        *   更新 Agent 对象时，如果提供了 `agent_category_id`，需要验证该分类是否存在。如果不存在，则返回错误。
    *   **获取 Agent 列表 (`GET /agents`)**:
        *   添加查询参数 `agent_category_id: Optional[int] = Query(None, description="按 Agent 分类 ID 筛选")`。
        *   在查询构建时加入对 `agent_category_id` 的过滤。
        *   在返回的 `schemas.Agent` 中包含 `category` 详情 (通过 SQLAlchemy 的 relationship 自动加载或手动查询)。
    *   **获取可用 Agent 列表 (`GET /agents/available`)**:
        *   添加查询参数 `agent_category_id: Optional[int] = Query(None, description="按 Agent 分类 ID 筛选")`。
        *   在查询构建时加入对 `agent_category_id` 的过滤。
        *   在返回的 `schemas.AgentListItem` 中包含 `category` 详情。
    *   **获取 Agent 详情 (`GET /agents/{agent_id}`)**:
        *   在返回的 `schemas.AgentWithPermissions` (它继承自 `AgentDetail`) 中包含 `category` 详情。
    *   **获取数字人列表 (`GET /agents/digital-humans`)**:
        *   添加查询参数 `agent_category_id: Optional[int] = Query(None, description="按 Agent 分类 ID 筛选")`。
        *   在查询构建时加入对 `agent_category_id` 的过滤。
        *   在返回的 `schemas.Agent` 中包含 `category` 详情。
    *   **获取可用数字人列表 (`GET /agents/available/digital-humans`)**:
        *   添加查询参数 `agent_category_id: Optional[int] = Query(None, description="按 Agent 分类 ID 筛选")`。
        *   在查询构建时加入对 `agent_category_id` 的过滤。
        *   在返回的 `schemas.AgentListItem` 中包含 `category` 详情。

## 第三阶段：数据库迁移

*   使用 Alembic (如果项目中已集成) 或手动执行 SQL 来创建 `agent_categories` 表，并在 `agents` 表中添加 `agent_category_id` 列和外键约束。

## 可视化计划 (Mermaid Diagram)

```mermaid
graph TD
    A[开始] --> B{创建 Agent 分类模块};
    B --> B1[定义 AgentCategory DB 模型];
    B --> B2[定义 AgentCategory Schemas];
    B --> B3[实现 AgentCategory API];
    B3 --> C{集成 Agent 分类到 Agent 模块};
    C --> C1[修改 Agent DB 模型];
    C --> C2[修改 Agent Schemas];
    C --> C3[修改 Agent API 接口];
    C3 --> D[数据库迁移];
    D --> E[完成];

    subgraph Agent 分类模块
        B1
        B2
        B3
    end

    subgraph Agent 模块集成
        C1
        C2
        C3
    end