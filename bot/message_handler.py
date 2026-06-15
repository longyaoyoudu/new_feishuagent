import json
from typing import Dict, Any, Optional
import asyncio

from utils.logger import logger
from utils import get_feishu_client, clean_model_output
from agents.feishu_agent import FeishuAgent
from session import get_session_manager


class MessageHandler:
    """飞书消息处理器"""

    _instance: Optional["MessageHandler"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = False
            self.agent: Optional[FeishuAgent] = None
            self.feishu_client = None
            self.session_manager = None
            self._processing_tasks: Dict[str, asyncio.Task] = {}

    async def initialize(self):
        """初始化处理器"""
        if self._initialized:
            return

        logger.info("初始化消息处理器...")

        self.feishu_client = get_feishu_client()
        self.session_manager = get_session_manager()
        self.agent = FeishuAgent()

        self._initialized = True
        logger.info("消息处理器初始化完成")

    async def handle_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理飞书事件
        
        Args:
            event_data: 解密后的事件数据
            
        Returns:
            响应数据（如果需要）
        """
        if not self._initialized:
            await self.initialize()

        header = event_data.get("header", {})
        event_type = header.get("event_type", "")

        logger.info(f"收到事件: {event_type}")

        if event_type == "im.message.receive_v1":
            return await self._handle_message_event(event_data)
        
        elif event_type == "p2p_chat_create":
            return await self._handle_chat_create(event_data)

        logger.debug(f"未处理的事件类型: {event_type}")
        return None

    async def _handle_message_event(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理消息接收事件
        
        Args:
            event_data: 事件数据
            
        Returns:
            响应数据
        """
        try:
            event = event_data.get("event", {})
            message = event.get("message", {})
            sender = event.get("sender", {})

            msg_type = message.get("msg_type", "")
            chat_type = message.get("chat_type", "")

            sender_id = sender.get("sender_id", {})
            open_id = sender_id.get("open_id", "")
            union_id = sender_id.get("union_id", "")
            user_id = sender_id.get("user_id", "")

            chat_id = message.get("chat_id", "")

            logger.info(f"收到消息: chat_type={chat_type}, msg_type={msg_type}, open_id={open_id}")

            if msg_type == "text":
                content_str = message.get("content", "{}")
                try:
                    content = json.loads(content_str)
                    text = content.get("text", "")
                except json.JSONDecodeError:
                    text = content_str

                if not text:
                    logger.warning("消息内容为空")
                    return None

                if open_id:
                    asyncio.create_task(
                        self._process_user_message(open_id, chat_id, text, chat_type)
                    )
                else:
                    logger.warning("无法获取发送者ID")

            return None

        except Exception as e:
            logger.error(f"处理消息事件出错: {str(e)}", exc_info=True)
            return None

    async def _handle_chat_create(self, event_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        处理首次聊天事件
        
        Args:
            event_data: 事件数据
            
        Returns:
            响应数据
        """
        try:
            event = event_data.get("event", {})
            chat_id = event.get("chat_id", "")
            operator = event.get("operator", {})
            open_id = operator.get("open_id", "")

            logger.info(f"用户首次创建聊天: chat_id={chat_id}, open_id={open_id}")

            welcome_msg = "你好！我是飞书智能助手，可以帮助你管理日程、总结云文档、回答问题等。有什么我可以帮你的吗？"
            
            if chat_id and open_id:
                await self._send_reply(chat_id, open_id, welcome_msg)

            return None

        except Exception as e:
            logger.error(f"处理聊天创建事件出错: {str(e)}", exc_info=True)
            return None

    async def _process_user_message(
        self, 
        user_id: str, 
        chat_id: str, 
        text: str, 
        chat_type: str
    ):
        """
        处理用户消息（异步任务）
        
        Args:
            user_id: 用户ID（open_id）
            chat_id: 聊天ID
            text: 消息文本
            chat_type: 聊天类型（p2p 或 group）
        """
        session = self.session_manager.get_session(user_id)
        
        async with session._lock:
            try:
                logger.info(f"处理用户消息: user_id={user_id}, text={text[:50]}...")

                if not self.agent:
                    self.agent = FeishuAgent()

                original_history = self.agent.conversation_history
                self.agent.conversation_history = session.conversation_history

                try:
                    response = await self.agent.process_message(text, chat_id=chat_id, chat_type=chat_type)
                finally:
                    session.conversation_history = self.agent.conversation_history
                    self.agent.conversation_history = original_history

                logger.info(f"生成回复: {response[:50]}...")

                await self._send_reply(chat_id, user_id, response)

            except Exception as e:
                logger.error(f"处理用户消息出错: {str(e)}", exc_info=True)
                error_msg = f"抱歉，处理你的请求时遇到了一些问题。请稍后再试。"
                try:
                    await self._send_reply(chat_id, user_id, error_msg)
                except Exception as send_error:
                    logger.error(f"发送错误消息失败: {str(send_error)}")

    async def _send_reply(self, chat_id: str, user_id: str, text: str):
        """
        发送回复消息
        
        Args:
            chat_id: 聊天ID
            user_id: 用户ID（open_id）
            text: 回复文本
        """
        try:
            cleaned_text = clean_model_output(text)
            content = json.dumps({"text": cleaned_text}, ensure_ascii=False)

            result = await self.feishu_client.send_message(
                receive_id=chat_id,
                msg_type="text",
                content=content,
                receive_id_type="chat_id",
            )

            if result.get("success"):
                logger.info(f"消息发送成功: message_id={result.get('message_id')}")
            else:
                logger.warning(f"消息发送可能失败: {result}")

        except Exception as e:
            logger.error(f"发送消息出错: {str(e)}", exc_info=True)
            raise


_message_handler: Optional[MessageHandler] = None


def get_message_handler() -> MessageHandler:
    """获取消息处理器单例"""
    global _message_handler
    if _message_handler is None:
        _message_handler = MessageHandler()
    return _message_handler
