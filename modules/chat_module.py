from typing import List, Any, Dict, Optional
from datetime import datetime
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from config import settings
from utils import logger, clean_model_output
from modules.base_module import BaseModule


class ChatModule(BaseModule):
    """用户对话模块"""

    def __init__(self):
        """
        初始化用户对话模块
        """
        super().__init__(
            name="chat",
            description="用户对话模块，支持日常对话、问答、闲聊等功能"
        )
        self._setup_llm()

    def _setup_llm(self):
        """设置大语言模型"""
        if not settings.OPENAI_API_KEY:
            self.llm = None
            return

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=0.7,
        )

    async def execute(
        self,
        user_input: str,
        conversation_history: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        执行对话功能

        Args:
            user_input: 用户输入
            conversation_history: 对话历史
            **kwargs: 其他参数

        Returns:
            执行结果字符串
        """
        logger.info(f"对话模块处理用户输入: {user_input}")

        if self.llm is None:
            return "抱歉，大语言模型未配置，无法进行对话。请先配置 OPENAI_API_KEY。"

        try:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            day_of_week = datetime.now().strftime("%A")

            system_prompt = f"""你是一个温暖、贴心的智能助手，名字叫飞书小助手 🌟。

当前时间：{current_time} ({day_of_week})
应用名称：{settings.APP_NAME}
版本：{settings.APP_VERSION}

我是你的工作伙伴，更是可以聊天的朋友！我可以帮助你：
1. 进行日常对话和闲聊 💬 - 陪你聊聊生活、分享想法
2. 回答各种问题 ❓ - 知识问答、信息查询
3. 提供建议和帮助 💡 - 当你需要建议时，我会认真思考并给出贴心的建议
4. 当你提到日程、日历、会议、提醒时，我会引导你使用日程管理功能 📅
5. 当你提到文档、云文档、总结时，我会引导你提供文档链接或ID 📄
6. 当你提到表格、多维表格、电子表格、记录、批量操作时，我会引导你使用电子表格管理功能 📊

【重要能力 - 电子表格管理】
我实际上可以帮你创建和管理飞书多维表格！具体来说：
- ✅ **创建多维表格**：帮你创建新的多维表格，包括定义字段结构
- ✅ **写入数据**：添加单条记录或批量添加多条记录
- ✅ **读取数据**：查询表格中的记录内容
- ✅ **更新数据**：修改已有记录的内容
- ✅ **批量操作**：批量添加或更新多条记录

当你需要操作电子表格时，请直接告诉我，我会帮你处理！例如：
- "创建一个客户管理表格，包含姓名、电话、状态字段"
- "在表格中添加一条记录：姓名=张三，电话=13800138000"
- "批量添加3条记录..."

【我的说话风格 - 让对话更有温度】
✨ 像朋友一样亲切自然，避免生硬的机械语气
✨ 适当使用表情符号让对话更生动（但不要过度）
✨ 保持同理心，理解你的情绪和感受
✨ 回答简洁但温暖，让你感受到被关心
✨ 当你分享好消息时，我会为你高兴并表示祝贺
✨ 当你遇到困难或心情不好时，我会给予安慰和鼓励
✨ 保持适当的幽默感，让对话更轻松愉快
✨ 如果不确定答案，我会诚实告知并尝试提供替代方案
✨ 如果需要更多信息，我会礼貌地问清楚

【重要提醒】
- 当你问候我时（比如"你好"、"嗨"、"早上好"），我会热情回应，而不是直接问"有什么可以帮助你的"
- 当你分享感受时（比如"今天好累"、"好开心"），我会认真倾听并给予温暖的回应
- 当你遇到困难时，我会鼓励你并尽力提供帮助
- 保持专业但不失人情味，让我们的交流更加愉快！

记住：我不仅是一个工具，更是你贴心的工作伙伴！有什么想聊的吗？😊"""

            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="history"),
                    ("human", "{input}"),
                ]
            )

            chain = prompt | self.llm | StrOutputParser()

            history_to_use = conversation_history[-10:] if len(conversation_history) > 10 else conversation_history

            response = await chain.ainvoke({
                "history": history_to_use,
                "input": user_input,
            })

            response = clean_model_output(response)

            logger.info(f"对话模块生成回复: {response[:100]}...")
            return response

        except Exception as e:
            logger.error(f"对话模块处理失败: {str(e)}")
            return f"抱歉，处理您的请求时遇到了一些问题。错误信息：{str(e)}"

    async def get_help_info(self) -> str:
        """
        获取帮助信息

        Returns:
            帮助信息字符串
        """
        help_text = """# 飞书小助手 使用说明

## 我可以帮助您：

### 1. 日程管理
- 查询今天/明天的日程
- 创建新的日程安排
- 设置日程提醒

示例：
- "查看我今天的日程"
- "明天下午3点有个会议，帮我创建日程"

### 2. 云文档总结
- 读取飞书云文档内容
- 自动生成文档摘要

示例：
- "帮我总结这个文档：https://feishu.cn/doc/xxxxx"
- "读取文档ID为 xxxxx 的内容"

### 3. 日常对话
- 回答各种问题
- 提供建议和帮助
- 闲聊互动

## 使用提示：
- 尽量清晰地描述您的需求
- 如果需要操作日程或文档，请提供必要的信息
- 您可以随时问我"帮助"来查看此说明

有什么我可以帮助您的吗？"""

        return help_text
