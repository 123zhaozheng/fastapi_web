from fastapi import HTTPException, status


class AppException(HTTPException):
    """
    Base exception for application-specific exceptions
    
    Attributes:
        detail: Exception detail message
        status_code: HTTP status code
        code: Application-specific error code
    """
    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        code: str = "app_error"
    ):
        self.code = code
        super().__init__(status_code=status_code, detail=detail)


class UserNotFoundException(AppException):
    """Exception raised when a user is not found"""
    def __init__(self, detail: str = "用户未找到"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_404_NOT_FOUND,
            code="user_not_found"
        )


class InvalidCredentialsException(AppException):
    """Exception raised when credentials are invalid"""
    def __init__(self, detail: str = "用户名或密码错误"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="invalid_credentials"
        )


class PermissionDeniedException(AppException):
    """Exception raised when user doesn't have required permissions"""
    def __init__(self, detail: str = "权限不足"):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_403_FORBIDDEN,
            code="permission_denied"
        )


class ResourceNotFoundException(AppException):
    """Exception raised when a resource is not found"""
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            detail=f"未找到 ID 为 {resource_id} 的 {resource_type}",
            status_code=status.HTTP_404_NOT_FOUND,
            code="resource_not_found"
        )


class DuplicateResourceException(AppException):
    """Exception raised when a resource already exists"""
    def __init__(self, resource_type: str, field: str, value: str):
        super().__init__(
            detail=f"字段为 {field}，值为 '{value}' 的 {resource_type} 已存在",
            status_code=status.HTTP_409_CONFLICT,
            code="duplicate_resource"
        )


class InvalidOperationException(AppException):
    """Exception raised when an operation is invalid"""
    def __init__(self, detail: str):
        super().__init__(
            detail=detail,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_operation"
        )


class DifyApiException(AppException):
    """Exception raised when there's an issue with Dify API"""
    def __init__(self, detail: str, status_code: int = status.HTTP_502_BAD_GATEWAY, code: str = "dify_api_error"):
        super().__init__(
            detail=detail,
            status_code=status_code,
            code=code # Pass the received code to the parent class
        )


class FileTooLargeException(AppException):
    """Exception raised when an uploaded file is too large"""
    def __init__(self, max_size: int):
        super().__init__(
            detail=f"文件过大。最大允许大小为 {max_size / (1024 * 1024):.1f} MB",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code="file_too_large"
        )


class InvalidFileTypeException(AppException):
    """Exception raised when an uploaded file has an invalid type"""
    def __init__(self, supported_types: list):
        super().__init__(
            detail=f"无效的文件类型。支持的类型: {', '.join(supported_types)}",
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            code="invalid_file_type"
        )
