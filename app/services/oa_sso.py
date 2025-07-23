import httpx
from loguru import logger
from app.config import settings
from app.utils.sm2_utils import SM2Utils  # reference will update path if needed

class OASsoException(Exception):
    """Custom exception for OA SSO errors"""
    pass


class OASsoService:
    """Service to interact with OA SSO for user authentication"""

    def __init__(self,
                 base_url: str | None = None,
                 public_key: str | None = None,
                 channel_id: str | None = None):
        self.base_url = base_url or settings.OA_SSO_BASE_URL.rstrip("/")
        self.public_key = public_key or settings.OA_SSO_PUBLIC_KEY
        self.channel_id = channel_id or settings.OA_SSO_CHANNEL_ID
        self.client = httpx.AsyncClient(timeout=10.0)

        if not self.public_key:
            logger.warning("OA_SSO_PUBLIC_KEY is not set. OA SSO will not work correctly.")

    async def close(self):
        await self.client.aclose()

    async def get_workcode(self, token: str) -> str:
        """Retrieve workcode from OA SSO using the token provided by frontend."""
        if not token:
            raise OASsoException("Token must not be empty")

        current_token = token
        for attempt in range(2):
            plaintext = f"{self.channel_id}-{current_token}"
            logger.debug(f"OA SSO plaintext (attempt {attempt + 1}): {plaintext}")

            encrypted_hex = SM2Utils.encrypt(self.public_key, plaintext)
            if not encrypted_hex:
                raise OASsoException("Failed to encrypt token for OA SSO")

            url = (f"{self.base_url}/api/nsh/ssotoken/getssotoken?channelid="
                   f"{self.channel_id}&Encrypted={encrypted_hex}")
            logger.debug(f"Requesting OA SSO URL (attempt {attempt + 1}): {url}")

            try:
                response = await self.client.post(url)
                response.raise_for_status()
            except httpx.RequestError as exc:
                logger.error(f"Error on OA SSO request (attempt {attempt + 1}): {exc}")
                raise OASsoException("请求 OA SSO 接口失败") from exc
            except httpx.HTTPStatusError as exc:
                logger.error(
                    f"OA SSO HTTP error (attempt {attempt + 1}): {exc.response.status_code}"
                )
                raise OASsoException("OA SSO 接口返回错误") from exc

            data = response.json()
            logger.debug(f"OA SSO response data (attempt {attempt + 1}): {data}")

            status = data.get("status")

            if status == "0":
                workcode = data.get("workcode")
                if not workcode:
                    raise OASsoException("OA SSO 返回数据缺少工号")
                return workcode

            if status == "1":
                if attempt == 0:  # First attempt
                    new_token = data.get("token")
                    if not new_token:
                        raise OASsoException("OA SSO status is 1 but no newtoken provided")
                    current_token = new_token
                    logger.info("OA SSO token expired, retrying with a new token.")
                    continue
                else:  # Second attempt also failed with status 1
                    msg = data.get("message", "OA SSO 认证在第二次尝试后失败")
                    raise OASsoException(msg)
            
            # Other status code
            msg = data.get("message", "OA SSO 认证失败")
            raise OASsoException(msg)

        raise OASsoException("OA SSO 认证在两次尝试后仍然失败") 