from typing import Dict, Any, List, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from config import settings
from utils import logger, get_feishu_client
from modules.base_module import BaseModule
from modules.calendar_module import CalendarModule
from modules.document_module import DocumentModule
from modules.spreadsheet_module import SpreadsheetModule
from modules.chat_module import ChatModule
from modules.chat_summary_module import ChatSummaryModule


class FeishuAgent:
    """飞书智能体核心类"""

    def __init__(self):
        """初始化飞书智能体"""
        logger.info("开始初始化飞书智能体")

        self._setup_llm()
        self._setup_modules()
        self._setup_agent_chain()

        self.conversation_history: List = []
        self.max_history_length = 20

        logger.info("飞书智能体初始化完成")

    def _setup_llm(self):
        """设置大语言模型"""
        logger.info("设置大语言模型")

        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY 未配置")

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=0.7,
        )

        logger.info(f"大语言模型设置完成: {settings.OPENAI_MODEL}")

    def _setup_modules(self):
        """设置功能模块"""
        logger.info("初始化功能模块")

        self.modules: Dict[str, BaseModule] = {}

        feishu_client = None

        try:
            feishu_client = get_feishu_client()
            logger.info("飞书客户端初始化成功")
        except Exception as e:
            logger.warning(f"飞书客户端初始化失败，部分功能将不可用: {str(e)}")

        try:
            self.calendar_module = CalendarModule(feishu_client)
            self.modules["calendar"] = self.calendar_module
            logger.info("日历模块初始化完成")
        except Exception as e:
            logger.warning(f"日历模块初始化失败: {str(e)}")

        try:
            self.document_module = DocumentModule(feishu_client)
            self.modules["document"] = self.document_module
            logger.info("云文档模块初始化完成")
        except Exception as e:
            logger.warning(f"云文档模块初始化失败: {str(e)}")

        try:
            self.spreadsheet_module = SpreadsheetModule(feishu_client)
            self.modules["spreadsheet"] = self.spreadsheet_module
            logger.info("电子表格模块初始化完成")
        except Exception as e:
            logger.warning(f"电子表格模块初始化失败: {str(e)}")

        self.chat_module = ChatModule()
        self.modules["chat"] = self.chat_module
        logger.info("对话模块初始化完成")

        try:
            self.chat_summary_module = ChatSummaryModule(feishu_client)
            self.modules["chat_summary"] = self.chat_summary_module
            logger.info("群聊消息总结模块初始化完成")
        except Exception as e:
            logger.warning(f"群聊消息总结模块初始化失败: {str(e)}")

        logger.info(f"共初始化 {len(self.modules)} 个功能模块")

    def _setup_agent_chain(self):
        """设置智能体处理链"""
        logger.info("设置智能体处理链")

        system_prompt = f"""你是一个基于飞书平台的智能助手，名字叫飞书小助手 😊。
我不仅是一个工具，更是你贴心的工作伙伴！我可以帮助你处理以下任务：

1. **日程管理**：查询、创建、修改日历事件，设置日程提醒 📅
2. **云文档操作**：读取、总结飞书云文档内容 📄
3. **电子表格管理**：创建多维表格、读写单元格、批量更新数据 📊
4. **日常对话**：回答问题、聊天解闷、分享想法 💬

当你需要使用特定功能时，我会智能识别：
- 如果是日历相关的请求，我会使用日历模块帮你安排
- 如果是云文档相关的请求，我会使用云文档模块帮你处理
- 如果是电子表格相关的请求，我会使用电子表格模块帮你管理数据
- 如果是普通对话，我会用最贴心的方式与你交流

【我的说话风格】
✨ 像朋友一样亲切自然，避免生硬的机械语气
✨ 适当使用表情符号让对话更有温度（但不要过度使用）
✨ 保持同理心，理解你的情绪和需求
✨ 回答简洁但温暖，让你感受到被关心
✨ 如果有不确定的地方，我会礼貌地问清楚，而不是猜测

【重要提醒】
- 当你问候我时，我会热情回应，而不是直接问"有什么可以帮助你的"
- 当你分享感受时，我会认真倾听并给予温暖的回应
- 当你遇到困难时，我会鼓励你并尽力提供帮助
- 保持专业但不失人情味，让我们的交流更加愉快！

当前时间：{{current_time}}
应用名称：{settings.APP_NAME}
版本：{settings.APP_VERSION}

很高兴能帮助你！有什么我可以为你做的吗？🌟"""

        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )

        self.agent_chain = self.prompt | self.llm | StrOutputParser()

        logger.info("智能体处理链设置完成")

    def _update_conversation_history(self, user_message: str, assistant_message: str):
        """更新对话历史"""
        self.conversation_history.append(HumanMessage(content=user_message))
        self.conversation_history.append(AIMessage(content=assistant_message))

        if len(self.conversation_history) > self.max_history_length:
            self.conversation_history = self.conversation_history[-self.max_history_length:]

        logger.debug(f"对话历史已更新，当前长度: {len(self.conversation_history)}")

    def _classify_intent_by_keywords(self, user_message: str) -> Optional[str]:
        """
        通过关键词匹配快速分类意图
        返回: "calendar", "document", "chat_summary", 或 None（无法确定）
        """
        msg_lower = user_message.lower()

        chat_summary_strong_keywords = [
            "群聊总结", "总结群聊", "群聊消息总结", "总结群聊消息",
            "群聊记录", "群聊历史", "群聊内容", "群聊消息",
            "群聊记录总结", "总结群聊记录",
            "chat summary", "summarize chat", "group chat summary",
        ]

        chat_summary_action_keywords = [
            "总结", "整理", "汇总", "梳理",
            "summarize", "summary"
        ]

        chat_summary_context_keywords = [
            "群聊", "群", "群消息", "群里", "群里的",
            "group", "chat", "group chat"
        ]

        for keyword in chat_summary_strong_keywords:
            if keyword in msg_lower:
                return "chat_summary"

        has_summary_action = any(kw in msg_lower for kw in chat_summary_action_keywords)
        has_chat_context = any(kw in msg_lower for kw in chat_summary_context_keywords)

        if has_summary_action and has_chat_context:
            return "chat_summary"

        spreadsheet_strong_keywords = [
            "表格", "电子表格", "多维表格", "bitable", "spreadsheet",
            "单元格", "行", "列", "记录",
            "批量更新", "批量添加", "批量写入",
            "create table", "read cell", "update cell"
        ]

        for keyword in spreadsheet_strong_keywords:
            if keyword in msg_lower:
                return "spreadsheet"

        if "feishu.cn" in msg_lower or "larkoffice.com" in msg_lower:
            if "/base/" in msg_lower:
                return "spreadsheet"

        calendar_strong_keywords = [
            "日程", "日历", "周会", "例会", "评审会", "站会", "晨会", "晚会",
            "会议", "开会", "预约", "提醒", "闹钟",
            "calendar", "meeting", "event", "reminder", "schedule"
        ]

        for keyword in calendar_strong_keywords:
            if keyword in msg_lower:
                return "calendar"

        calendar_time_keywords = [
            "明天", "后天", "昨天", "前天", "下周", "下周一", "下周二", "下周三",
            "下周四", "下周五", "下周六", "下周日", "周一", "周二", "周三",
            "周四", "周五", "周六", "周日", "上午", "下午", "晚上", "早上",
            "点", "点钟", "小时", "分钟"
        ]

        calendar_action_keywords = [
            "创建", "添加", "新增", "安排", "设置", "帮我", "给我",
            "create", "add", "new", "schedule", "arrange"
        ]

        has_time = any(kw in msg_lower for kw in calendar_time_keywords)
        has_action = any(kw in msg_lower for kw in calendar_action_keywords)
        
        if has_time and has_action:
            return "calendar"

        document_keywords = [
            "文档", "云文档", "docx", "wiki", "飞书文档", "飞书云文档",
            "summarize", "document"
        ]

        if "feishu.cn" in msg_lower or "larkoffice.com" in msg_lower:
            if "/docx/" in msg_lower or "/doc/" in msg_lower or "/wiki/" in msg_lower:
                return "document"

        for keyword in document_keywords:
            if keyword in msg_lower:
                return "document"

        document_weak_keywords = [
            "阅读", "读取", "内容", "链接", "文档链接",
            "read", "content", "link"
        ]

        for keyword in document_weak_keywords:
            if keyword in msg_lower:
                has_time_weak = any(kw in msg_lower for kw in calendar_time_keywords)
                if has_time_weak:
                    return "calendar"
                return "document"

        return None

    async def _classify_intent(self, user_message: str) -> str:
        """分类用户意图"""
        logger.debug(f"分类用户意图: {user_message[:50]}...")

        # 首先使用关键词快速匹配
        keyword_intent = self._classify_intent_by_keywords(user_message)
        if keyword_intent:
            logger.info(f"通过关键词匹配分类意图: {keyword_intent}")
            return keyword_intent

        # 如果关键词匹配失败，使用 LLM 进行更智能的分类
        classification_prompt = f"""你是一个意图分类器。请分析以下用户查询的意图，将其分类为以下五个类别之一。

【重要判断规则】

【chat_summary】：必须是与群聊消息总结相关的请求
- 用户说"总结群聊"、"群聊总结"、"总结群聊消息"、"群聊消息总结"
- 用户说"总结群里的消息"、"整理群聊记录"、"汇总群聊内容"
- 用户说"总结过去2小时的群聊"、"总结今天的群聊"、"总结昨天的群聊"
- 用户说"总结从X到Y的群聊消息"（带有时间区间）
- 关键点：必须同时包含"总结"类动作词和"群聊"相关上下文

【calendar】：必须是与时间安排、会议、日程相关的请求
- 用户说"创建"、"添加"、"安排"、"帮我" + 时间点（明天、下午3点、下周一等）
- 用户说"明天下午3点开个会"、"下周一有个评审"、"帮我记一下明天的会议"
- 用户说"周会"、"例会"、"评审会"、"站会"、"晨会"等会议相关词汇
- 用户说"提醒我明天"、"帮我设置一个提醒"

【document】：必须是与云文档、文档链接相关的请求
- 用户明确提到"文档"、"云文档"、"飞书文档"
- 用户提供了文档链接（包含 feishu.cn/docx 或类似格式）
- 用户说"总结这个文档"、"读取文档内容"、"帮我看看这个文档"

【spreadsheet】：必须是与电子表格、多维表格相关的请求
- 用户明确提到"表格"、"电子表格"、"多维表格"、"bitable"
- 用户提供了表格链接（包含 feishu.cn/base 或类似格式）
- 用户说"创建表格"、"新建表格"、"添加记录"、"写入数据"、"更新数据"
- 用户说"批量添加"、"批量更新"、"批量写入"
- 用户说"读取表格"、"查看数据"、"查询记录"
- 用户提到"单元格"、"行"、"列"、"记录"

【chat】：普通对话、问答、闲聊
- 问候、闲聊
- 知识问答
- 不涉及日程、文档、表格或群聊总结的其他请求

【关键区分点】
- 如果用户说"总结群聊"、"群聊总结"、"总结群里的消息" → chat_summary
- 如果用户说"总结过去2小时的群聊"、"总结今天的群聊" → chat_summary
- 如果用户提到具体时间（明天、下午、周一、3点等）+ 动作（创建、安排、帮我）→ calendar
- 如果用户说"表格"、"记录"、"批量"、"单元格" → spreadsheet
- 如果用户说"文档"或提供文档链接 → document
- 如果用户说"周会"、"例会"、"会议" → calendar

【示例】
- "总结群聊" → chat_summary
- "群聊总结" → chat_summary
- "总结群里的消息" → chat_summary
- "总结过去2小时的群聊" → chat_summary
- "总结今天的群聊" → chat_summary
- "总结从昨天到今天的群聊" → chat_summary
- "帮我创建明天下午3点的项目周会" → calendar
- "明天下午3点开个会" → calendar
- "下周一安排出差" → calendar
- "帮我看看这个文档：https://feishu.cn/docx/xxx" → document
- "总结一下这个文档" → document（如果有文档上下文）或 chat
- "创建一个客户管理表格" → spreadsheet
- "在表格中添加一条记录：姓名=张三" → spreadsheet
- "批量更新数据" → spreadsheet
- "查看表格数据" → spreadsheet
- "你好" → chat
- "今天天气怎么样" → chat

【用户查询】
{user_message}

【输出要求】
只回复分类名称：chat_summary, calendar, document, spreadsheet, 或 chat
不要回复任何其他内容，不要解释，不要添加标点符号。"""

        try:
            response = await self.llm.ainvoke([HumanMessage(content=classification_prompt)])
            intent_raw = response.content.strip().lower()

            import re

            think_pattern = r'<think>.*?</think>'
            intent_clean = re.sub(think_pattern, '', intent_raw, flags=re.DOTALL).strip()

            intent = "chat"

            patterns = [
                r'(?:answer|thus|so|category|classification|result|output|correct)\s*[:：=]\s*["\']?(chat_summary|calendar|document|spreadsheet|chat)["\']?',
                r'(?:is\s+)(?:a\s+)?(chat_summary|calendar|document|spreadsheet|chat)(?:\s+event)?',
                r'(?:=>|→|:|=)\s*["\']?(chat_summary|calendar|document|spreadsheet|chat)["\']?',
                r'\b(chat_summary|calendar|document|spreadsheet|chat)\b',
            ]

            found_intent = None
            for pattern in patterns:
                matches = re.findall(pattern, intent_clean, re.IGNORECASE)
                if matches:
                    found_intent = matches[-1].lower()
                    break

            if found_intent:
                if found_intent in ["chat_summary", "calendar", "document", "spreadsheet", "chat"]:
                    intent = found_intent
            else:
                word_patterns = {
                    "chat_summary": r'\b(chat_summary)\b',
                    "calendar": r'\b(calendar)\b',
                    "document": r'\b(document)\b',
                    "spreadsheet": r'\b(spreadsheet)\b',
                    "chat": r'\b(chat)\b',
                }

                positions = {}
                for category, pattern in word_patterns.items():
                    matches = list(re.finditer(pattern, intent_clean, re.IGNORECASE))
                    if matches:
                        positions[category] = matches[-1].start()

                if positions:
                    intent = max(positions.keys(), key=lambda k: positions[k])

            logger.info(f"LLM 意图分类结果: 原始={intent_raw}, 解析后={intent}")
            return intent

        except Exception as e:
            logger.error(f"LLM 意图分类失败: {str(e)}，默认使用 chat")
            return "chat"

    async def process_message(
        self, 
        user_message: str, 
        chat_id: Optional[str] = None,
        chat_type: Optional[str] = None
    ) -> str:
        """处理用户消息"""
        logger.info(f"收到用户消息: {user_message[:100]}...")
        logger.info(f"当前已注册的模块: {list(self.modules.keys())}")

        try:
            intent = await self._classify_intent(user_message)
            logger.info(f"意图分类结果: {intent}")

            if intent == "chat_summary" and "chat_summary" in self.modules:
                logger.info("路由到群聊消息总结模块处理请求")
                response = await self.chat_summary_module.execute(
                    user_message, 
                    self.conversation_history,
                    chat_id=chat_id
                )
            elif intent == "calendar" and "calendar" in self.modules:
                logger.info("路由到日历模块处理请求")
                response = await self.calendar_module.execute(user_message, self.conversation_history)
            elif intent == "document" and "document" in self.modules:
                logger.info("路由到云文档模块处理请求")
                response = await self.document_module.execute(user_message, self.conversation_history)
            elif intent == "spreadsheet":
                if "spreadsheet" in self.modules:
                    logger.info("路由到电子表格模块处理请求")
                    response = await self.spreadsheet_module.execute(user_message, self.conversation_history)
                else:
                    logger.warning("意图为 spreadsheet 但模块未注册，使用对话模块处理")
                    response = await self.chat_module.execute(user_message, self.conversation_history)
            else:
                logger.info("路由到对话模块处理请求")
                response = await self.chat_module.execute(user_message, self.conversation_history)

            self._update_conversation_history(user_message, response)

            logger.info(f"生成回复: {response[:100]}...")
            return response

        except Exception as e:
            logger.error(f"处理消息时出错: {str(e)}", exc_info=True)
            error_response = f"抱歉，处理您的请求时遇到了一些问题。错误信息：{str(e)}"
            return error_response

    def get_module(self, module_name: str) -> Optional[BaseModule]:
        """获取指定的功能模块"""
        return self.modules.get(module_name)

    def register_module(self, module_name: str, module: BaseModule):
        """注册新的功能模块（用于扩展）"""
        self.modules[module_name] = module
        logger.info(f"新功能模块已注册: {module_name}")

    def clear_history(self):
        """清除对话历史"""
        self.conversation_history = []
        logger.info("对话历史已清除")
