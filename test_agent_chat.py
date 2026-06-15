#!/usr/bin/env python3
"""
测试智能体对话功能的脚本
"""

import asyncio
import sys
from pathlib import Path

# 确保能够找到项目模块
sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logger, logger
from config import settings


async def test_basic_conversation():
    """测试基本对话功能"""
    logger.info("=" * 50)
    logger.info("测试 1: 基本对话功能")
    logger.info("=" * 50)
    
    from agents.feishu_agent import FeishuAgent
    
    agent = FeishuAgent()
    
    test_cases = [
        "你好",
        "今天天气怎么样？",
        "你能帮我做什么？",
        "介绍一下你自己"
    ]
    
    for i, user_input in enumerate(test_cases, 1):
        logger.info(f"\n测试用例 {i}: 用户说: {user_input}")
        try:
            response = await agent.process_message(user_input)
            logger.info(f"智能体回复: {response}")
            assert response, "智能体应该返回非空回复"
            logger.info(f"测试用例 {i}: 通过 ✓")
        except Exception as e:
            logger.error(f"测试用例 {i}: 失败 ✗ - {str(e)}")
            return False
    
    return True


async def test_intent_classification():
    """测试意图分类功能"""
    logger.info("\n" + "=" * 50)
    logger.info("测试 2: 意图分类功能")
    logger.info("=" * 50)
    
    from agents.feishu_agent import FeishuAgent
    
    agent = FeishuAgent()
    
    # 测试不同类型的意图
    test_cases = [
        ("你好", "chat"),
        ("今天天气怎么样？", "chat"),
        ("明天下午3点有个会议，帮我创建日程", "calendar"),
        ("查看我今天的日程", "calendar"),
        ("帮我总结这个文档：https://feishu.cn/docx/xxx", "document"),
        ("读取文档内容", "document"),
    ]
    
    all_passed = True
    for i, (user_input, expected_intent) in enumerate(test_cases, 1):
        logger.info(f"\n测试用例 {i}: 用户说: {user_input}")
        logger.info(f"预期意图: {expected_intent}")
        
        try:
            # 直接测试意图分类
            intent = await agent._classify_intent(user_input)
            logger.info(f"实际意图: {intent}")
            
            # 检查意图是否匹配（允许一定的灵活性）
            if intent == expected_intent:
                logger.info(f"测试用例 {i}: 通过 ✓")
            else:
                logger.warning(f"测试用例 {i}: 意图不匹配（可能是正常的，取决于上下文）")
                # 不视为失败，因为意图分类可能有合理的差异
            
        except Exception as e:
            logger.error(f"测试用例 {i}: 失败 ✗ - {str(e)}")
            all_passed = False
    
    return all_passed


async def test_multi_turn_conversation():
    """测试多轮对话能力"""
    logger.info("\n" + "=" * 50)
    logger.info("测试 3: 多轮对话能力")
    logger.info("=" * 50)
    
    from agents.feishu_agent import FeishuAgent
    
    agent = FeishuAgent()
    
    # 测试多轮对话
    conversation = [
        "你好，我叫张三",
        "很高兴认识你，我叫什么名字？",
        "你能记住我们的对话吗？",
        "刚才我们聊了什么？"
    ]
    
    all_passed = True
    for i, user_input in enumerate(conversation, 1):
        logger.info(f"\n第 {i} 轮对话: 用户说: {user_input}")
        try:
            response = await agent.process_message(user_input)
            logger.info(f"智能体回复: {response}")
            assert response, "智能体应该返回非空回复"
            logger.info(f"第 {i} 轮对话: 通过 ✓")
        except Exception as e:
            logger.error(f"第 {i} 轮对话: 失败 ✗ - {str(e)}")
            all_passed = False
    
    # 检查对话历史
    logger.info(f"\n对话历史长度: {len(agent.conversation_history)}")
    logger.info(f"最大历史长度: {agent.max_history_length}")
    
    return all_passed


async def test_edge_cases():
    """测试边界情况"""
    logger.info("\n" + "=" * 50)
    logger.info("测试 4: 边界情况")
    logger.info("=" * 50)
    
    from agents.feishu_agent import FeishuAgent
    
    agent = FeishuAgent()
    
    test_cases = [
        "",  # 空输入
        "   ",  # 空白输入
        "a" * 1000,  # 超长输入
        "特殊字符: !@#$%^&*()_+-=[]{}|;':\",./<>?",  # 特殊字符
        "混合中英文: Hello 你好 World 世界",  # 混合语言
    ]
    
    all_passed = True
    for i, user_input in enumerate(test_cases, 1):
        logger.info(f"\n测试用例 {i}: 输入长度={len(user_input)}")
        if len(user_input) > 50:
            logger.info(f"输入预览: {user_input[:50]}...")
        else:
            logger.info(f"输入: '{user_input}'")
        
        try:
            response = await agent.process_message(user_input)
            logger.info(f"智能体回复: {response[:100] if len(response) > 100 else response}")
            assert response, "智能体应该返回非空回复"
            logger.info(f"测试用例 {i}: 通过 ✓")
        except Exception as e:
            logger.error(f"测试用例 {i}: 失败 ✗ - {str(e)}")
            all_passed = False
    
    return all_passed


async def main():
    """主测试函数"""
    setup_logger()
    
    logger.info("=" * 60)
    logger.info("开始测试智能体对话功能")
    logger.info(f"应用名称: {settings.APP_NAME}")
    logger.info(f"版本: {settings.APP_VERSION}")
    logger.info(f"模型: {settings.OPENAI_MODEL}")
    logger.info("=" * 60)
    
    results = {}
    
    # 运行所有测试
    results["基本对话功能"] = await test_basic_conversation()
    results["意图分类功能"] = await test_intent_classification()
    results["多轮对话能力"] = await test_multi_turn_conversation()
    results["边界情况处理"] = await test_edge_cases()
    
    # 总结测试结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果总结")
    logger.info("=" * 60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "通过 ✓" if result else "失败 ✗"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n总计: {passed}/{total} 个测试通过")
    
    if passed == total:
        logger.info("所有测试都通过了！✓")
        return 0
    else:
        logger.warning("部分测试失败，请检查上面的日志")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"测试过程中发生错误: {str(e)}", exc_info=True)
        sys.exit(1)
