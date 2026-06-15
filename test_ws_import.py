#!/usr/bin/env python3
"""测试长连接模块导入"""

import sys
sys.path.insert(0, '.')

try:
    from config import settings
    print("✓ config.settings 导入成功")
except Exception as e:
    print(f"✗ config.settings 导入失败: {e}")

try:
    import lark_oapi as lark
    from lark_oapi import ws
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
    print("✓ lark_oapi SDK 导入成功")
except Exception as e:
    print(f"✗ lark_oapi SDK 导入失败: {e}")

try:
    from bot.ws_handler import (
        WsMessageHandler,
        create_event_handler,
        create_ws_client,
        run_ws_client,
    )
    print("✓ bot.ws_handler 导入成功")
except Exception as e:
    print(f"✗ bot.ws_handler 导入失败: {e}")

try:
    from session import get_session_manager
    print("✓ session 导入成功")
except Exception as e:
    print(f"✗ session 导入失败: {e}")

try:
    from agents.feishu_agent import FeishuAgent
    print("✓ agents.feishu_agent 导入成功")
except Exception as e:
    print(f"✗ agents.feishu_agent 导入失败: {e}")

print("\n导入测试完成!")
