# FastAPI AI Chat Backend

## 📝 项目概述

这是一个基于 FastAPI 构建的 AI 聊天应用后端服务，提供了用户管理、角色管理、聊天机器人交互等功能。

## ✨ 功能特性

*   用户认证与授权 (JWT Bearer Token)
*   用户管理 (CRUD 操作)
*   角色与权限管理
*   部门管理
*   菜单管理 (用于前端动态路由或权限控制)
*   AI 代理配置与管理
*   与 Dify AI 平台集成进行聊天交互
*   文件上传功能 (例如：头像、聊天附件)
*   请求日志与全局异常处理

## 🛠️ 技术栈

*   **后端框架**: FastAPI ([`fastapi>=0.115.12`](pyproject.toml:10))
*   **数据库**: PostgreSQL ([`postgres:13-alpine`](docker-compose.yml:5))
*   **ORM**: SQLAlchemy ([`sqlalchemy>=2.0.40`](pyproject.toml:24))
*   **数据库驱动**: Psycopg2 ([`psycopg2-binary>=2.9.10`](pyproject.toml:18))
*   **编程语言**: Python 3.10 ([`FROM python:3.10-slim`](Dockerfile:2))
*   **异步 ASGI 服务器**: Uvicorn ([`uvicorn>=0.34.2`](pyproject.toml:26))
*   **数据校验与序列化**: Pydantic ([`pydantic>=2.11.3`](pyproject.toml:19)), Pydantic Settings ([`pydantic-settings>=2.9.1`](pyproject.toml:20))
*   **认证与安全**: Python-JOSE ([`python-jose>=3.4.0`](pyproject.toml:21)) for JWT, Passlib ([`passlib>=1.7.4`](pyproject.toml:16)) & Bcrypt ([`bcrypt>=4.3.0`](pyproject.toml:8)) for password hashing
*   **日志**: Loguru ([`loguru>=0.7.3`](pyproject.toml:15))
*   **HTTP 客户端**: HTTPX ([`httpx>=0.28.1`](pyproject.toml:14)) (可能用于调用 Dify API)
*   **邮件验证**: Email-Validator ([`email-validator>=2.2.0`](pyproject.toml:9))
*   **表单数据处理**: Python-Multipart ([`python-multipart>=0.0.20`](pyproject.toml:22))
*   **SSE (Server-Sent Events)**: SSE-Starlette ([`sse-starlette>=2.3.3`](pyproject.toml:25)) (可能用于聊天流式响应)
*   **容器化**: Docker, Docker Compose

## 🚀 快速开始

### 依赖环境

*   Docker
*   Docker Compose

### 安装与运行 (使用 Docker Compose)

1.  **克隆项目**:
    ```bash
    git clone <your-repository-url>
    cd <project-directory-name>
    ```

2.  **配置环境变量**:
    复制 [`.env.example`](.env.example:1) 文件为 `.env`，并根据您的实际情况修改其中的配置项。
    ```bash
    cp .env.example .env
    ```
    至少需要配置以下 PostgreSQL 相关的变量：
    *   `PGHOST` (如果使用 docker-compose 且服务名为 `db`，则通常为 `db`)
    *   `PGPORT` (PostgreSQL 内部端口，通常为 `5432`)
    *   `PGUSER`
    *   `PGPASSWORD`
    *   `PGDATABASE`
    以及应用密钥：
    *   `SECRET_KEY` (用于 JWT 签名，请生成一个强随机字符串)
    *   `DIFY_API_BASE_URL` (如果需要使用 Dify 服务)
    *   `DIFY_API_KEY` (如果需要使用 Dify 服务)

3.  **构建并启动服务**:
    ```bash
    docker-compose up --build -d
    ```
    服务将在 `http://localhost:15000` (根据 [`docker-compose.yml`](docker-compose.yml:29) 中的端口映射) 启动。
    数据库服务 (PostgreSQL) 将在宿主机的 `15432` 端口可用 (根据 [`docker-compose.yml`](docker-compose.yml:12) 中的端口映射)。

4.  **查看 API 文档**:
    API 文档 (Swagger UI) 可以在 `http://localhost:15000/api/openapi.json` (实际路径为 `/docs`) 访问。
    *   Swagger UI: `http://localhost:15000/docs`
    *   ReDoc: `http://localhost:15000/redoc`

    (API 路径前缀为 [`/api`](app/config.py:9)，具体 OpenAPI URL 为 [`/api/openapi.json`](app/main.py:22))

### 本地开发 (不使用 Docker)

1.  **确保已安装 Python 3.10+**

