import base64
import hashlib
import json
from typing import Optional, Dict, Any

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from config import settings
from utils.logger import logger


class EventDecryptor:
    """飞书事件解密工具"""

    def __init__(self, encrypt_key: Optional[str] = None):
        self.encrypt_key = encrypt_key or settings.FEISHU_ENCRYPT_KEY
        self._key: Optional[bytes] = None
        
        if self.encrypt_key:
            self._key = hashlib.sha256(self.encrypt_key.encode()).digest()[:16]
            logger.info("事件解密器初始化完成")
        else:
            logger.warning("未配置加密密钥，将不进行解密")

    def decrypt(self, encrypt: str) -> str:
        """
        解密飞书事件数据
        
        Args:
            encrypt: 加密的 base64 字符串
            
        Returns:
            解密后的 JSON 字符串
        """
        if not self._key:
            logger.warning("未配置加密密钥，直接返回原始数据")
            return encrypt

        try:
            encrypted_data = base64.b64decode(encrypt)
            
            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]
            
            cipher = AES.new(self._key, AES.MODE_CBC, iv)
            decrypted_data = unpad(cipher.decrypt(ciphertext), AES.block_size)
            
            result = decrypted_data.decode('utf-8')
            logger.debug("事件数据解密成功")
            return result
            
        except Exception as e:
            logger.error(f"事件解密失败: {str(e)}")
            raise ValueError(f"事件解密失败: {str(e)}")

    def decrypt_event(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """
        解密飞书事件请求体
        
        Args:
            request_body: 飞书 POST 请求的 JSON body
            
        Returns:
            解密后的事件数据
        """
        if "encrypt" not in request_body:
            logger.debug("请求体未加密，直接返回")
            return request_body

        encrypted = request_body["encrypt"]
        decrypted_str = self.decrypt(encrypted)
        
        try:
            decrypted_data = json.loads(decrypted_str)
            return decrypted_data
        except json.JSONDecodeError as e:
            logger.error(f"解密后的数据不是有效的 JSON: {str(e)}")
            raise ValueError(f"解密后的数据不是有效的 JSON: {str(e)}")


class EventVerifier:
    """飞书事件验证工具"""

    def __init__(self, verification_token: Optional[str] = None):
        self.verification_token = verification_token or settings.FEISHU_VERIFICATION_TOKEN
        
        if self.verification_token:
            logger.info("事件验证器初始化完成")
        else:
            logger.warning("未配置验证令牌，将跳过验证")

    def verify(self, request_body: Dict[str, Any]) -> bool:
        """
        验证事件请求的令牌
        
        Args:
            request_body: 请求体
            
        Returns:
            验证是否通过
        """
        if not self.verification_token:
            return True

        token = request_body.get("token")
        if token and token == self.verification_token:
            logger.debug("事件令牌验证通过")
            return True
        
        header = request_body.get("header", {})
        token = header.get("token")
        if token and token == self.verification_token:
            logger.debug("事件令牌验证通过（从 header）")
            return True

        logger.warning(f"事件令牌验证失败，期望: {self.verification_token[:8]}..., 实际: {token}")
        return False

    def is_challenge_request(self, request_body: Dict[str, Any]) -> bool:
        """
        检查是否是 URL 验证请求
        
        Args:
            request_body: 请求体
            
        Returns:
            是否是 challenge 请求
        """
        return "challenge" in request_body and "type" in request_body and request_body.get("type") == "url_verification"

    def get_challenge_response(self, request_body: Dict[str, Any]) -> Dict[str, str]:
        """
        获取 URL 验证的响应
        
        Args:
            request_body: 请求体
            
        Returns:
            包含 challenge 的响应
        """
        challenge = request_body.get("challenge", "")
        logger.info(f"收到 URL 验证请求，challenge: {challenge[:8]}...")
        return {"challenge": challenge}


_event_decryptor: Optional[EventDecryptor] = None
_event_verifier: Optional[EventVerifier] = None


def get_event_decryptor() -> EventDecryptor:
    """获取事件解密器单例"""
    global _event_decryptor
    if _event_decryptor is None:
        _event_decryptor = EventDecryptor()
    return _event_decryptor


def get_event_verifier() -> EventVerifier:
    """获取事件验证器单例"""
    global _event_verifier
    if _event_verifier is None:
        _event_verifier = EventVerifier()
    return _event_verifier
