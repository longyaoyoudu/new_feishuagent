from typing import List, Any, Dict, Optional
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
import json
import re

from config import settings
from utils import logger, FeishuClient, clean_model_output
from modules.base_module import BaseModule


class DocumentModule(BaseModule):
    """云文档管理模块"""

    def __init__(self, feishu_client: Optional[FeishuClient] = None):
        """
        初始化云文档管理模块

        Args:
            feishu_client: 飞书客户端实例
        """
        super().__init__(
            name="document",
            description="云文档管理模块，支持读取、总结飞书云文档内容"
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
            chunk_size=4000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "。", "，", " ", ""],
        )

    def _extract_document_token(self, user_input: str) -> Optional[Dict[str, Any]]:
        """
        从用户输入中提取文档token和类型

        Args:
            user_input: 用户输入

        Returns:
            包含token和类型的字典，如果未找到则返回None
            格式: {"token": "xxx", "type": "wiki"|"document"|"unknown"}
        """
        MIN_TOKEN_LENGTH = 27

        # 先检查是否是知识库链接
        wiki_pattern = r'https?://[^\s]*?/wiki/([a-zA-Z0-9]+)'
        match = re.search(wiki_pattern, user_input)
        if match:
            token = match.group(1).strip()
            if len(token) >= MIN_TOKEN_LENGTH:
                logger.info(f"从用户输入中提取到知识库节点token: {token}")
                return {"token": token, "type": "wiki"}

        # 检查是否是普通文档链接
        doc_link_patterns = [
            r'https?://[^\s]*?/doc/([a-zA-Z0-9]+)',
            r'https?://[^\s]*?/docx/([a-zA-Z0-9]+)',
        ]

        for pattern in doc_link_patterns:
            match = re.search(pattern, user_input)
            if match:
                token = match.group(1).strip()
                if len(token) >= MIN_TOKEN_LENGTH:
                    logger.info(f"从用户输入中提取到文档token: {token}")
                    return {"token": token, "type": "document"}

        # 检查是否是显式的文档ID格式（如 "文档ID: xxx" 或 "文档token: xxx"）
        # 这种情况下需要同时有文档相关关键词和足够长度的token
        doc_id_patterns = [
            r'文档(?:ID|token|编号)?[:：\s]+([a-zA-Z0-9]+)',
        ]

        for pattern in doc_id_patterns:
            match = re.search(pattern, user_input)
            if match:
                token = match.group(1).strip()
                if len(token) >= MIN_TOKEN_LENGTH:
                    logger.info(f"从用户输入中提取到文档token: {token}")
                    return {"token": token, "type": "document"}

        return None

    async def _summarize_content(self, content: str, title: str = "") -> str:
        """
        总结文档内容

        Args:
            content: 文档内容
            title: 文档标题

        Returns:
            文档摘要
        """
        if self.llm is None:
            return "抱歉，大语言模型未配置，无法进行文档总结。"

        try:
            chunks = self.text_splitter.split_text(content)

            if len(chunks) == 1:
                return await self._summarize_single_chunk(content, title)
            else:
                return await self._summarize_multiple_chunks(chunks, title)

        except Exception as e:
            logger.error(f"文档总结失败: {str(e)}")
            return f"文档总结时出错: {str(e)}"

    async def _summarize_single_chunk(self, content: str, title: str) -> str:
        """
        总结单块内容

        Args:
            content: 内容
            title: 标题

        Returns:
            摘要
        """
        system_prompt = """你是一个贴心的文档摘要助手 📄。我会用心阅读文档内容，为你生成一个清晰、全面且易于理解的摘要。

【我的目标】
帮助你快速了解文档的核心内容，节省宝贵的时间！⏱️

请按照以下友好的结构生成摘要：
1. **📋 文档概述**（1-2句话概括文档主要内容）- 用亲切的语言描述文档讲了什么
2. **✨ 核心要点**（列出3-5个最重要的要点）- 清晰、简洁地列出关键信息
3. **💡 关键结论**（如果有的话）- 总结文档的主要结论或建议

【温馨提示】
请确保摘要：
- ✅ 准确反映文档的核心内容，不添加文档中没有的信息
- ✅ 语言简洁明了，但不失亲切和温暖
- ✅ 结构清晰，让读者一目了然
- ✅ 如果文档中有重要的建议或行动项，特别指出

文档标题：{title}

让我们一起把这份文档变得更加易懂吧！😊"""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "文档内容：\n{content}\n\n请生成该文档的摘要："),
            ]
        )

        chain = prompt | self.llm | StrOutputParser()

        summary = await chain.ainvoke({
            "title": title,
            "content": content,
        })

        summary = clean_model_output(summary)

        return summary

    async def _summarize_multiple_chunks(self, chunks: List[str], title: str) -> str:
        """
        总结多块内容（使用Map-Reduce方式）

        Args:
            chunks: 内容块列表
            title: 标题

        Returns:
            综合摘要
        """
        chunk_summaries = []

        for i, chunk in enumerate(chunks):
            logger.info(f"处理第 {i+1}/{len(chunks)} 个内容块")

            chunk_summary = await self._summarize_single_chunk(
                chunk,
                f"{title} (第 {i+1} 部分)"
            )
            chunk_summaries.append(chunk_summary)

        combined_summary = "\n\n".join([
            f"## 第 {i+1} 部分摘要\n{summary}"
            for i, summary in enumerate(chunk_summaries)
        ])

        final_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", """你是一个贴心的文档摘要助手 📄。我会整合多个内容块的摘要，为你生成一个完整、清晰的综合文档摘要。

