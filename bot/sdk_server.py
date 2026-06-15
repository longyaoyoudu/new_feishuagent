"""
使用飞书官方 SDK 的 HTTP 服务器
使用 EventDispatcherHandler 处理事件（自动解密、验签）
"""
from aiohttp import web
import json
from typing import Dict, Any

import lark_oapi as lark

from config import settings
from utils.logger import logger
from bot.ws_handler import (
    create_event_handler,
    convert_aiohttp_to_raw_request,
    convert_raw_response_to_aiohttp,
)


async def handle_webhook(request: web.Request) -> web.Response:
    """
    使用官方 SDK 处理飞书事件回调

    Args:
        request: HTTP 请求

    Returns:
        HTTP 响应
    """
    try:
        body = await request.read()
        logger.debug(f"收到请求: path={request.path}, headers={dict(request.headers)}")

        handler = create_event_handler()

        raw_req = convert_aiohttp_to_raw_request(request, body)

        raw_resp = handler.do(raw_req)

        logger.debug(f"处理完成: status_code={raw_resp.status_code}")

        return convert_raw_response_to_aiohttp(raw_resp)

    except json.JSONDecodeError:
        logger.error("请求体不是有效的 JSON")
        return web.json_response({"error": "Invalid JSON"}, status=400)

    except Exception as e:
        logger.error(f"处理请求出错: {str(e)}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


async def health_check(request: web.Request) -> web.Response:
    """健康检查端点"""
    return web.json_response({
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "sdk_http",
    })


async def webhook_event(request: web.Request) -> web.Response:
    """事件订阅端点"""
    return await handle_webhook(request)


async def create_app() -> web.Application:
    """
    创建 aiohttp 应用

    Returns:
        aiohttp 应用实例
    """
    app = web.Application()

    app.add_routes([
        web.get("/health", health_check),
        web.post("/webhook/event", webhook_event),
    ])

    logger.info("SDK HTTP 服务器应用创建完成")
    return app


def run_sdk_server():
    """运行使用官方 SDK 的 HTTP 服务器"""
    logger.info(f"启动 SDK HTTP 服务器: {settings.HTTP_HOST}:{settings.HTTP_PORT}")
    logger.info("使用飞书官方 SDK 的 EventDispatcherHandler 处理事件")
    logger.info("SDK 特性: 自动解密事件、自动验证 token、自动验签")

    app = create_app()
    web.run_app(
        app,
        host=settings.HTTP_HOST,
        port=settings.HTTP_PORT,
    )
