from gmssl import sm2, sm3, func
from loguru import logger

class SM2Utils:
    """SM2 encryption/decryption utilities compatible with Java implementation."""

    @staticmethod
    def encrypt(public_key_hex: str, data: str) -> str:
        """
        使用SM2算法加密数据，确保输出格式与Java Bouncy Castle兼容。

        Args:
            public_key_hex: SM2公钥的十六进制字符串，必须以"04"开头表示未压缩。
            data: 需要加密的原始数据 (bytes类型)。

        Returns:
            加密后的十六进制字符串 (C1C2C3格式)，可被Java端解密。
        
        Raises:
            ValueError: 如果公钥格式不正确。
            RuntimeError: 如果加密过程中出现错误（如KDF结果为0）。
        """
        data = data.encode('utf-8')
        # 1. 验证公钥格式是否正确
        if not public_key_hex.startswith('04') or len(public_key_hex) != 130:
            raise ValueError("公钥必须是130个字符的十六进制字符串，且以 '04' 开头。")
        
        # 2. 实例化CryptSM2类，它内部会自动处理'04'前缀
        # mode=0 表示C1C2C3顺序，与Java代码一致
        sm2_crypt = sm2.CryptSM2(private_key=None, public_key=public_key_hex, mode=0)
        
        # 3. 将原始数据转为十六进制
        msg_hex = data.hex()
        
        # 4. 生成随机数k
        k = func.random_hex(sm2_crypt.para_len)
        
        # 5. 计算C1 = [k]G = (x1, y1)
        # _kg 方法返回 x, y 坐标拼接的十六进制字符串
        c1_point_hex = sm2_crypt._kg(int(k, 16), sm2_crypt.ecc_table['g'])
        
        # 关键修改：手动添加'04'前缀，以满足Java Bouncy Castle的格式要求
        c1_hex = '04' + c1_point_hex
        
        # 6. 计算 [k]P_A = (x2, y2)，并派生密钥t
        xy_hex = sm2_crypt._kg(int(k, 16), sm2_crypt.public_key)
        # KDF密钥派生函数
        t = sm3.sm3_kdf(xy_hex.encode('utf-8'), len(data))
        
        if int(t, 16) == 0:
            raise RuntimeError("密钥派生函数(KDF)结果为0，加密失败，请重试。")
            
        # 7. 计算C2 = M xor t
        form = f'%0{len(msg_hex)}x'
        c2_hex = form % (int(msg_hex, 16) ^ int(t, 16))
        
        # 8. 计算C3 = Hash(x2 || M || y2)
        x2_hex = xy_hex[0:sm2_crypt.para_len]
        y2_hex = xy_hex[sm2_crypt.para_len:2*sm2_crypt.para_len]
        # 将 x2, 原始消息, y2 拼接为字节串进行哈希
        c3_input_bytes = bytes.fromhex(f'{x2_hex}{msg_hex}{y2_hex}')
        c3_hex = sm3.sm3_hash(list(c3_input_bytes))

        # 9. 拼接C1, C2, C3，并返回大写的十六进制字符串
        encrypted_hex = f"{c1_hex}{c2_hex}{c3_hex}"
        
        return encrypted_hex.upper()

    @staticmethod
    def decrypt(private_key_hex: str, encrypted_data_hex: str) -> bytes | None:
        """Decrypt data with SM2 private key.

        Args:
            private_key_hex: Private key hex string.
            encrypted_data_hex: Cipher text (C1+C2+C3 format).
        Returns:
            Decrypted bytes or None on failure.
        """
        if not private_key_hex or not encrypted_data_hex:
            logger.warning("SM2 decrypt: invalid input")
            return None

        try:
            sm2_crypt = sm2.CryptSM2(private_key=private_key_hex, public_key="")
            return sm2_crypt.decrypt(encrypted_data_hex)
        except Exception as exc:
            logger.error(f"SM2 decrypt error: {exc}")
            return None 