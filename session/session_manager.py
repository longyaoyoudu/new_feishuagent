from typing import Dict, Optional
from datetime import datetime, timedelta
import asyncio

from utils.logger import logger


class UserSession:
    """用户会话"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.conversation_history = []
        self.last_active_time = datetime.now()
        self._lock = asyncio.Lock()

    async def get_lock(self):
        """获取会话锁（用于防止并发处理同一用户的消息）"""
        return self._lock

    def update_active_time(self):
        """更新最后活跃时间"""
        self.last_active_time = datetime.now()

    def is_expired(self, timeout_hours: int = 24) -> bool:
        """
        检查会话是否过期
        
        Args:
            timeout_hours: 超时时间（小时）
            
        Returns:
            是否过期
        """
        return datetime.now() - self.last_active_time > timedelta(hours=timeout_hours)

    def clear_history(self):
        """清除对话历史"""
        self.conversation_history = []
        logger.info(f"用户 {self.user_id} 对话历史已清除")


class SessionManager:
    """会话管理器"""

    _instance: Optional["SessionManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_sessions"):
            self._sessions: Dict[str, UserSession] = {}
            logger.info("会话管理器初始化完成")

    def get_session(self, user_id: str) -> UserSession:
        """
        获取用户会话，如果不存在则创建
        
        Args:
            user_id: 用户ID（open_id 或 union_id）
            
        Returns:
            用户会话
        """
        if user_id not in self._sessions:
            self._sessions[user_id] = UserSession(user_id)
            logger.info(f"创建新会话: user_id={user_id}")
        
        session = self._sessions[user_id]
        session.update_active_time()
        return session

    def get_or_create_session(self, user_id: str) -> UserSession:
        """获取或创建用户会话（同 get_session）"""
        return self.get_session(user_id)

    def remove_session(self, user_id: str):
        """
        移除用户会话
        
        Args:
            user_id: 用户ID
        """
        if user_id in self._sessions:
            del self._sessions[user_id]
            logger.info(f"移除会话: user_id={user_id}")

    def clear_expired_sessions(self, timeout_hours: int = 24) -> int:
        """
        清除过期的会话
        
        Args:
            timeout_hours: 超时时间（小时）
            
        Returns:
            清除的会话数量
        """
        expired_users = [
            user_id for user_id, session in self._sessions.items()
            if session.is_expired(timeout_hours)
        ]
        
        for user_id in expired_users:
            del self._sessions[user_id]
        
        if expired_users:
            logger.info(f"清除了 {len(expired_users)} 个过期会话")
        
        return len(expired_users)

    def get_active_session_count(self) -> int:
        """获取活跃会话数量"""
        return len(self._sessions)


_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """获取会话管理器单例"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