2.  **创建并激活虚拟环境**:
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # venv\Scripts\activate  # Windows
    ```

3.  **安装依赖**:
    ```bash
    pip install -r requirements.txt
    ```
    (或者，如果项目使用 `uv` 并且有 `uv.lock` 文件，可以使用 `uv pip sync`)

4.  **配置环境变量**:
    (同上，创建并编辑 `.env` 文件。确保数据库服务已在本地或远程启动并可访问)

5.  **启动应用**:
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ```
    应用将在 `http://localhost:8000` 启动。

## 📁 项目结构

```
.
├── app/                  # 应用核心代码
│   ├── api/              # API 路由模块 (auth, users, roles, departments, menus, agents, chat)
│   ├── core/             # 核心配置 (deps.py, exceptions.py, security.py)
│   ├── middleware/       # 中间件 (logging.py)
│   ├── models/           # SQLAlchemy 数据模型 (user.py, role.py, etc.)
│   ├── schemas/          # Pydantic 数据模型/模式 (user.py, role.py, token.py, response.py, etc.)
│   ├── services/         # 业务逻辑服务 (dify.py, file_storage.py)
│   ├── utils/            # 工具函数 (logger.py, validators.py)
│   ├── __init__.py
│   ├── config.py         # 应用配置 (Settings class)
│   ├── database.py       # 数据库连接与会话管理
│   └── main.py           # FastAPI 应用入口与中间件配置
├── docs/                 # 项目相关文档 (例如 user_role_api_update.md)
├── uploads/              # (默认) 文件上传存储目录 (由 FILE_STORAGE_PATH 定义)
│   ├── avatars/
│   └── icons/
├── .env                  # (自行创建) 环境变量文件
├── .env.example          # 环境变量示例文件
├── .gitignore            # Git 忽略文件配置
├── docker-compose.yml    # Docker Compose 配置文件
├── Dockerfile            # Docker 镜像构建文件
├── pyproject.toml        # Python 项目配置文件 (PEP 621), 包含依赖
├── requirements.txt      # 项目依赖 (通常由 pyproject.toml 生成或手动维护)
├── uv.lock               # uv 包管理器锁文件
└── README.md             # (本文档) 项目说明文件
```

## 接口文档

API 接口遵循 OpenAPI 规范，基础路径前缀为 [`/api`](app/config.py:9)。

*   **Swagger UI**: `http://localhost:15000/docs`
*   **ReDoc**: `http://localhost:15000/redoc`

主要模块包括：
*   **Authentication**: `http://localhost:15000/api/auth`
*   **Users**: `http://localhost:15000/api/users`
*   **Roles**: `http://localhost:15000/api/roles`
*   **Departments**: `http://localhost:15000/api/departments`
*   **Menus**: `http://localhost:15000/api/menus`
*   **Agents**: `http://localhost:15000/api/agents`
*   **Chat**: `http://localhost:15000/api/chat`

(请将 `http://localhost:15000` 替换为实际部署的 API 基础 URL)

## ⚙️ 配置项

项目的主要配置项通过环境变量进行管理，请参考 [`.env.example`](.env.example:1) 文件和 [`app/config.py`](app/config.py:1)。

关键配置包括：
*   `PROJECT_NAME`: 项目名称 (默认: "FastAPI AI Chat Backend")
*   `API_V1_STR`: API 版本前缀 (默认: "/api")
*   `SECRET_KEY`: 用于 JWT 签名的密钥 (必须设置一个强随机字符串)
*   `ACCESS_TOKEN_EXPIRE_MINUTES`: Access Token 过期时间 (分钟)
*   `REFRESH_TOKEN_EXPIRE_MINUTES`: Refresh Token 过期时间 (分钟)
*   `POSTGRES_HOST`: PostgreSQL 服务器地址
*   `POSTGRES_PORT`: PostgreSQL 服务器端口
*   `POSTGRES_USER`: PostgreSQL 用户名
*   `POSTGRES_PASSWORD`: PostgreSQL 密码
*   `POSTGRES_DB`: PostgreSQL 数据库名称
*   `DATABASE_URI`: (可选) 完整的数据库连接字符串，如果提供则会覆盖上述单独的 PG 参数
*   `DIFY_API_BASE_URL`: Dify API 基础 URL
*   `DIFY_API_KEY`: Dify API 密钥
*   `FILE_STORAGE_PATH`: 文件存储的基础路径 (默认: `./uploads`)
*   `MAX_UPLOAD_SIZE`: 最大上传文件大小 (字节)
*   `LOG_LEVEL`: 日志级别 (例如: INFO, DEBUG)
*   `LOG_FILE`: 日志文件路径

## 🤝 贡献指南

(暂无，可根据需要补充)

## 📄 许可证

(暂未指定，可根据需要补充)