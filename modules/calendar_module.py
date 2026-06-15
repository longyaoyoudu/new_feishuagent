from typing import List, Any, Dict, Optional, Tuple
from datetime import datetime, timedelta, date
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
import json
import re
import string

from config import settings
from utils import logger, FeishuClient
from modules.base_module import BaseModule


class CalendarModule(BaseModule):
    """日程管理模块"""
    
    # 日期关键词映射：关键词 -> (weekday, is_next_week)
    # weekday: 0=周一, 1=周二, ..., 6=周日
    # is_next_week: True=下周, False=本周
    DATE_KEYWORDS = {
        "下周一": (0, True),
        "下周二": (1, True),
        "下周三": (2, True),
        "下周四": (3, True),
        "下周五": (4, True),
        "下周六": (5, True),
        "下周日": (6, True),
        "下礼拜天": (6, True),
        "周一": (0, False),
        "星期二": (0, False),
        "周二": (1, False),
        "星期三": (1, False),
        "周三": (2, False),
        "星期四": (2, False),
        "周四": (3, False),
        "星期五": (3, False),
        "周五": (4, False),
        "星期六": (4, False),
        "周六": (5, False),
        "星期日": (5, False),
        "周日": (6, False),
        "礼拜天": (6, False),
    }
    
    # 相对日期关键词
    RELATIVE_DATE_KEYWORDS = {
        "明天": 1,
        "明日": 1,
        "后天": 2,
        "昨天": -1,
        "昨日": -1,
        "前天": -2,
        "今天": 0,
        "今日": 0,
    }
    
    # 时长关键词映射
    DURATION_KEYWORDS = {
        "一小时": 60,
        "1小时": 60,
        "半小时": 30,
        "30分钟": 30,
        "30分": 30,
        "两小时": 120,
        "2小时": 120,
        "一个半小时": 90,
        "1.5小时": 90,
    }
    
    # 取消关键词
    CANCEL_KEYWORDS = ["取消", "放弃", "不用了", "算了", "不创建了", "stop", "cancel"]
    
    # 创建关键词
    CREATE_KEYWORDS = ["创建", "添加", "新增", "安排", "预约", "设置", "create", "add", "new", "schedule"]
    
    # 查询关键词
    QUERY_KEYWORDS = ["查询", "查看", "看看", "有什么", "安排", "query", "view", "show", "list"]
    
    # 时间指示器关键词
    TIME_INDICATORS = ["点", "分", "时", "小时", "分钟", "上午", "下午", "晚上", "早上", 
                        "明天", "后天", "周一", "周二", "周三", "周四", "周五", "周六", "周日", 
                        "下周一", "下周二", "全天"]

    def __init__(self, feishu_client: Optional[FeishuClient] = None):
        """
        初始化日程管理模块

        Args:
            feishu_client: 飞书客户端实例
        """
        super().__init__(
            name="calendar",
            description="日程管理模块，支持查询、创建、修改日历事件，设置日程提醒"
        )
        self.feishu_client = feishu_client
        self._setup_llm()
        self._pending_create: Optional[Dict[str, Any]] = None

    def _setup_llm(self):
        """设置大语言模型"""
        if not settings.OPENAI_API_KEY:
            self.llm = None
            return

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=0.1,
        )

    def _parse_natural_time(self, time_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        解析自然语言时间描述

        Args:
            time_str: 时间字符串

        Returns:
            (start_timestamp, end_timestamp, start_date, end_date) - 其中时间戳为秒级字符串，日期为YYYY-MM-DD格式
        """
        now = datetime.now()
        today = now.date()
        
        time_str = time_str.lower().strip()
        
        all_day = "全天" in time_str or "整天" in time_str
        target_date = self._get_target_date(time_str, today)
        hour, minute = self._parse_time_component(time_str)
        duration_minutes = self._parse_duration(time_str)
        
        if all_day:
            start_date_str = target_date.strftime("%Y-%m-%d")
            end_date_str = (target_date + timedelta(days=1)).strftime("%Y-%m-%d")
            return None, None, start_date_str, end_date_str
        else:
            start_dt = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            
            start_timestamp = str(int(start_dt.timestamp()))
            end_timestamp = str(int(end_dt.timestamp()))
            
            return start_timestamp, end_timestamp, None, None
    
    def _get_target_date(self, time_str: str, today: date) -> date:
        """
        从时间字符串中解析目标日期

        Args:
            time_str: 时间字符串
            today: 今天的日期

        Returns:
            目标日期
        """
        # 首先检查"下周"相关关键词（需要优先匹配，因为包含"周一"等）
        for keyword, (weekday, is_next_week) in self.DATE_KEYWORDS.items():
            if is_next_week and keyword in time_str:
                return self._calculate_weekday_date(today, weekday, is_next_week)
        
        # 检查相对日期关键词
        for keyword, days_delta in self.RELATIVE_DATE_KEYWORDS.items():
            if keyword in time_str:
                return today + timedelta(days=days_delta)
        
        # 检查本周关键词
        for keyword, (weekday, is_next_week) in self.DATE_KEYWORDS.items():
            if not is_next_week and keyword in time_str:
                return self._calculate_weekday_date(today, weekday, is_next_week)
        
        # 默认返回今天
        return today
    
    def _calculate_weekday_date(self, today: date, target_weekday: int, is_next_week: bool) -> date:
        """
        计算指定星期几的日期

        Args:
            today: 今天的日期
            target_weekday: 目标星期几 (0=周一, 1=周二, ..., 6=周日)
            is_next_week: 是否是下周

        Returns:
            计算后的日期
        """
        days_ahead = (target_weekday - today.weekday()) % 7
        
        if is_next_week:
            # 如果今天就是目标星期几，需要加7天
            if days_ahead == 0:
                days_ahead = 7
            else:
                days_ahead += 7
        
        return today + timedelta(days=days_ahead)
    
    def _parse_time_component(self, time_str: str) -> Tuple[int, int]:
        """
        解析时间字符串中的小时和分钟

        Args:
            time_str: 时间字符串

        Returns:
            (小时, 分钟)
        """
        hour = 9
        minute = 0
        
        # 判断上午/下午
        is_pm = "下午" in time_str or "晚上" in time_str or "傍晚" in time_str
        is_am = "早上" in time_str or "上午" in time_str or "早晨" in time_str
        
        # 匹配时间格式，如 "3点", "3:30", "15点45分"
        time_match = re.search(r'(\d{1,2})[点:：时](\d{1,2})?[分]?', time_str)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            
            # 处理12小时制
            if is_pm and hour < 12:
                hour += 12
            elif is_am and hour >= 12:
                hour -= 12
        else:
            # 没有明确的时间，根据上午/下午调整默认时间
            if is_pm:
                hour = 14  # 下午默认2点
            elif is_am:
                hour = 9  # 上午默认9点
        
        # 处理"半"字，如 "3点半"
        if "半" in time_str and not time_match:
            minute = 30
        
        # 再次确认上午/下午的处理
        if "早上" in time_str or "上午" in time_str:
            if hour >= 12:
                hour -= 12
        elif "下午" in time_str or "晚上" in time_str:
            if hour < 12:
                hour += 12
        
        return hour, minute
    
    def _parse_duration(self, time_str: str) -> int:
        """
        解析时长

        Args:
            time_str: 时间字符串

        Returns:
            时长（分钟）
        """
        # 默认1小时
        duration_minutes = 60
        
        for keyword, minutes in self.DURATION_KEYWORDS.items():
            if keyword in time_str:
                return minutes
        
        return duration_minutes

    def _get_missing_fields(self, parameters: Dict[str, Any]) -> List[str]:
        """
        检查创建日程时缺少的必填字段

        Args:
            parameters: 参数字典

        Returns:
            缺少的字段列表
        """
        missing = []
        
        if not parameters.get("summary"):
            missing.append("标题")
        
        has_time = (parameters.get("start_time") and parameters.get("end_time")) or \
                   (parameters.get("start_date") and parameters.get("end_date"))
        
        if not has_time:
            missing.append("开始时间和结束时间")
        
        return missing

    async def _parse_user_intent(
        self,
        user_input: str,
        conversation_history: List[BaseMessage]
    ) -> Dict[str, Any]:
        """
        解析用户日程相关意图

        Args:
            user_input: 用户输入
            conversation_history: 对话历史

        Returns:
            解析结果，包含动作类型和参数
        """
        if self.llm is None:
            logger.warning("大语言模型未配置，无法解析用户意图")
            return {"action": "unknown", "reason": "LLM not configured"}

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        system_prompt_template = """你是一个贴心的日程管理助手 📅。请用心分析用户的输入，理解他们想要执行什么操作，并准确提取相关参数。

当前时间：$current_time

我会帮助用户高效地管理日程，让他们的工作和生活更加井井有条！请将用户意图分类为以下类型之一：
1. query：查询日程（查看今天/明天/某一天的日程，查看即将到来的日程等）
2. create：创建日程（添加新的会议、约会、提醒等）
3. remind：设置提醒（为某个日程设置提醒）
4. unknown：无法识别的操作

【重要判断规则】
以下情况必须判断为 "create"：
- 用户说"创建"、"添加"、"新增"、"安排"、"预约"、"帮我"、"给我"、"设置"日程/会议/提醒
- 用户说"明天下午3点开个会"、"下周一有个评审"等涉及具体时间安排的请求
- 用户说"帮我记一下"、"提醒我明天"等安排性质的请求

以下情况必须判断为 "query"：
- 用户说"查看"、"查询"、"看看"、"有什么"、"什么安排"日程
- 用户说"明天有什么事"、"下周一的安排"等查询性质的请求

请以JSON格式返回结果，包含以下字段：
- action: 操作类型（query/create/remind/unknown）
- parameters: 参数字典，根据不同操作类型包含不同参数
  - 对于 query：可能包含 date（日期字符串，格式YYYY-MM-DD）、time_range（时间范围）
  - 对于 create：包含以下字段：
    - summary: 日程标题（必填）- 从用户输入中提取，如"项目周会"、"出差"、"评审会"等
    - description: 日程描述（可选）
    - start_time_raw: 开始时间的自然语言描述（如"明天下午3点"、"下周一上午10点"）
    - end_time_raw: 结束时间的自然语言描述（可选）
    - start_date_raw: 全天日程的开始日期（如"明天"、"下周一"，与start_time_raw二选一）
    - end_date_raw: 全天日程的结束日期（可选）
    - is_all_day: 是否为全天日程（true/false）
    - location: 地点（可选）
    - attendees: 参与者列表，每个参与者包含name（姓名）、email（邮箱，可选）
    - reminder_minutes: 提前多少分钟提醒（如15、30、60，可选）
  - 对于 remind：包含 event_id（日程ID）、remind_time（提醒时间）
- confidence: 置信度（0-1之间的浮点数）
- explanation: 简短的解释（用友好的语气描述用户的意图）

【温馨提示】
- 对于创建日程，如果用户提到"全天"、"整天"，请设置is_all_day为true
- 时间描述要尽可能保留用户的原始表述，如"明天下午3点"、"下周一上午10点半"
- 如果信息不足，请在参数中标记为 null，并在 explanation 中说明需要哪些信息。
- 当用户说"创建日程"但没有提供具体信息时，action 仍然是 "create"，只是 parameters 中的字段为 null

【更多示例】

示例输出4（用户说"帮我创建一个日程"）：
{{
  "action": "create",
  "parameters": {{
    "summary": null,
    "start_time_raw": null,
    "is_all_day": false
  }},
  "confidence": 0.9,
  "explanation": "用户想要创建日程，但缺少标题和时间信息，我需要友好地询问这些信息"
}}

示例输出5（用户说"明天下午3点和张三开项目周会，在会议室A"）：
{{
  "action": "create",
  "parameters": {{
    "summary": "项目周会",
    "start_time_raw": "明天下午3点",
    "is_all_day": false,
    "location": "会议室A",
    "attendees": [{{"name": "张三"}}]
  }},
  "confidence": 0.95,
  "explanation": "用户想要创建明天下午3点的项目周会，我会帮他安排好这个会议"
}}

示例输出6（用户说"下周一全天出差"）：
{{
  "action": "create",
  "parameters": {{
    "summary": "出差",
    "start_date_raw": "下周一",
    "is_all_day": true
  }},
  "confidence": 0.9,
  "explanation": "用户想要创建下周一全天的出差日程，我会帮他记录好"
}}

示例输出7（用户说"明天有什么安排"）：
{{
  "action": "query",
  "parameters": {{"date": "2026-04-24"}},
  "confidence": 0.95,
  "explanation": "用户查询明天的日程，我会帮他查看并友好地汇报"
}}

请只返回JSON格式的结果，不要返回其他内容。让我们一起帮助用户高效管理日程吧！✨"""

        system_prompt = string.Template(system_prompt_template).substitute(
            current_time=current_time
        )

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_prompt),
                    MessagesPlaceholder(variable_name="history"),
                    ("human", "{input}"),
                ]
            )

            chain = prompt | self.llm | StrOutputParser()

            result = await chain.ainvoke({
                "history": conversation_history[-10:] if len(conversation_history) > 10 else conversation_history,
                "input": user_input,
            })

            json_start = result.find('{')
            json_end = result.rfind('}') + 1
            if json_start != -1 and json_end > json_start:
                json_str = result[json_start:json_end]
                parsed = json.loads(json_str)
            else:
                parsed = json.loads(result)

            logger.info(f"用户意图解析结果: {parsed}")
            return parsed

        except Exception as e:
            logger.error(f"解析用户意图失败: {str(e)}")
            return {"action": "unknown", "reason": str(e)}

    async def _query_calendar(self, parameters: Dict[str, Any]) -> str:
        """
        查询日历事件

        Args:
            parameters: 查询参数

        Returns:
            查询结果描述
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法查询日程。请先配置飞书应用凭证。"

        try:
            date = parameters.get("date")
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")

            logger.info(f"查询日期 {date} 的日程")

            # 计算日期范围的时间戳
            start_time, end_time = self._get_date_range_timestamps(date)

            result = await self.feishu_client.get_calendar_events(
                calendar_id="primary",
                start_time=start_time,
                end_time=end_time,
                max_results=10
            )

            events = result.get("events", [])

            if not events:
                return f"您在 {date} 没有安排任何日程。"

            response = f"您在 {date} 有以下 {len(events)} 个日程：\n\n"

            for i, event in enumerate(events, 1):
                response += self._format_event_for_display(i, event)

            return response

        except Exception as e:
            logger.error(f"查询日程失败: {str(e)}")
            return f"查询日程时出错: {str(e)}"
    
    def _get_date_range_timestamps(self, date_str: str) -> Tuple[str, str]:
        """
        将日期字符串转换为当天的开始和结束时间戳

        Args:
            date_str: 日期字符串，格式为 YYYY-MM-DD

        Returns:
            (开始时间戳, 结束时间戳) - 秒级字符串
        """
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            # 如果解析失败，使用今天
            date_obj = datetime.now().date()
        
        # 当天开始时间 (00:00:00)
        start_dt = datetime.combine(date_obj, datetime.min.time())
        # 当天结束时间 (23:59:59)
        end_dt = datetime.combine(date_obj, datetime.max.time())
        
        return str(int(start_dt.timestamp())), str(int(end_dt.timestamp()))
    
    def _format_event_for_display(self, index: int, event: Dict[str, Any]) -> str:
        """
        格式化单个日程事件用于显示

        Args:
            index: 日程序号
            event: 日程事件数据

        Returns:
            格式化后的字符串
        """
        start_time = event.get("start_time", {})
        end_time = event.get("end_time", {})
        
        # 解析时间信息
        time_display = self._format_event_time(start_time, end_time)
        
        response = f"{index}. {event.get('summary', '无标题')}\n"
        if time_display:
            response += f"   时间: {time_display}\n"
        if event.get("description"):
            desc = event.get("description", "")
            response += f"   描述: {desc[:100]}...\n" if len(desc) > 100 else f"   描述: {desc}\n"
        if event.get("location"):
            response += f"   地点: {event.get('location')}\n"
        response += "\n"
        
        return response
    
    def _format_event_time(self, start_time: Any, end_time: Any) -> str:
        """
        格式化日程的时间显示

        Args:
            start_time: 开始时间信息（可能是字典或字符串）
            end_time: 结束时间信息（可能是字典或字符串）

        Returns:
            格式化后的时间字符串
        """
        # 处理字典类型的时间信息
        if isinstance(start_time, dict) and isinstance(end_time, dict):
            # 检查是否是全天日程
            if "date" in start_time and "date" in end_time:
                start_date = start_time.get("date", "")
                end_date = end_time.get("date", "")
                if start_date == end_date:
                    return f"{start_date}（全天）"
                else:
                    return f"{start_date} - {end_date}（全天）"
            
            # 检查是否有时间戳
            elif "timestamp" in start_time and "timestamp" in end_time:
                try:
                    start_ts = int(start_time.get("timestamp", "0"))
                    end_ts = int(end_time.get("timestamp", "0"))
                    start_dt = datetime.fromtimestamp(start_ts)
                    end_dt = datetime.fromtimestamp(end_ts)
                    
                    # 如果是同一天，只显示一个日期
                    if start_dt.date() == end_dt.date():
                        return f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%H:%M')}"
                    else:
                        return f"{start_dt.strftime('%Y-%m-%d %H:%M')} - {end_dt.strftime('%Y-%m-%d %H:%M')}"
                except (ValueError, OSError):
                    pass
        
        # 处理字符串类型的时间信息
        start_str = str(start_time) if start_time else ""
        end_str = str(end_time) if end_time else ""
        
        if start_str and end_str:
            return f"{start_str} - {end_str}"
        
        return ""

    async def _create_calendar_event(self, parameters: Dict[str, Any]) -> str:
        """
        创建日历事件

        Args:
            parameters: 创建参数

        Returns:
            创建结果描述
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法创建日程。请先配置飞书应用凭证。"

        try:
            # 合并待创建参数和新参数
            merged_params = self._merge_pending_params(parameters)
            
            summary = merged_params.get("summary")
            if not summary:
                return "请提供日程的标题。"

            # 解析时间参数
            start_time, end_time, start_date, end_date = self._parse_event_time_params(merged_params)

            # 检查必填字段
            for_conversion = {
                "summary": summary,
                "start_time": start_time,
                "end_time": end_time,
                "start_date": start_date,
                "end_date": end_date,
            }
            missing = self._get_missing_fields(for_conversion)

            if missing:
                # 保存待创建状态
                self._pending_create = merged_params
                missing_str = "、".join(missing)
                return f"创建日程还需要以下信息：{missing_str}。请补充这些信息，我会继续帮您创建日程。"

            # 清除待创建状态
            self._pending_create = None

            # 准备创建参数
            create_params = self._prepare_create_params(merged_params, summary, start_time, end_time, start_date, end_date)
            
            logger.info(f"创建日程: {summary}")
            
            # 调用飞书API创建日程
            result = await self._call_create_calendar_api(create_params)

            return self._format_create_response(result, create_params)

        except Exception as e:
            logger.error(f"创建日程失败: {str(e)}")
            return f"创建日程时出错: {str(e)}"
    
    def _merge_pending_params(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        合并待创建参数和新参数

        Args:
            parameters: 新参数

        Returns:
            合并后的参数字典
        """
        if self._pending_create:
            return {**self._pending_create, **parameters}
        return parameters
    
    def _parse_event_time_params(self, params: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        解析日程时间参数

        Args:
            params: 参数字典

        Returns:
            (start_time, end_time, start_date, end_date)
        """
        start_time_raw = params.get("start_time_raw")
        start_date_raw = params.get("start_date_raw")
        is_all_day = params.get("is_all_day", False)
        
        start_time = None
        end_time = None
        start_date = None
        end_date = None

        if is_all_day:
            if start_date_raw:
                start_time, end_time, start_date, end_date = self._parse_natural_time(start_date_raw)
                if not start_date:
                    # 尝试直接解析YYYY-MM-DD格式
                    if re.match(r'\d{4}-\d{2}-\d{2}', start_date_raw):
                        start_date = start_date_raw
        else:
            if start_time_raw:
                start_time, end_time, start_date, end_date = self._parse_natural_time(start_time_raw)
            else:
                # 直接使用已有的时间戳
                start_time = params.get("start_time")
                end_time = params.get("end_time")

        return start_time, end_time, start_date, end_date
    
    def _prepare_create_params(
        self, 
        params: Dict[str, Any], 
        summary: str,
        start_time: Optional[str],
        end_time: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str]
    ) -> Dict[str, Any]:
        """
        准备创建日程的参数

        Args:
            params: 原始参数字典
            summary: 日程标题
            start_time: 开始时间戳
            end_time: 结束时间戳
            start_date: 开始日期（全天日程）
            end_date: 结束日期（全天日程）

        Returns:
            整理后的创建参数字典
        """
        is_all_day = params.get("is_all_day", False)
        description = params.get("description", "")
        location = params.get("location", "")
        attendees = params.get("attendees", [])
        reminder_minutes = params.get("reminder_minutes")

        reminders = None
        if reminder_minutes:
            reminders = [{"minutes": reminder_minutes}]

        return {
            "summary": summary,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "start_date": start_date,
            "end_date": end_date,
            "is_all_day": is_all_day,
            "location": location,
            "attendees": attendees,
            "reminders": reminders,
        }
    
    async def _call_create_calendar_api(self, create_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用飞书API创建日程

        Args:
            create_params: 创建参数

        Returns:
            API响应结果
        """
        is_all_day = create_params.get("is_all_day", False)
        start_date = create_params.get("start_date")
        end_date = create_params.get("end_date")
        
        common_params = {
            "summary": create_params["summary"],
            "description": create_params["description"],
            "location": create_params["location"],
            "attendees": create_params["attendees"],
            "reminders": create_params["reminders"],
            "calendar_id": "primary"
        }

        if is_all_day and start_date and end_date:
            return await self.feishu_client.create_calendar_event(
                **common_params,
                start_date=start_date,
                end_date=end_date
            )
        else:
            return await self.feishu_client.create_calendar_event(
                **common_params,
                start_time=create_params["start_time"],
                end_time=create_params["end_time"]
            )
    
    def _format_create_response(self, result: Dict[str, Any], create_params: Dict[str, Any]) -> str:
        """
        格式化创建日程的响应

        Args:
            result: API响应结果
            create_params: 创建参数

        Returns:
            格式化后的响应字符串
        """
        if result.get("success"):
            event_id = result.get("event_id")
            start_info = result.get("start_time", {})
            end_info = result.get("end_time", {})
            
            summary = create_params["summary"]
            description = create_params["description"]
            location = create_params["location"]

            response = f"✅ 日程创建成功！\n\n"
            response += f"📌 标题：{summary}\n"
            response += f"🆔 日程ID：{event_id}\n"

            # 使用已有的时间格式化方法
            time_display = self._format_event_time(start_info, end_info)
            if time_display:
                if "全天" in time_display:
                    response += f"📅 日期：{time_display}\n"
                else:
                    response += f"⏰ 时间：{time_display}\n"

            if description:
                response += f"📝 描述：{description}\n"
            if location:
                response += f"📍 地点：{location}\n"

            return response
        else:
            return f"创建日程失败: {result.get('message', '未知错误')}"

    async def execute(
        self,
        user_input: str,
        conversation_history: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        执行日程管理功能

        Args:
            user_input: 用户输入
            conversation_history: 对话历史
            **kwargs: 其他参数

        Returns:
            执行结果字符串
        """
        logger.info(f"日程模块处理用户输入: {user_input}")

        user_input_lower = user_input.lower()
        
        # 检查取消操作
        cancel_result = self._check_cancel_operation(user_input_lower)
        if cancel_result is not None:
            return cancel_result

        # 处理待创建日程
        if self._pending_create:
            logger.info(f"存在待创建的日程，将用户输入作为补充信息处理")
            return await self._handle_pending_create(user_input, conversation_history)

        # 解析用户意图
        intent = await self._parse_user_intent(user_input, conversation_history)
        action = intent.get("action", "unknown")
        parameters = intent.get("parameters", {})

        logger.info(f"解析结果: action={action}, parameters={parameters}")

        # 根据意图执行操作
        return await self._execute_by_intent(action, parameters, user_input_lower)
    
    def _check_cancel_operation(self, user_input_lower: str) -> Optional[str]:
        """
        检查是否为取消操作

        Args:
            user_input_lower: 小写的用户输入

        Returns:
            如果是取消操作，返回取消结果；否则返回 None
        """
        for keyword in self.CANCEL_KEYWORDS:
            if keyword in user_input_lower:
                if self._pending_create:
                    pending_summary = self._pending_create.get("summary", "未命名日程")
                    self._pending_create = None
                    return f"已取消创建日程「{pending_summary}」。"
                else:
                    return "当前没有待创建的日程。"
        return None
    
    async def _execute_by_intent(
        self, 
        action: str, 
        parameters: Dict[str, Any], 
        user_input_lower: str
    ) -> str:
        """
        根据解析的意图执行操作

        Args:
            action: 操作类型
            parameters: 操作参数
            user_input_lower: 小写的用户输入

        Returns:
            执行结果字符串
        """
        if action == "query":
            return await self._query_calendar(parameters)
        elif action == "create":
            return await self._create_calendar_event(parameters)
        elif action == "remind":
            return "设置提醒功能正在开发中，敬请期待。"
        else:
            # 尝试使用关键词匹配
            return await self._try_keyword_match(parameters, user_input_lower)
    
    async def _try_keyword_match(self, parameters: Dict[str, Any], user_input_lower: str) -> str:
        """
        当意图解析失败时，尝试使用关键词匹配

        Args:
            parameters: 操作参数
            user_input_lower: 小写的用户输入

        Returns:
            执行结果字符串
        """
        # 检查创建关键词
        for keyword in self.CREATE_KEYWORDS:
            if keyword in user_input_lower:
                logger.info(f"检测到创建关键词 '{keyword}'，尝试创建日程")
                return await self._create_calendar_event(parameters)

        # 检查查询关键词
        for keyword in self.QUERY_KEYWORDS:
            if keyword in user_input_lower:
                logger.info(f"检测到查询关键词 '{keyword}'，查询日程")
                return await self._query_calendar(parameters)

        return "我理解您想进行日程相关的操作，但具体意图不够明确。请告诉我您想查询日程、创建日程还是设置提醒？"

    async def _handle_pending_create(
        self,
        user_input: str,
        conversation_history: List[BaseMessage]
    ) -> str:
        """
        处理待创建日程的补充信息

        Args:
            user_input: 用户输入
            conversation_history: 对话历史

        Returns:
            执行结果字符串
        """
        intent = await self._parse_user_intent(user_input, conversation_history)
        action = intent.get("action", "unknown")
        parameters = intent.get("parameters", {})

        # 如果用户想查询日程，允许中断待创建流程
        if action == "query":
            return await self._query_calendar(parameters)

        # 合并参数到待创建状态
        self._update_pending_create_from_params(user_input, action, parameters)

        # 继续创建流程
        merged_params = {**self._pending_create, **parameters}
        logger.info(f"合并后的参数: {merged_params}")

        return await self._create_calendar_event(merged_params)
    
    def _update_pending_create_from_params(
        self, 
        user_input: str, 
        action: str, 
        parameters: Dict[str, Any]
    ) -> None:
        """
        从解析的参数更新待创建日程的状态

        Args:
            user_input: 用户输入
            action: 解析的操作类型
            parameters: 解析的参数
        """
        # 处理标题
        self._update_pending_summary(user_input, action, parameters)
        
        # 定义需要合并的参数字段
        fields_to_update = [
            "start_time_raw", "start_date_raw", "is_all_day", 
            "location", "description", "attendees", "reminder_minutes"
        ]
        
        # 从 parameters 中提取并更新字段
        for field in fields_to_update:
            value = parameters.get(field)
            if value is not None:
                self._pending_create[field] = value
        
        # 处理时间信息（当解析失败时，直接从用户输入中提取）
        self._update_pending_time_from_input(user_input)
    
    def _update_pending_summary(self, user_input: str, action: str, parameters: Dict[str, Any]) -> None:
        """
        更新待创建日程的标题

        Args:
            user_input: 用户输入
            action: 解析的操作类型
            parameters: 解析的参数
        """
        pending_summary = self._pending_create.get("summary", "")
        
        if not pending_summary:
            if parameters.get("summary"):
                self._pending_create["summary"] = parameters.get("summary")
            elif action == "create" and parameters.get("summary"):
                self._pending_create["summary"] = parameters.get("summary")
            else:
                # 如果用户输入简短，直接作为标题
                if 0 < len(user_input) < 50:
                    self._pending_create["summary"] = user_input
    
    def _update_pending_time_from_input(self, user_input: str) -> None:
        """
        直接从用户输入中提取时间信息

        Args:
            user_input: 用户输入
        """
        has_time_info = any(ind in user_input for ind in self.TIME_INDICATORS)
        
        # 只有在还没有时间信息时才处理
        if has_time_info and not self._pending_create.get("start_time_raw") and not self._pending_create.get("start_date_raw"):
            if "全天" in user_input:
                self._pending_create["is_all_day"] = True
                self._pending_create["start_date_raw"] = user_input
            else:
                self._pending_create["start_time_raw"] = user_input
