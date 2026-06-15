#!/usr/bin/env python3
"""
飞书智能体项目主入口
使用 Langchain 框架构建，支持日程提醒、云文档总结、用户对话等功能
"""

import asyncio
from pathlib import Path

from utils import setup_logger, logger
from config import settings


def setup_project():
    """项目初始化设置"""
    setup_logger()

    logger.info(f"=" * 50)
    logger.info(f"{settings.APP_NAME} 启动中...")
    logger.info(f"版本: {settings.APP_VERSION}")
    logger.info(f"=" * 50)

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    logger.info("项目初始化完成")


async def run_agent():
    """运行智能体主逻辑"""
    try:
        logger.info("智能体核心逻辑开始执行")

        from agents.feishu_agent import FeishuAgent

        agent = FeishuAgent()

        logger.info("智能体初始化完成，等待用户输入...")

        while True:
            user_input = input("\n用户: ")

            if user_input.lower() in ["exit", "quit", "退出"]:
                logger.info("用户请求退出，智能体停止运行")
                print("智能体: 再见！")
                break

            response = await agent.process_message(user_input)
            print(f"智能体: {response}")

    except KeyboardInterrupt:
        logger.info("检测到键盘中断，智能体停止运行")
    except Exception as e:
        logger.error(f"智能体运行出错: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    setup_project()

    try:
        asyncio.run(run_agent())
    except Exception as e:
        logger.error(f"程序异常退出: {str(e)}", exc_info=True)
        exit(1)
