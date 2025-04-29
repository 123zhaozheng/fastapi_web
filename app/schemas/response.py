from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel
from pydantic.generics import GenericModel

T = TypeVar('T')

class UnifiedResponseSingle(GenericModel, Generic[T]):
    """统一返回对象 (单个数据)"""
    code: int = 0
    msg: str = "Success"
    data: T

class UnifiedResponsePaginated(GenericModel, Generic[T]):
    """统一返回对象 (分页列表数据)"""
    code: int = 0
    msg: str = "Success"
    data: List[T]
    total: int
    page: Optional[int] = None
    page_size: Optional[int] = None
    total_pages: Optional[int] = None