【我的目标】
帮你全面了解这份长文档的核心内容，让阅读变得轻松愉快！✨

请按照以下友好的结构生成综合摘要：
1. **📋 文档概述**（1-2句话概括文档主要内容）- 用亲切的语言描述整个文档的主题
2. **✨ 核心要点**（列出3-5个最重要的要点）- 整合所有部分的关键信息，避免重复
3. **💡 关键结论**（如果有的话）- 总结文档的主要结论或建议

【温馨提示】
请确保综合摘要：
- ✅ 整合所有部分的核心内容，不遗漏重要信息
- ✅ 避免重复，保持内容简洁
- ✅ 准确反映文档的整体结构和内容
- ✅ 语言亲切温暖，让读者感受到被关心
- ✅ 如果文档中有重要的建议或行动项，特别指出

文档标题：{title}

让我们一起把这份长文档变得更加易懂吧！😊"""),
                ("human", "各部分摘要：\n{combined_summary}\n\n请生成综合摘要："),
            ]
        )

        chain = final_prompt | self.llm | StrOutputParser()

        final_summary = await chain.ainvoke({
            "title": title,
            "combined_summary": combined_summary,
        })

        final_summary = clean_model_output(final_summary)

        return final_summary

    async def _read_document(self, token: str, token_type: str = "document") -> str:
        """
        读取文档内容

        Args:
            token: 文档token或知识库节点token
            token_type: token类型，"document"或"wiki"

        Returns:
            文档内容描述
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法读取云文档。请先配置飞书应用凭证。"

        try:
            document_token = token
            actual_title = None

            # 如果是知识库节点，先转换为实际的文档token
            if token_type == "wiki":
                logger.info(f"检测到知识库节点token: {token}，正在转换为实际文档token...")

                wiki_result = await self.feishu_client.get_wiki_node_info(token)

                if not wiki_result.get("success"):
                    return f"获取知识库节点信息失败: {wiki_result.get('message', '未知错误')}"

                node = wiki_result.get("node", {})
                obj_token = node.get("obj_token")
                obj_type = node.get("obj_type")
                actual_title = node.get("title")

                if not obj_token:
                    return f"知识库节点 '{token}' 没有关联的文档，或无法获取文档信息。"

                logger.info(f"知识库节点转换成功: node_token={token} -> obj_token={obj_token}, obj_type={obj_type}")

                # 检查是否支持的文档类型
                if obj_type not in ["doc", "docx"]:
                    return f"该知识库节点类型为 '{obj_type}'，目前只支持读取文档类型（doc/docx）的内容。"

                document_token = obj_token

            logger.info(f"读取云文档: {document_token}")

            result = await self.feishu_client.get_document_content(document_token)

            if not result.get("success"):
                return f"读取文档失败: {result.get('message', '未知错误')}"

            document = result.get("document", {})
            title = actual_title or document.get("title", "无标题")
            content = document.get("content", "")

            if not content:
                return f"文档 '{title}' 内容为空。"

            logger.info(f"成功读取文档: {title}，内容长度: {len(content)}")

            summary = await self._summarize_content(content, title)

            response = f"# 文档：{title}\n\n"
            if token_type == "wiki":
                response += f"*(来自知识库节点)*\n\n"
            response += f"## 文档摘要\n\n{summary}\n\n"
            response += f"---\n"
            response += f"*文档ID: {document_token}*\n"
            response += f"*内容长度: {len(content)} 字符*\n"

            return response

        except Exception as e:
            logger.error(f"读取文档失败: {str(e)}", exc_info=True)
            return f"读取文档时出错: {str(e)}"

    async def execute(
        self,
        user_input: str,
        conversation_history: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        执行云文档管理功能

        Args:
            user_input: 用户输入
            conversation_history: 对话历史
            **kwargs: 其他参数

        Returns:
            执行结果字符串
        """
        logger.info(f"云文档模块处理用户输入: {user_input}")

        token_info = self._extract_document_token(user_input)

        if token_info:
            token = token_info.get("token")
            token_type = token_info.get("type", "document")
            return await self._read_document(token, token_type)
        else:
            return "我理解您想操作云文档，但我需要文档的链接或文档ID。请提供云文档的链接或文档ID，我将为您读取并总结文档内容。"
