from typing import List, Any, Dict, Optional
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
import json
import re
import time
from datetime import datetime, timedelta

from config import settings
from utils import logger, FeishuClient, clean_model_output
from modules.base_module import BaseModule


class ChatSummaryModule(BaseModule):
    """群聊消息总结模块"""

    def __init__(self, feishu_client: Optional[FeishuClient] = None):
        """
        初始化群聊消息总结模块

        Args:
            feishu_client: 飞书客户端实例
        """
        super().__init__(
            name="chat_summary",
            description="群聊消息总结模块，支持总结群聊历史消息"
        )
        self.feishu_client = feishu_client
        self._setup_llm()
        self._setup_text_splitter()

    def _setup_llm(self):
        """设置大语言模型"""
        if not settings.OPENAI_API_KEY:
            self.llm = None
            return

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
            temperature=0.3,
        )

    def _setup_text_splitter(self):
        """设置文本分割器"""
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=8000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )

    def _parse_time_range(self, user_input: str) -> Dict[str, Any]:
        """
        从用户输入中解析时间区间

        Args:
            user_input: 用户输入

        Returns:
            包含时间区间的字典，格式：
            - {"has_time_range": True, "start_time": timestamp, "end_time": timestamp}
            - {"has_time_range": False}
        """
        now = datetime.now()
        start_time = None
        end_time = None
        has_time_range = False

        msg_lower = user_input.lower()

        # 检查是否有明确的时间区间关键词
        time_keywords = [
            "今天", "昨天", "前天",
            "本周", "上周", "上一周",
            "本月", "上个月", "上月",
            "小时", "分钟",
            "从", "到", "至",
            "早上", "上午", "中午", "下午", "晚上", "凌晨",
        ]

        has_time_keyword = any(kw in msg_lower for kw in time_keywords)

        # 解析 "过去X小时"、"最近X小时"
        past_hours_pattern = r'(?:过去|最近|近)(\d+)(?:小时|h)'
        match = re.search(past_hours_pattern, msg_lower)
        if match:
            hours = int(match.group(1))
            end_time = int(now.timestamp())
            start_time = int((now - timedelta(hours=hours)).timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 过去{hours}小时")

        # 解析 "过去X分钟"、"最近X分钟"
        past_minutes_pattern = r'(?:过去|最近|近)(\d+)(?:分钟|min)'
        match = re.search(past_minutes_pattern, msg_lower)
        if match and not has_time_range:
            minutes = int(match.group(1))
            end_time = int(now.timestamp())
            start_time = int((now - timedelta(minutes=minutes)).timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 过去{minutes}分钟")

        # 解析 "今天"
        if "今天" in msg_lower and not has_time_range:
            today_start = datetime(now.year, now.month, now.day, 0, 0, 0)
            start_time = int(today_start.timestamp())
            end_time = int(now.timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 今天")

        # 解析 "昨天"
        if "昨天" in msg_lower and not has_time_range:
            yesterday = now - timedelta(days=1)
            yesterday_start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
            yesterday_end = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)
            start_time = int(yesterday_start.timestamp())
            end_time = int(yesterday_end.timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 昨天")

        # 解析 "前天"
        if "前天" in msg_lower and not has_time_range:
            day_before_yesterday = now - timedelta(days=2)
            start = datetime(day_before_yesterday.year, day_before_yesterday.month, day_before_yesterday.day, 0, 0, 0)
            end = datetime(day_before_yesterday.year, day_before_yesterday.month, day_before_yesterday.day, 23, 59, 59)
            start_time = int(start.timestamp())
            end_time = int(end.timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 前天")

        # 解析 "本周"
        if "本周" in msg_lower and not has_time_range:
            start_of_week = now - timedelta(days=now.weekday())
            week_start = datetime(start_of_week.year, start_of_week.month, start_of_week.day, 0, 0, 0)
            start_time = int(week_start.timestamp())
            end_time = int(now.timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 本周")

        # 解析 "上周"
        if ("上周" in msg_lower or "上一周" in msg_lower) and not has_time_range:
            start_of_week = now - timedelta(days=now.weekday())
            last_week_start = start_of_week - timedelta(days=7)
            last_week_end = start_of_week - timedelta(seconds=1)
            start_time = int(last_week_start.timestamp())
            end_time = int(last_week_end.timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 上周")

        # 解析 "本月"
        if "本月" in msg_lower and not has_time_range:
            month_start = datetime(now.year, now.month, 1, 0, 0, 0)
            start_time = int(month_start.timestamp())
            end_time = int(now.timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 本月")

        # 解析 "上个月"、"上月"
        if ("上个月" in msg_lower or "上月" in msg_lower) and not has_time_range:
            if now.month == 1:
                last_month = 12
                last_month_year = now.year - 1
            else:
                last_month = now.month - 1
                last_month_year = now.year

            if last_month == 12:
                next_month = 1
                next_month_year = last_month_year + 1
            else:
                next_month = last_month + 1
                next_month_year = last_month_year

            last_month_start = datetime(last_month_year, last_month, 1, 0, 0, 0)
            last_month_end = datetime(next_month_year, next_month, 1, 0, 0, 0) - timedelta(seconds=1)
            start_time = int(last_month_start.timestamp())
            end_time = int(last_month_end.timestamp())
            has_time_range = True
            logger.info(f"解析到时间区间: 上个月")

        # 解析具体日期格式，如 "2024年1月1日"、"1月1日"、"01-01"
        date_patterns = [
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            r'(\d{1,2})月(\d{1,2})日',
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            r'(\d{1,2})/(\d{1,2})/(\d{4})',
        ]

        for pattern in date_patterns:
            matches = list(re.finditer(pattern, user_input))
            if len(matches) >= 2 and not has_time_range:
                # 找到两个日期，可能是 "从X到Y" 的格式
                try:
                    date1 = self._parse_match_to_datetime(matches[0], now)
                    date2 = self._parse_match_to_datetime(matches[1], now)

                    if date1 and date2:
                        if date1 > date2:
                            date1, date2 = date2, date1

                        start_time = int(date1.timestamp())
                        end_time = int(date2.timestamp())
                        has_time_range = True
                        logger.info(f"解析到时间区间: {date1} 到 {date2}")
                        break
                except Exception as e:
                    logger.warning(f"解析日期失败: {e}")

        return {
            "has_time_range": has_time_range,
            "start_time": start_time,
            "end_time": end_time,
        }

    def _parse_match_to_datetime(self, match, now: datetime) -> Optional[datetime]:
        """
        将正则匹配结果解析为datetime对象

        Args:
            match: 正则匹配对象
            now: 当前时间

        Returns:
            datetime对象或None
        """
        groups = match.groups()

        if len(groups) == 3:
            # 完整日期格式，包含年
            if groups[0].isdigit() and len(groups[0]) == 4:
                # 格式: 2024-01-01 或 2024年1月1日
                year = int(groups[0])
                month = int(groups[1])
                day = int(groups[2])
            else:
                # 格式: 01/01/2024 (月/日/年)
                month = int(groups[0])
                day = int(groups[1])
                year = int(groups[2])
        elif len(groups) == 2:
            # 只有月日，使用当前年
            month = int(groups[0])
            day = int(groups[1])
            year = now.year
        else:
            return None

        try:
            return datetime(year, month, day, 0, 0, 0)
        except ValueError:
            return None

    def _parse_timestamp(self, timestamp) -> int:
        """
        解析时间戳，自动处理毫秒级和秒级时间戳

        飞书API返回的时间戳通常是毫秒级的（13位数字），
        但也可能是秒级的（10位数字）。

        Args:
            timestamp: 时间戳，可以是字符串或数字

        Returns:
            秒级时间戳的整数
        """
        if timestamp is None:
            return 0

        try:
            ts = int(timestamp)
            # 如果是毫秒级时间戳（13位数字），转换为秒级
            if ts > 9999999999:  # 大于 2286-11-21 的秒级时间戳
                return ts // 1000
            return ts
        except (ValueError, TypeError):
            return 0

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        格式化消息列表为可读文本

        Args:
            messages: 消息列表

        Returns:
            格式化后的文本
        """
        if not messages:
            logger.debug("消息列表为空，无内容可格式化")
            return ""

        logger.debug(f"开始格式化 {len(messages)} 条消息")

        formatted_lines = []

        for i, msg in enumerate(messages):
            msg_type = msg.get("msg_type", "")
            content_str = msg.get("content")
            create_time = msg.get("create_time", "")
            sender = msg.get("sender", {})
            sender_id = sender.get("sender_id", {})

            user_name = sender_id.get("open_id", "") or sender_id.get("user_id", "") or "未知用户"

            logger.debug(f"消息 {i+1}: msg_type={msg_type}, content={content_str[:100] if content_str else 'None'}..., user_name={user_name}")

            if content_str is None:
                formatted_msg = f"[{user_name}] [无内容]"
                logger.warning(f"消息 {i+1} 内容为空")
            else:
                formatted_msg = self._parse_message_content(content_str, msg_type, user_name)

            if create_time:
                try:
                    ts = self._parse_timestamp(create_time)
                    if ts > 0:
                        dt = datetime.fromtimestamp(ts)
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        formatted_lines.append(f"[{time_str}] {formatted_msg}")
                    else:
                        formatted_lines.append(formatted_msg)
                except (ValueError, TypeError, OSError):
                    formatted_lines.append(formatted_msg)
            else:
                formatted_lines.append(formatted_msg)

        result = "\n".join(formatted_lines)
        logger.debug(f"格式化完成，结果长度: {len(result)} 字符")
        if result:
            logger.debug(f"格式化结果预览: {result[:200]}...")

        return result

    def _parse_message_content(self, content_str: str, msg_type: str, user_name: str) -> str:
        """
        解析飞书消息内容
        飞书API返回的content格式通常是JSON字符串，如 '{"text":"你好"}'

        Args:
            content_str: 消息内容字符串
            msg_type: 消息类型
            user_name: 用户名

        Returns:
            解析后的格式化消息
        """
        if not content_str:
            return f"[{user_name}] [无内容]"

        try:
            content = json.loads(content_str)
            if msg_type == "text":
                text = content.get("text", "")
                if text:
                    return f"[{user_name}] {text}"
                else:
                    return f"[{user_name}] [文本消息]"
            elif msg_type == "post":
                return f"[{user_name}] [富文本消息]"
            elif msg_type == "image":
                return f"[{user_name}] [图片]"
            elif msg_type == "file":
                return f"[{user_name}] [文件]"
            elif msg_type == "media":
                return f"[{user_name}] [视频/音频]"
            elif msg_type == "sticker":
                return f"[{user_name}] [表情]"
            else:
                return f"[{user_name}] [{msg_type}消息]"
        except json.JSONDecodeError:
            pass

        if ":" in content_str:
            colon_index = content_str.find(":")
            content_type = content_str[:colon_index]
            actual_content = content_str[colon_index + 1:]

            if content_type == "text":
                return f"[{user_name}] {actual_content}"
            elif content_type == "post":
                try:
                    post_content = json.loads(actual_content)
                    return f"[{user_name}] [富文本消息]"
                except json.JSONDecodeError:
                    return f"[{user_name}] [富文本消息]"
            elif content_type == "image":
                return f"[{user_name}] [图片]"
            elif content_type == "file":
                return f"[{user_name}] [文件]"
            elif content_type == "media":
                return f"[{user_name}] [视频/音频]"
            elif content_type == "sticker":
                return f"[{user_name}] [表情]"
            else:
                return f"[{user_name}] {content_str}"

        return f"[{user_name}] {content_str}"

    async def _summarize_messages(self, messages: List[Dict[str, Any]], chat_id: str) -> str:
        """
        总结群聊消息

        Args:
            messages: 消息列表
            chat_id: 群聊ID

        Returns:
            消息总结
        """
        if not messages:
            logger.warning("消息列表为空，无法进行总结")
            return "当前群聊中没有找到可总结的消息。"

        if self.llm is None:
            logger.error("大语言模型未配置")
            return "抱歉，大语言模型未配置，无法进行消息总结。"

        formatted_content = self._format_messages(messages)

        if not formatted_content.strip():
            logger.warning("格式化后的消息内容为空")
            return "当前群聊中没有找到可总结的文本消息。"

        logger.info(f"准备总结的消息内容长度: {len(formatted_content)} 字符")
        logger.debug(f"准备发送给LLM的内容: {formatted_content[:500]}...")

        try:
            chunks = self.text_splitter.split_text(formatted_content)
            logger.info(f"消息内容被分割为 {len(chunks)} 个块")

            if len(chunks) == 1:
                return await self._summarize_single_chunk(formatted_content, len(messages))
            else:
                return await self._summarize_multiple_chunks(chunks, len(messages))

        except Exception as e:
            logger.error(f"消息总结失败: {str(e)}", exc_info=True)
            return f"消息总结时出错: {str(e)}"

    async def _summarize_single_chunk(self, content: str, message_count: int) -> str:
        """
        总结单块消息内容

        Args:
            content: 内容
            message_count: 消息数量

        Returns:
            摘要
        """
        logger.info(f"开始调用LLM总结: message_count={message_count}, content_length={len(content)}")

        system_prompt = """你是一个贴心的群聊消息总结助手 📝。我会用心阅读群聊消息，为你生成一个清晰、全面且易于理解的总结。

【我的目标】
帮助你快速了解群聊的核心内容，节省宝贵的时间！⏱️

请按照以下友好的结构生成总结：
1. **📋 群聊概述**（1-2句话概括群聊主要讨论的内容）- 用亲切的语言描述大家在聊什么
2. **✨ 核心话题**（列出3-5个最重要的讨论话题）- 清晰、简洁地列出关键讨论点
3. **💡 重要结论/决定**（如果有的话）- 总结群聊中的主要结论、决定或行动项
4. **👥 参与讨论的人员**（可选）- 如果有重要人物或多人参与，可以简要提及

【温馨提示】
请确保总结：
- ✅ 准确反映群聊的核心内容，不添加消息中没有的信息
- ✅ 语言简洁明了，但不失亲切和温暖
- ✅ 结构清晰，让读者一目了然
- ✅ 如果有重要的决定、行动项或待办事项，特别指出
- ✅ 注意消息的时间顺序，理解对话的上下文

消息数量：{message_count} 条

让我们一起把这段群聊消息变得更加易懂吧！😊"""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "群聊消息：\n{content}\n\n请生成该群聊消息的总结："),
            ]
        )

        chain = prompt | self.llm | StrOutputParser()

        logger.debug(f"发送给LLM的完整内容: {content[:1000]}...")

        try:
            summary = await chain.ainvoke({
                "content": content,
                "message_count": message_count,
            })

            logger.info(f"LLM原始回复长度: {len(summary) if summary else 0} 字符")
            logger.debug(f"LLM原始回复: {summary[:500] if summary else 'None'}...")

            summary = clean_model_output(summary)

            logger.info(f"清理后的回复长度: {len(summary) if summary else 0} 字符")
            logger.debug(f"清理后的回复: {summary[:500] if summary else 'None'}...")

            return summary
        except Exception as e:
            logger.error(f"LLM调用失败: {str(e)}", exc_info=True)
            return f"调用大语言模型时出错: {str(e)}"

    async def _summarize_multiple_chunks(self, chunks: List[str], total_message_count: int) -> str:
        """
        总结多块消息内容（使用Map-Reduce方式）

        Args:
            chunks: 内容块列表
            total_message_count: 总消息数量

        Returns:
            综合摘要
        """
        chunk_summaries = []

        for i, chunk in enumerate(chunks):
            logger.info(f"处理第 {i+1}/{len(chunks)} 个消息块")

            chunk_summary = await self._summarize_single_chunk(
                chunk,
                0  # 分块时不显示具体数量
            )
            chunk_summaries.append(chunk_summary)

        combined_summary = "\n\n".join([
            f"## 第 {i+1} 部分摘要\n{summary}"
            for i, summary in enumerate(chunk_summaries)
        ])

        final_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """你是一个贴心的群聊消息总结助手 📝。我会整合多个消息块的摘要，为你生成一个完整、清晰的综合消息总结。

【我的目标】
帮你全面了解这段群聊的核心内容，让阅读变得轻松愉快！✨

请按照以下友好的结构生成综合总结：
1. **📋 群聊概述**（1-2句话概括群聊主要讨论的内容）- 用亲切的语言描述整个群聊的主题
2. **✨ 核心话题**（列出3-5个最重要的讨论话题）- 整合所有部分的关键信息，避免重复
3. **💡 重要结论/决定**（如果有的话）- 总结群聊中的主要结论、决定或行动项
4. **👥 参与讨论的人员**（可选）- 如果有重要人物或多人参与，可以简要提及

【温馨提示】
请确保综合总结：
- ✅ 整合所有部分的核心内容，不遗漏重要信息
- ✅ 避免重复，保持内容简洁
- ✅ 准确反映群聊的整体结构和内容
- ✅ 语言亲切温暖，让读者感受到被关心
- ✅ 如果有重要的决定、行动项或待办事项，特别指出

总消息数量：{total_message_count} 条

让我们一起把这段群聊消息变得更加易懂吧！😊"""),
                ("human", "各部分摘要：\n{combined_summary}\n\n请生成综合总结："),
            ]
        )

        chain = final_prompt | self.llm | StrOutputParser()

        final_summary = await chain.ainvoke({
            "total_message_count": total_message_count,
            "combined_summary": combined_summary,
        })

        final_summary = clean_model_output(final_summary)

        return final_summary

    async def _summarize_chat(
        self,
        chat_id: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        max_messages: int = 100,
    ) -> str:
        """
        总结群聊消息

        Args:
            chat_id: 群聊ID
            start_time: 开始时间戳（可选）
            end_time: 结束时间戳（可选）
            max_messages: 最大获取消息数量

        Returns:
            总结结果
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法获取群聊消息。请先配置飞书应用凭证。"

        try:
            logger.info(f"总结群聊消息: chat_id={chat_id}")

            # 构建时间范围描述
            time_range_desc = ""
            if start_time and end_time:
                start_dt = datetime.fromtimestamp(start_time)
                end_dt = datetime.fromtimestamp(end_time)
                time_range_desc = f" (时间范围: {start_dt.strftime('%Y-%m-%d %H:%M')} 到 {end_dt.strftime('%Y-%m-%d %H:%M')})"
            elif start_time:
                start_dt = datetime.fromtimestamp(start_time)
                time_range_desc = f" (从 {start_dt.strftime('%Y-%m-%d %H:%M')} 开始)"

            # 获取群聊历史消息
            result = await self.feishu_client.get_chat_history(
                chat_id=chat_id,
                start_time=start_time,
                end_time=end_time,
                max_results=max_messages,
            )

            if not result.get("success"):
                return f"获取群聊消息失败: {result.get('message', '未知错误')}"

            messages = result.get("messages", [])

            if not messages:
                if time_range_desc:
                    return f"当前群聊{time_range_desc}中没有找到可总结的消息。"
                else:
                    return "当前群聊中没有找到可总结的消息。"

            logger.info(f"成功获取 {len(messages)} 条消息，开始总结...")

            # 总结消息
            summary = await self._summarize_messages(messages, chat_id)

            response = f"# 群聊消息总结{time_range_desc}\n\n"
            response += f"📊 共获取到 {len(messages)} 条消息\n\n"
            response += f"## 总结内容\n\n{summary}\n\n"
            response += f"---\n"
            response += f"*群聊ID: {chat_id}*\n"
            if messages:
                first_msg = messages[0]
                last_msg = messages[-1]
                if first_msg.get("create_time") and last_msg.get("create_time"):
                    try:
                        first_ts = self._parse_timestamp(first_msg["create_time"])
                        last_ts = self._parse_timestamp(last_msg["create_time"])
                        if first_ts > 0 and last_ts > 0:
                            first_dt = datetime.fromtimestamp(first_ts)
                            last_dt = datetime.fromtimestamp(last_ts)
                            response += f"*消息时间范围: {first_dt.strftime('%Y-%m-%d %H:%M')} 到 {last_dt.strftime('%Y-%m-%d %H:%M')}*\n"
                    except (ValueError, TypeError, OSError):
                        pass

            return response

        except Exception as e:
            logger.error(f"总结群聊消息失败: {str(e)}", exc_info=True)
            return f"总结群聊消息时出错: {str(e)}"

    async def execute(
        self,
        user_input: str,
        conversation_history: List[BaseMessage],
        chat_id: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """
        执行群聊消息总结功能

        Args:
            user_input: 用户输入
            conversation_history: 对话历史
            chat_id: 群聊ID（必需）
            **kwargs: 其他参数

        Returns:
            执行结果字符串
        """
        logger.info(f"群聊总结模块处理用户输入: {user_input}")

        if not chat_id:
            return "抱歉，无法获取群聊ID，无法进行消息总结。请确保在群聊中使用此功能。"

        # 解析时间区间
        time_range = self._parse_time_range(user_input)

        if time_range["has_time_range"]:
            logger.info(f"检测到时间区间，按时间范围总结消息")
            return await self._summarize_chat(
                chat_id=chat_id,
                start_time=time_range.get("start_time"),
                end_time=time_range.get("end_time"),
            )
        else:
            logger.info(f"未检测到时间区间，总结最近的消息")
            return await self._summarize_chat(
                chat_id=chat_id,
            )
