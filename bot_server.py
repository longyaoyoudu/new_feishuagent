#!/usr/bin/env python3
"""
飞书智能体机器人服务入口
启动 HTTP 服务器接收飞书事件回调
"""

import asyncio
from pathlib import Path

from utils import setup_logger, logger
from config import settings
from bot import run_server


def setup_project():
    """项目初始化设置"""
    setup_logger()

    logger.info(f"=" * 50)
    logger.info(f"{settings.APP_NAME} 机器人服务启动中...")
    logger.info(f"版本: {settings.APP_VERSION}")
    logger.info(f"=" * 50)

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    logger.info("项目初始化完成")


def main():
    """主函数"""
    setup_project()

    try:
        logger.info(f"机器人服务监听地址: http://{settings.HTTP_HOST}:{settings.HTTP_PORT}")
        logger.info(f"事件回调地址: http://<你的域名>:{settings.HTTP_PORT}/webhook/event")
        logger.info("请在飞书开放平台配置事件订阅的请求地址")
        logger.info(f"=" * 50)

        run_server()

    except KeyboardInterrupt:
        logger.info("检测到键盘中断，服务停止")
    except Exception as e:
        logger.error(f"服务异常退出: {str(e)}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
