#!/usr/bin/env python3
"""
简单的智能体对话测试脚本
"""

import asyncio
import sys
from pathlib import Path

# 确保能够找到项目模块
sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logger, logger
from config import settings


async def main():
    """主函数"""
    setup_logger()
    
    logger.info("=" * 50)
    logger.info("飞书智能体对话测试")
    logger.info(f"应用名称: {settings.APP_NAME}")
    logger.info(f"版本: {settings.APP_VERSION}")
    logger.info(f"模型: {settings.OPENAI_MODEL}")
    logger.info("=" * 50)
    
    try:
        # 导入并初始化智能体
        from agents.feishu_agent import FeishuAgent
        
        logger.info("正在初始化智能体...")
        agent = FeishuAgent()
        logger.info("智能体初始化成功！")
        
        # 简单测试几个预设问题
        test_questions = [
            "你好",
            "你能帮我做什么？",
            "今天天气怎么样？",
        ]
        
        logger.info("\n开始测试对话功能...")
        logger.info("-" * 50)
        
        for i, question in enumerate(test_questions, 1):
            logger.info(f"\n测试 {i}: 用户说: {question}")
            try:
                response = await agent.process_message(question)
                logger.info(f"智能体回复: {response}")
            except Exception as e:
                logger.error(f"测试 {i} 失败: {str(e)}")
        
        logger.info("\n" + "-" * 50)
        logger.info("预设问题测试完成！")
        logger.info("=" * 50)
        
        # 提供交互模式选项
        logger.info("\n您现在可以直接与智能体对话了！")
        logger.info("输入 'exit' 或 'quit' 退出")
        logger.info("-" * 50)
        
        while True:
            try:
                user_input = input("\n用户: ")
                
                if user_input.lower() in ["exit", "quit", "退出"]:
                    logger.info("用户请求退出")
                    break
                
                if not user_input.strip():
                    logger.warning("请输入有效内容")
                    continue
                
                response = await agent.process_message(user_input)
                print(f"智能体: {response}")
                
            except KeyboardInterrupt:
                logger.info("\n检测到键盘中断，退出程序")
                break
            except Exception as e:
                logger.error(f"处理消息时出错: {str(e)}")
                print(f"抱歉，处理您的请求时遇到了一些问题。请重试。")
        
        logger.info("=" * 50)
        logger.info("智能体对话测试结束")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"初始化智能体失败: {str(e)}", exc_info=True)
        print(f"\n错误: 无法初始化智能体。")
        print(f"详细信息: {str(e)}")
        print("\n请检查:")
        print("1. 网络连接是否正常")
        print("2. API密钥是否有效")
        print("3. 所有依赖是否已安装")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
        sys.exit(1)
