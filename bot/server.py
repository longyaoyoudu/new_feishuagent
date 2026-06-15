from aiohttp import web
import json
from typing import Dict, Any

from config import settings
from utils.logger import logger
from utils import get_event_decryptor, get_event_verifier
from bot import get_message_handler


routes = web.RouteTableDef()


async def handle_webhook(request: web.Request) -> web.Response:
    """
    处理飞书事件回调
    
    Args:
        request: HTTP 请求
        
    Returns:
        HTTP 响应
    """
    try:
        body = await request.json()
        logger.debug(f"收到请求: {body}")

        decryptor = get_event_decryptor()
        verifier = get_event_verifier()

        event_data = decryptor.decrypt_event(body)

        if verifier.is_challenge_request(event_data):
            response = verifier.get_challenge_response(event_data)
            logger.info("响应 URL 验证请求")
            return web.json_response(response)

        if not verifier.verify(event_data):
            logger.warning("事件验证失败，拒绝处理")
            return web.json_response({"error": "Invalid token"}, status=403)

        handler = get_message_handler()
        result = await handler.handle_event(event_data)

        if result:
            return web.json_response(result)
        
        return web.json_response({"status": "success"})

    except json.JSONDecodeError:
        logger.error("请求体不是有效的 JSON")
        return web.json_response({"error": "Invalid JSON"}, status=400)
    
    except Exception as e:
        logger.error(f"处理请求出错: {str(e)}", exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


@routes.get("/health")
async def health_check(request: web.Request) -> web.Response:
    """健康检查端点"""
    return web.json_response({
        "status": "ok",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    })


@routes.post("/webhook/event")
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

    handler = get_message_handler()
    await handler.initialize()

    logger.info("HTTP 服务器应用创建完成")
    return app


def run_server():
    """运行 HTTP 服务器"""
    logger.info(f"启动 HTTP 服务器: {settings.HTTP_HOST}:{settings.HTTP_PORT}")
    
    app = create_app()
    web.run_app(
        app,
        host=settings.HTTP_HOST,
        port=settings.HTTP_PORT,
    )
