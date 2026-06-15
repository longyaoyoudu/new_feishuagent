#!/usr/bin/env python3
"""
测试云文档模块的功能
用于验证文档读取、意图分类等功能
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils import setup_logger, logger
from config import settings
from modules.document_module import DocumentModule
from agents.feishu_agent import FeishuAgent
from utils import get_feishu_client


async def test_intent_classification():
    """测试意图分类"""
    print("\n" + "="*60)
    print("测试 1: 意图分类")
    print("="*60)
    
    test_cases = [
        "帮我总结这个文档：https://feishu.cn/docx/abc123def45",
        "读取文档ID为 xyz789 的内容",
        "这个文档讲了什么？https://example.feishu.cn/wiki/test123",
        "今天天气怎么样？",
        "查看我明天的日程",
    ]
    
    try:
        agent = FeishuAgent()
        
        for test_input in test_cases:
            print(f"\n输入: {test_input}")
            intent = await agent._classify_intent(test_input)
            print(f"分类结果: {intent}")
            
            # 验证
            if "文档" in test_input or "docx" in test_input or "wiki" in test_input:
                expected = "document"
            elif "日程" in test_input:
                expected = "calendar"
            else:
                expected = "chat"
                
            if intent == expected:
                print(f"✅ 分类正确")
            else:
                print(f"⚠️  分类可能有问题，预期: {expected}")
                
    except Exception as e:
        logger.error(f"意图分类测试失败: {str(e)}", exc_info=True)
        print(f"❌ 测试失败: {str(e)}")


async def test_token_extraction():
    """测试文档token提取"""
    print("\n" + "="*60)
    print("测试 2: 文档Token提取")
    print("="*60)
    
    test_cases = [
        "帮我总结这个文档：https://feishu.cn/docx/abc123def456xyz",
        "读取文档 https://example.feishu.cn/wiki/wik123abc456xyz",
        "文档ID: doc789xyz123abc",
        "https://myspace.feishu.cn/doc/doc987cba654zyx",
        "今天天气怎么样？",
    ]
    
    try:
        module = DocumentModule()
        
        for test_input in test_cases:
            print(f"\n输入: {test_input}")
            token_info = module._extract_document_token(test_input)
            
            if token_info:
                token = token_info.get("token")
                token_type = token_info.get("type")
                print(f"提取结果: token={token}, type={token_type}")
                
                # 验证类型
                if "wiki" in test_input and token_type == "wiki":
                    print(f"✅ 类型正确 (wiki)")
                elif "docx" in test_input or "doc/" in test_input:
                    if token_type == "document":
                        print(f"✅ 类型正确 (document)")
                    else:
                        print(f"⚠️  类型可能有问题")
                else:
                    print(f"✅ 提取成功")
            else:
                if "天气" in test_input:
                    print(f"✅ 正确地没有提取到token（不是文档请求）")
                else:
                    print(f"❌ 没有提取到token")
                    
    except Exception as e:
        logger.error(f"Token提取测试失败: {str(e)}", exc_info=True)
        print(f"❌ 测试失败: {str(e)}")


async def test_api_connection():
    """测试飞书API连接"""
    print("\n" + "="*60)
    print("测试 3: 飞书API连接测试")
    print("="*60)
    
    try:
        client = get_feishu_client()
        print(f"飞书客户端初始化成功")
        print(f"App ID: {settings.FEISHU_APP_ID[:8]}...")
        
        # 测试获取access_token
        print("\n测试获取 access_token...")
        try:
            # 访问私有方法来测试
            access_token = await client._get_access_token()
            if access_token:
                print(f"✅ access_token 获取成功 (长度: {len(access_token)})")
            else:
                print(f"❌ access_token 获取失败")
        except Exception as e:
            print(f"❌ access_token 获取失败: {str(e)}")
            logger.error(f"获取 access_token 失败: {str(e)}", exc_info=True)
            
    except Exception as e:
        logger.error(f"API连接测试失败: {str(e)}", exc_info=True)
        print(f"❌ 测试失败: {str(e)}")


async def test_document_reading():
    """测试文档读取（需要用户提供有效的文档token）"""
    print("\n" + "="*60)
    print("测试 4: 文档读取测试（需要有效token）")
    print("="*60)
    
    print("\n请输入一个有效的飞书文档链接或token进行测试：")
    print("（直接按回车跳过此测试）")
    
    try:
        user_input = input("文档链接或token: ").strip()
        
        if not user_input:
            print("跳过文档读取测试")
            return
        
        # 获取飞书客户端
        feishu_client = get_feishu_client()
        
        # 初始化 DocumentModule 并传入 feishu_client
        module = DocumentModule(feishu_client=feishu_client)
        
        # 测试token提取
        token_info = module._extract_document_token(user_input)
        
        if not token_info:
            print(f"❌ 无法从输入中提取文档token")
            return
        
        token = token_info.get("token")
        token_type = token_info.get("type")
        
        print(f"\n提取到: token={token}, type={token_type}")
        
        # 测试实际读取
        print("\n尝试读取文档内容...")
        
        try:
            response = await module._read_document(token, token_type)
            print(f"\n返回结果：")
            print("-"*60)
            print(response[:500] if len(response) > 500 else response)
            if len(response) > 500:
                print(f"\n...（结果已截断，总长度: {len(response)} 字符）")
            print("-"*60)
            
            # 分析结果
            if "失败" in response or "错误" in response or "无法" in response:
                print(f"❌ 文档读取可能失败")
                print(f"\n💡 提示：请检查以下几点：")
                print(f"   1. 飞书开放平台是否开通了以下权限：")
                print(f"      - docx:document:readonly")
                print(f"      - docx:document.raw_content:readonly")
                print(f"      - wiki:wiki:readonly (如果是知识库文档)")
                print(f"   2. 文档是否通过右上角「...」->「更多」->「添加文档应用」授权给应用")
                print(f"   3. 文档token是否正确")
            else:
                print(f"✅ 文档读取成功！")
                
        except Exception as e:
            logger.error(f"文档读取测试失败: {str(e)}", exc_info=True)
            print(f"❌ 读取失败: {str(e)}")
            
    except Exception as e:
        logger.error(f"文档读取测试异常: {str(e)}", exc_info=True)
        print(f"❌ 测试失败: {str(e)}")


async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("飞书智能体 - 云文档模块测试")
    print("="*60)
    
    # 初始化
    setup_logger()
    logger.info("开始测试云文档模块")
    
    # 检查配置
    print(f"\n配置检查：")
    print(f"  FEISHU_APP_ID: {settings.FEISHU_APP_ID[:8]}..." if settings.FEISHU_APP_ID else "  FEISHU_APP_ID: 未配置")
    print(f"  FEISHU_APP_SECRET: {'已配置' if settings.FEISHU_APP_SECRET else '未配置'}")
    print(f"  OPENAI_API_KEY: {'已配置' if settings.OPENAI_API_KEY else '未配置'}")
    print(f"  OPENAI_MODEL: {settings.OPENAI_MODEL}")
    
    # 运行测试
    await test_intent_classification()
    await test_token_extraction()
    await test_api_connection()
    await test_document_reading()
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)
    
    print("\n💡 如果测试发现问题，请检查：")
    print("   1. .env 文件中的配置是否正确")
    print("   2. 飞书开放平台的应用权限是否开通")
    print("   3. 文档是否授权给应用访问")
    print("   4. 查看 logs/feishu_agent.log 获取详细错误信息")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n测试发生异常: {str(e)}")
        logger.error(f"测试异常: {str(e)}", exc_info=True)
