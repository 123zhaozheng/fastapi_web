import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from loguru import logger
import json


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging HTTP requests and responses
    """
    def __init__(self, app: ASGIApp):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next):
        """
        Process a request and log request/response details
        
        Args:
            request: FastAPI request
            call_next: ASGI app
            
        Returns:
            Response from the call_next function
        """
        # Generate request ID
        request_id = request.headers.get("X-Request-ID", "")
        if not request_id:
            import uuid
            request_id = str(uuid.uuid4())
        
        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "unknown")
        
        # Log request start
        logger.info(
            f"Request started: {method} {path} - "
            f"IP: {client_ip} - "
            f"User-Agent: {user_agent} - "
            f"Request-ID: {request_id}"
        )
        
        # Record start time
        start_time = time.time()
        
        # Process request
        try:
            # Forward to endpoint
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log successful response
            logger.info(
                f"Request completed: {method} {path} - "
                f"Status: {response.status_code} - "
                f"Time: {process_time:.3f}s - "
                f"Request-ID: {request_id}"
            )
            
            # Add processing time header to response
            response.headers["X-Process-Time"] = str(process_time)
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Calculate processing time
            process_time = time.time() - start_time
            
            # Log error
            logger.error(
                f"Request failed: {method} {path} - "
                f"Error: {str(e)} - "
                f"Time: {process_time:.3f}s - "
                f"Request-ID: {request_id}"
            )
            
            # Re-raise exception
            raise
