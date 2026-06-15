from abc import ABC, abstractmethod
from typing import List, Any, Dict, Optional
from langchain_core.messages import BaseMessage


class BaseModule(ABC):
    """功能模块基类"""

    def __init__(self, name: str, description: str):
        """
        初始化功能模块

        Args:
            name: 模块名称
            description: 模块描述
        """
        self.name = name
        self.description = description
        self._enabled = True

    @abstractmethod
    async def execute(
        self,
        user_input: str,
        conversation_history: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        执行模块功能

        Args:
            user_input: 用户输入
            conversation_history: 对话历史
            **kwargs: 其他参数

        Returns:
            执行结果字符串
        """
        pass

    @property
    def enabled(self) -> bool:
        """获取模块启用状态"""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        """设置模块启用状态"""
        self._enabled = value

    def get_info(self) -> Dict[str, Any]:
        """获取模块信息"""
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
        }

    def __str__(self) -> str:
        return f"{self.name}: {self.description}"
