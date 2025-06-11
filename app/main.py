import os
import time
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.schemas.response import UnifiedResponseSingle

from app.config import settings
from app.api import auth, users, roles, departments, menus, agents, chat, agent_categories
from app.utils.logger import setup_logging
from app.core.exceptions import AppException

# 导入新的存储服务和配置
from app.core.storage import storage_client, STORAGE_TYPE
from fastapi.staticfiles import StaticFiles

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Creating FastAPI app...")
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)
logger.info("FastAPI app created.")

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup logging
setup_logging()

# 根据存储类型，有条件地挂载静态文件目录
if STORAGE_TYPE == 'local':
    logger.info("Local storage is used, mounting static directories...")
    # 确保基础目录存在
    local_storage_path = "./uploads"
    os.makedirs(os.path.join(local_storage_path, "avatars"), exist_ok=True)
    os.makedirs(os.path.join(local_storage_path, "icons"), exist_ok=True)
    
    # 将 /avatars URL 路径映射到 /app/uploads/avatars 物理路径
    app.mount("/avatars", StaticFiles(directory=os.path.join(local_storage_path, "avatars")), name="avatars")
    # 将 /icons URL 路径映射到 /app/uploads/icons 物理路径
    app.mount("/icons", StaticFiles(directory=os.path.join(local_storage_path, "icons")), name="icons")
    logger.info(f"Mounted /avatars to {os.path.join(local_storage_path, 'avatars')}")
    logger.info(f"Mounted /icons to {os.path.join(local_storage_path, 'icons')}")
else:
    logger.info("S3 storage is used, skipping static directory mounting.")

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")
    ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")
    
    logger.info(f"Request started: {request.method} {request.url.path} - IP: {ip} - User-Agent: {user_agent}")
    
    start_time = time.time()
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(f"Request completed: {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")
        
        response.headers["X-Process-Time"] = str(process_time)
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Request failed: {request.method} {request.url.path} - Error: {str(e)} - Time: {process_time:.3f}s")
        raise

# Global exception handler
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    logger.error(f"AppException: {str(exc.detail)} - Status: {exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "code": "internal_error"}
    )

logger.info("Including API routers...")
# Include API routers
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["Authentication"])
app.include_router(users.router, prefix=settings.API_V1_STR, tags=["Users"])
app.include_router(roles.router, prefix=settings.API_V1_STR, tags=["Roles"])
app.include_router(departments.router, prefix=settings.API_V1_STR, tags=["Departments"])
app.include_router(menus.router, prefix=settings.API_V1_STR, tags=["Menus"])
app.include_router(agents.router, prefix=settings.API_V1_STR, tags=["Agents"])
app.include_router(chat.router, prefix=settings.API_V1_STR, tags=["Chat"])
app.include_router(agent_categories.router, prefix=settings.API_V1_STR, tags=["Agent Categories"])
logger.info("API routers included.")

@app.get("/")
async def root():
    return {"message": "Welcome to AI Chat API"}

# Run the application with uvicorn when this script is executed
if __name__ == "__main__":
    import uvicorn
    import platform
    import socket
    
    # 获取系统信息
    system_info = {
        "os": platform.system(),
        "version": settings.VERSION if hasattr(settings, "VERSION") else "1.0.0",
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
        "ip": socket.gethostbyname(socket.gethostname())
    }
    
    # 美化的 ASCII 艺术标题
    ascii_art = f"""
    ╭─────────────────────────────────────────────────────╮
    │                                                     │
    │   █▀▄ █ █▀▀ █ ▀█▀ ▄▀█ █   █ █ █ █▀▄▀█ ▄▀█ █▄░█    │
    │   █▄▀ █ █▄█ █ ░█░ █▀█ █▄▄ █▀█ █▄█ █░▀░█ █▀█ █░▀█   │
    │                                                     │
    │        FastAPI 智能对话系统后端 v{system_info["version"]}        │
    │                                                     │
    ╰─────────────────────────────────────────────────────╯
    
    ╭───────────────────── 服务器信息 ─────────────────────╮
    │                                                     │
    │  系统: {system_info["os"]}                                        
    │  Python版本: {system_info["python"]}                             
    │  主机名: {system_info["hostname"]}                               
    │  IP地址: {system_info["ip"]}                                  
    │  运行端口: 15000                                     │
    │                                                     │
    ╰─────────────────────────────────────────────────────╯
    """
    
    print(ascii_art)
    uvicorn.run("app.main:app", host="0.0.0.0", port=15000, reload=True)
