import random
import string
import time
import uuid
from io import BytesIO
from typing import Tuple, Dict

from captcha.image import ImageCaptcha

class CaptchaManager:
    """
    验证码管理器

    负责生成、存储和验证验证码。
    使用内存缓存来存储验证码，并设置过期时间。
    """
    def __init__(self, expires_in: int = 180):
        self.expires_in = expires_in  # Captcha expires in 3 minutes
        self.cache: Dict[str, Tuple[str, float]] = {}
        self.image_captcha = ImageCaptcha()

    def _generate_code(self, length: int = 4) -> str:
        """生成指定长度的随机数字验证码"""
        return "".join(random.choices(string.digits, k=length))

    def generate(self) -> Tuple[str, bytes]:
        """
        生成一个新的验证码。

        Returns:
            Tuple[str, bytes]: 一个元组，包含验证码 ID 和 PNG 图像的字节流。
        """
        code = self._generate_code()
        captcha_id = str(uuid.uuid4())
        
        # Store in cache with expiration time
        self.cache[captcha_id] = (code, time.time() + self.expires_in)
        
        # Generate image
        image_data = self.image_captcha.generate(code)
        
        # Return as bytes
        return captcha_id, image_data.read()

    def verify(self, captcha_id: str, code: str) -> bool:
        """
        验证验证码是否正确。

        验证后，无论成功与否，都会从缓存中删除该验证码。

        Args:
            captcha_id: 验证码的唯一标识符。
            code: 用户输入的验证码。

        Returns:
            bool: 如果验证码正确且未过期，则返回 True，否则返回 False。
        """
        # Clean up expired captchas first
        self._cleanup_expired()

        if captcha_id not in self.cache:
            return False

        stored_code, expiration_time = self.cache.pop(captcha_id)

        if time.time() > expiration_time:
            return False

        return stored_code == code

    def _cleanup_expired(self):
        """从缓存中删除所有过期的验证码。"""
        now = time.time()
        expired_ids = [
            captcha_id for captcha_id, (_, expiration_time) in self.cache.items()
            if now > expiration_time
        ]
        for captcha_id in expired_ids:
            del self.cache[captcha_id]

# 创建一个全局的 CaptchaManager 实例
captcha_manager = CaptchaManager()