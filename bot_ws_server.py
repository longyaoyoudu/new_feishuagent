#!/usr/bin/env python3
"""
飞书智能体机器人服务入口（使用官方 SDK WebSocket 长连接）
使用飞书官方 SDK 的 WebSocket 长连接接收事件
"""

from pathlib import Path

from utils import setup_logger, logger
from config import settings
from bot import run_ws_client


def setup_project():
    """项目初始化设置"""
    setup_logger()

    logger.info(f"=" * 50)
    logger.info(f"{settings.APP_NAME} 机器人服务启动中...")
    logger.info(f"版本: {settings.APP_VERSION}")
    logger.info(f"连接方式: WebSocket 长连接（飞书官方 SDK）")
    logger.info(f"=" * 50)

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    logger.info("项目初始化完成")


def main():
    """主函数"""
    setup_project()

    try:
        logger.info("使用飞书官方 SDK 的 WebSocket 长连接接收事件")
        logger.info("")
        logger.info("配置说明：")
        logger.info("  1. 需要在 .env 文件中配置以下参数：")
        logger.info("     - FEISHU_APP_ID: 飞书应用 ID")
        logger.info("     - FEISHU_APP_SECRET: 飞书应用 Secret")
        logger.info("")
        logger.info("  2. 飞书开放平台配置：")
        logger.info("     - 进入应用后台 -> 事件订阅")
        logger.info("     - 选择 '使用长连接接收事件'")
        logger.info("     - 添加事件：'接收消息(im.message.receive_v1)'")
        logger.info("     - 开通权限：'获取用户身份'、'以应用身份发送消息' 等")
        logger.info("")
        logger.info("  3. 注意事项：")
        logger.info("     - WebSocket 长连接方式不需要公网地址")
        logger.info("     - WebSocket 长连接方式不需要内网穿透")
        logger.info("     - WebSocket 长连接方式直接与 HTTP 回调方式互斥，只能选择一种即可")
        logger.info(f"=" * 50)

        run_ws_client()

    except KeyboardInterrupt:
        logger.info("检测到键盘中断，服务停止")
    except Exception as e:
        logger.error(f"服务异常退出: {str(e)}", exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
