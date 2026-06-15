import json
import asyncio
from typing import Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor

import lark_oapi as lark
from lark_oapi import ws
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from utils.logger import logger
from config import settings
from utils import get_feishu_client
from agents.feishu_agent import FeishuAgent
from session import get_session_manager


class WsMessageHandler:
    """飞书消息处理器（支持 WebSocket 长连接和 HTTP 回调两种方式）"""

    _instance: Optional["WsMessageHandler"] = None

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
            self._executor = ThreadPoolExecutor(max_workers=4)

    def initialize(self):
        """初始化处理器（同步）"""
        if self._initialized:
            return

        logger.info("初始化消息处理器...")

        self.feishu_client = get_feishu_client()
        self.session_manager = get_session_manager()
        self.agent = FeishuAgent()

        self._initialized = True
        logger.info("消息处理器初始化完成")

    def _run_async(self, coro):
        """在线程池中运行异步函数"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def handle_p2_im_message_receive_v1(self, data: P2ImMessageReceiveV1):
        """
        处理接收消息事件

        Args:
            data: 消息事件数据
        """
        try:
            event = data.event
            if not event:
                logger.warning("事件数据为空")
                return

            message = event.message
            sender = event.sender

            if not message or not sender:
                logger.warning("消息或发送者数据为空")
                return

            msg_type = message.message_type
            chat_type = message.chat_type

            sender_id = sender.sender_id
            open_id = sender_id.open_id if sender_id else ""
            chat_id = message.chat_id

            logger.info(f"收到消息: chat_type={chat_type}, msg_type={msg_type}, open_id={open_id}")

            if msg_type == "text" and message.content:
                try:
                    content = json.loads(message.content)
                    text = content.get("text", "")
                except json.JSONDecodeError:
                    text = message.content

                if not text:
                    logger.warning("消息内容为空")
                    return

                if open_id and chat_id:
                    self._executor.submit(
                        self._run_async,
                        self._process_user_message(open_id, chat_id, text, chat_type or "")
                    )
                else:
                    logger.warning("无法获取发送者ID或聊天ID")

        except Exception as e:
            logger.error(f"处理消息事件出错: {str(e)}", exc_info=True)

    async def _process_user_message(
        self,
        user_id: str,
        chat_id: str,
        text: str,
        chat_type: str
    ):
        """
        处理用户消息

        Args:
            user_id: 用户ID（open_id）
            chat_id: 聊天ID
            text: 消息文本
            chat_type: 聊天类型
        """
        session = self.session_manager.get_session(user_id)

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
            error_msg = "抱歉，处理你的请求时遇到了一些问题。请稍后再试。"
            try:
                await self._send_reply(chat_id, user_id, error_msg)
            except Exception as send_error:
                logger.error(f"发送错误消息失败: {str(send_error)}")

    async def _send_reply(self, chat_id: str, user_id: str, text: str):
        """
        发送回复消息

        Args:
            chat_id: 聊天ID
            user_id: 用户ID
            text: 回复文本
        """
        try:
            content = json.dumps({"text": text}, ensure_ascii=False)

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


def create_event_handler() -> lark.EventDispatcherHandler:
    """
    创建事件处理器（用于 HTTP 回调方式）

    Returns:
        事件处理器实例
    """
    encrypt_key = settings.FEISHU_ENCRYPT_KEY or ""
    verification_token = settings.FEISHU_VERIFICATION_TOKEN or ""

    handler_builder = lark.EventDispatcherHandler.builder(encrypt_key, verification_token)

    ws_handler = WsMessageHandler()
    ws_handler.initialize()

    handler_builder.register_p2_im_message_receive_v1(
        lambda data: ws_handler.handle_p2_im_message_receive_v1(data)
    )

    logger.info("事件处理器创建完成")
    return handler_builder.build()


def create_ws_client() -> ws.Client:
    """
    创建 WebSocket 长连接客户端

    Returns:
        WebSocket 客户端实例
    """
    if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
        raise ValueError("飞书应用配置缺失，请检查 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

    event_handler = create_event_handler()

    client = ws.Client(
        app_id=settings.FEISHU_APP_ID,
        app_secret=settings.FEISHU_APP_SECRET,
        event_handler=event_handler,
        log_level=lark.LogLevel.INFO,
    )

    logger.info(f"WebSocket 客户端创建完成: app_id={settings.FEISHU_APP_ID[:8]}...")
    return client


def run_ws_client():
    """运行 WebSocket 长连接客户端"""
    logger.info("=" * 50)
    logger.info("启动飞书 WebSocket 长连接客户端...")
    logger.info(f"应用 ID: {settings.FEISHU_APP_ID[:8]}...")
    logger.info("连接方式: WebSocket 长连接（飞书官方 SDK）")
    logger.info("=" * 50)

    client = create_ws_client()

    logger.info("正在连接飞书服务器...")
    logger.info("连接成功后，控制台将打印 'connected to wss://xxxxx'")
    logger.info("=" * 50)

    client.start()


def convert_aiohttp_to_raw_request(
    request: "web.Request",
    body: bytes
) -> lark.RawRequest:
    """
    将 aiohttp 请求转换为 SDK 的 RawRequest

    Args:
        request: aiohttp 请求对象
        body: 请求体字节

    Returns:
        RawRequest 实例
    """
    raw_req = lark.RawRequest()
    raw_req.uri = str(request.path)
    raw_req.headers = dict(request.headers)
    raw_req.body = body
    return raw_req


def convert_raw_response_to_aiohttp(raw_resp: lark.RawResponse) -> "web.Response":
    """
    将 SDK 的 RawResponse 转换为 aiohttp 响应

    Args:
        raw_resp: SDK 的 RawResponse 实例

    Returns:
        aiohttp Response 实例
    """
    from aiohttp import web

    headers = raw_resp.headers or {}

    if raw_resp.content:
        return web.Response(
            status=raw_resp.status_code or 200,
            body=raw_resp.content,
            headers=headers
        )
    else:
        return web.Response(
            status=raw_resp.status_code or 200,
            headers=headers
        )


_ws_handler_instance: Optional[WsMessageHandler] = None


def get_ws_message_handler() -> WsMessageHandler:
    """获取消息处理器单例"""
    global _ws_handler_instance
    if _ws_handler_instance is None:
        _ws_handler_instance = WsMessageHandler()
    return _ws_handler_instance
