from typing import List, Any, Dict, Optional
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
import json
import re
from difflib import SequenceMatcher

from config import settings
from utils import logger, FeishuClient, clean_model_output, safe_json_loads
from modules.base_module import BaseModule


class SpreadsheetModule(BaseModule):
    """电子表格管理模块"""

    FIELD_TYPE_MAP = {
        "文本": 1,
        "多行文本": 1,
        "数字": 2,
        "单选": 3,
        "多选": 4,
        "日期": 5,
        "复选框": 7,
        "人员": 11,
        "超链接": 15,
        "创建人": 20,
        "创建时间": 21,
        "修改人": 22,
        "修改时间": 23,
        "自动编号": 1001,
    }

    def __init__(self, feishu_client: Optional[FeishuClient] = None):
        """
        初始化电子表格管理模块

        Args:
            feishu_client: 飞书客户端实例
        """
        super().__init__(
            name="spreadsheet",
            description="电子表格管理模块，支持创建多维表格、读写单元格、批量更新数据"
        )
        self.feishu_client = feishu_client
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
            temperature=0.3,
        )

    def _extract_bitable_token(self, user_input: str) -> Optional[str]:
        """
        从用户输入中提取多维表格token

        Args:
            user_input: 用户输入

        Returns:
            多维表格token，如果未找到则返回None
        """
        MIN_TOKEN_LENGTH = 20

        patterns = [
            r'https?://[^\s]*?/base/([a-zA-Z0-9]+)',
            r'多维表格(?:token|编号)?[:：\s]+([a-zA-Z0-9]+)',
            r'表格(?:token|编号)?[:：\s]+([a-zA-Z0-9]+)',
            r'token[:：\s]+([a-zA-Z0-9]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                token = match.group(1).strip()
                if len(token) >= MIN_TOKEN_LENGTH:
                    logger.info(f"从用户输入中提取到多维表格token: {token}")
                    return token

        return None

    def _extract_table_id(self, user_input: str) -> Optional[str]:
        """
        从用户输入中提取数据表ID

        Args:
            user_input: 用户输入

        Returns:
            数据表ID，如果未找到则返回None
        """
        patterns = [
            r'数据表(?:ID|编号)?[:：\s]+([a-zA-Z0-9_]+)',
            r'table(?:_id)?[:：\s]+([a-zA-Z0-9_]+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input, re.IGNORECASE)
            if match:
                table_id = match.group(1).strip()
                logger.info(f"从用户输入中提取到数据表ID: {table_id}")
                return table_id

        return None

    def _extract_table_name(self, user_input: str) -> Optional[str]:
        """
        从用户输入中提取数据表名称

        Args:
            user_input: 用户输入

        Returns:
            数据表名称，如果未找到则返回None
        """
        patterns = [
            r'(?:在|的)\s*([a-zA-Z0-9_]+?)\s*中',
            r'(?:数据表|表|表格)\s*[:：\s]*([a-zA-Z0-9_]+)',
            r'([a-zA-Z0-9_]+?)\s*(?:中|里)',
        ]

        excluded_words = [
            '添加', '插入', '写入', '修改', '更新', '删除',
            '查看', '读取', '查询', '一条', '记录', '数据',
            '字段', '信息', '结构', '列表', '显示', '批量',
            '多维表格', '多维', '客户管理', '表格',
        ]

        for pattern in patterns:
            match = re.search(pattern, user_input)
            if match:
                table_name = match.group(1).strip()
                if table_name and table_name not in excluded_words and len(table_name) >= 2:
                    logger.info(f"从用户输入中提取到数据表名称: {table_name}")
                    return table_name

        return None

    def _string_similarity(self, s1: str, s2: str) -> float:
        """
        计算两个字符串的相似度

        Args:
            s1: 第一个字符串
            s2: 第二个字符串

        Returns:
            相似度（0.0 - 1.0）
        """
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    async def _select_table_by_name(
        self,
        app_token: str,
        table_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        根据表名选择对应的数据表

        Args:
            app_token: 多维表格token
            table_name: 数据表名称

        Returns:
            数据表信息（包含 table_id 和 name），如果未找到则返回None
        """
        if self.feishu_client is None:
            return None

        tables_result = await self.feishu_client.list_tables(app_token)
        if not tables_result.get("success"):
            return None

        tables = tables_result.get("tables", [])
        if not tables:
            return None

        normalized_target = self._normalize_field_name(table_name)

        for table in tables:
            normalized_name = self._normalize_field_name(table.get("name", ""))
            if normalized_name == normalized_target:
                logger.info(f"根据表名 '{table_name}' 精确匹配到数据表: {table.get('name')} (ID: {table.get('table_id')})")
                return table

        for table in tables:
            normalized_name = self._normalize_field_name(table.get("name", ""))
            if normalized_target in normalized_name or normalized_name in normalized_target:
                logger.info(f"根据表名 '{table_name}' 包含匹配到数据表: {table.get('name')} (ID: {table.get('table_id')})")
                return table

        SIMILARITY_THRESHOLD = 0.7
        best_match = None
        best_similarity = 0.0

        for table in tables:
            actual_name = table.get("name", "")
            similarity = self._string_similarity(table_name, actual_name)
            logger.debug(f"表名相似度: '{table_name}' vs '{actual_name}' = {similarity:.2f}")

            if similarity > best_similarity and similarity >= SIMILARITY_THRESHOLD:
                best_similarity = similarity
                best_match = table

        if best_match:
            logger.info(f"根据表名 '{table_name}' 相似度匹配到数据表: {best_match.get('name')} (ID: {best_match.get('table_id')}, 相似度: {best_similarity:.2f})")
            return best_match

        logger.warning(f"未找到表名 '{table_name}' 对应的数据表")
        return None

    async def _get_target_table_id(
        self,
        app_token: str,
        user_input: str
    ) -> Optional[str]:
        """
        获取目标数据表ID，优先级：
        1. 用户输入中明确指定的 table_id
        2. 用户输入中提到的表名（精确匹配或模糊匹配）
        3. 默认使用第一个表

        Args:
            app_token: 多维表格token
            user_input: 用户输入

        Returns:
            数据表ID，如果未找到则返回None
        """
        table_id = self._extract_table_id(user_input)
        if table_id:
            return table_id

        table_name = self._extract_table_name(user_input)
        if table_name:
            matched_table = await self._select_table_by_name(app_token, table_name)
            if matched_table:
                return matched_table.get("table_id")

        if self.feishu_client is None:
            return None

        tables_result = await self.feishu_client.list_tables(app_token)
        if tables_result.get("success") and len(tables_result.get("tables", [])) > 0:
            default_table = tables_result["tables"][0]
            logger.info(f"使用默认第一个数据表: {default_table.get('name')} (ID: {default_table.get('table_id')})")
            return default_table["table_id"]

        return None

    def _normalize_field_name(self, name: str) -> str:
        """
        标准化字段名称，用于模糊匹配

        Args:
            name: 原始字段名

        Returns:
            标准化后的字段名（去除空格、特殊字符，转为小写）
        """
        normalized = re.sub(r'[\s_\-~@#$%^&*()\[\]{}|\\;:\'\"<>,.?/`！@#￥%……&*（）——+【】{}|；：""''《》，。？、·\n\r\t]', '', name)
        return normalized.lower()

    async def _match_field_names(
        self,
        app_token: str,
        table_id: str,
        input_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        将用户输入的字段名与表格实际字段名进行匹配

        Args:
            app_token: 多维表格token
            table_id: 数据表ID
            input_fields: 用户输入的字段数据

        Returns:
            匹配后的字段数据，包含匹配结果信息
        """
        if self.feishu_client is None:
            return {"success": False, "message": "飞书客户端未配置", "fields": {}}

        fields_result = await self.feishu_client.list_fields(app_token, table_id)
        if not fields_result.get("success"):
            return {
                "success": False,
                "message": f"获取表格字段列表失败: {fields_result.get('message', '未知错误')}",
                "fields": {}
            }

        actual_fields = fields_result.get("fields", [])
        if not actual_fields:
            return {"success": False, "message": "表格中没有字段", "fields": {}}

        actual_field_map = {}
        for field in actual_fields:
            field_name = field.get("field_name", "")
            field_id = field.get("field_id", "")
            normalized = self._normalize_field_name(field_name)
            actual_field_map[normalized] = {
                "field_name": field_name,
                "field_id": field_id,
                "original": field_name
            }

        matched_fields = {}
        unmatched_fields = []
        matched_info = []

        for input_name, value in input_fields.items():
            normalized_input = self._normalize_field_name(input_name)

            if normalized_input in actual_field_map:
                actual = actual_field_map[normalized_input]
                actual_name = actual["field_name"]
                matched_fields[actual_name] = value
                if input_name != actual_name:
                    matched_info.append(f"'{input_name}' -> '{actual_name}'")
                else:
                    matched_info.append(f"'{input_name}' 匹配成功")
            else:
                unmatched_fields.append(input_name)

        result = {
            "success": True,
            "fields": matched_fields,
            "unmatched": unmatched_fields,
            "matched_info": matched_info,
            "actual_fields": [f.get("field_name", "") for f in actual_fields]
        }

        if unmatched_fields:
            result["message"] = f"以下字段未找到匹配: {', '.join(unmatched_fields)}。表格实际字段: {', '.join(result['actual_fields'])}"
        else:
            result["message"] = "所有字段匹配成功"

        logger.info(f"字段匹配结果: {len(matched_fields)} 个匹配成功, {len(unmatched_fields)} 个未匹配")

        return result

    async def _parse_create_bitable_request(self, user_input: str, conversation_history: List[BaseMessage]) -> Dict[str, Any]:
        """
        解析创建多维表格的请求

        Args:
            user_input: 用户输入
            conversation_history: 对话历史

        Returns:
            解析结果，包含 name 和可选的 fields
        """
        if self.llm is None:
            return {"success": False, "message": "大语言模型未配置"}

        system_prompt = """你是一个电子表格操作专家。请分析用户的请求，提取创建多维表格所需的信息。

用户可能会说：
- "创建一个名为'客户管理'的多维表格"
- "帮我建一个项目追踪表，包含项目名称、负责人、截止日期、状态"
- "创建销售数据表，字段包括：产品名称、销量（数字）、销售日期、销售员"

请从用户输入中提取：
1. 表格名称（name）
2. 字段定义列表（fields），每个字段包含：
   - field_name: 字段名称
   - type: 字段类型数字（默认1=文本）
   - property: 字段属性（可选，如单选选项列表）

字段类型映射：
- 文本/多行文本: 1
- 数字: 2
- 单选: 3
- 多选: 4
- 日期: 5
- 复选框: 7
- 人员: 11
- 超链接: 15

输出格式：请只返回一个JSON对象，不要包含其他内容。
格式示例：
```json
{{
    "name": "客户管理",
    "fields": [
        {{"field_name": "客户名称", "type": 1}},
        {{"field_name": "联系电话", "type": 1}},
        {{"field_name": "合作状态", "type": 3, "property": {{"options": [{{"name": "已合作"}}, {{"name": "待联系"}}, {{"name": "已流失"}}]}}}}
    ]
}}
```

如果信息不足，返回：
```json
{{"error": "缺少必要信息，请提供表格名称"}}
```
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "用户输入：{user_input}\n\n请解析并返回JSON："),
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            result = await chain.ainvoke({"user_input": user_input})

            logger.debug(f"解析创建多维表格请求原始结果: {result}")

            parsed = safe_json_loads(result)

            if "error" in parsed:
                return {"success": False, "message": parsed["error"]}

            return {
                "success": True,
                "name": parsed.get("name"),
                "fields": parsed.get("fields", []),
            }

        except Exception as e:
            logger.error(f"解析创建多维表格请求失败: {str(e)}")
            return {"success": False, "message": f"解析请求时出错: {str(e)}"}

    async def _parse_write_request(self, user_input: str, conversation_history: List[BaseMessage]) -> Dict[str, Any]:
        """
        解析写入/更新数据的请求

        Args:
            user_input: 用户输入
            conversation_history: 对话历史

        Returns:
            解析结果，包含 fields 数据
        """
        if self.llm is None:
            return {"success": False, "message": "大语言模型未配置"}

        system_prompt = """你是一个电子表格操作专家。请分析用户的请求，提取要写入表格的数据。

用户可能会说：
- "在A表格中添加一条记录：姓名=张三，年龄=25，部门=技术部"
- "更新第1条记录，把状态改为已完成"
- "添加数据：产品=手机，价格=3999，库存=100"

请从用户输入中提取：
1. 要写入的字段数据（fields）
2. 操作类型："create"（新建）或 "update"（更新）
3. 如果是更新，提取 record_id 或索引

输出格式：请只返回一个JSON对象，不要包含其他内容。
格式示例：
```json
{{
    "action": "create",
    "fields": {{
        "姓名": "张三",
        "年龄": 25,
        "部门": "技术部"
    }}
}}
```

或更新操作：
```json
{{
    "action": "update",
    "record_id": "rec123",
    "fields": {{
        "状态": "已完成"
    }}
}}
```

如果信息不足，返回：
```json
{{"error": "缺少必要信息，请提供要写入的数据"}}
```
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "用户输入：{user_input}\n\n请解析并返回JSON："),
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            result = await chain.ainvoke({"user_input": user_input})

            logger.debug(f"解析写入请求原始结果: {result}")

            parsed = safe_json_loads(result)

            if "error" in parsed:
                return {"success": False, "message": parsed["error"]}

            return {"success": True, **parsed}

        except Exception as e:
            logger.error(f"解析写入请求失败: {str(e)}")
            return {"success": False, "message": f"解析请求时出错: {str(e)}"}

    async def _parse_batch_request(self, user_input: str, conversation_history: List[BaseMessage]) -> Dict[str, Any]:
        """
        解析批量操作的请求

        Args:
            user_input: 用户输入
            conversation_history: 对话历史

        Returns:
            解析结果，包含批量数据
        """
        if self.llm is None:
            return {"success": False, "message": "大语言模型未配置"}

        system_prompt = """你是一个电子表格操作专家。请分析用户的批量操作请求，提取要批量写入的数据。

用户可能会说：
- "批量添加3条记录：
  1. 姓名=李四，年龄=30，部门=市场部
  2. 姓名=王五，年龄=28，部门=技术部
  3. 姓名=赵六，年龄=32，部门=销售部"
- "批量更新：记录1的状态改为已完成，记录2的负责人改为张三"

请从用户输入中提取：
1. 操作类型："batch_create"（批量新建）或 "batch_update"（批量更新）
2. 记录列表

输出格式：请只返回一个JSON对象，不要包含其他内容。

批量新建格式示例：
```json
{{
    "action": "batch_create",
    "records": [
        {{"fields": {{"姓名": "李四", "年龄": 30, "部门": "市场部"}}}},
        {{"fields": {{"姓名": "王五", "年龄": 28, "部门": "技术部"}}}},
        {{"fields": {{"姓名": "赵六", "年龄": 32, "部门": "销售部"}}}}
    ]
}}
```

批量更新格式示例：
```json
{{
    "action": "batch_update",
    "records": [
        {{"record_id": "rec1", "fields": {{"状态": "已完成"}}}},
        {{"record_id": "rec2", "fields": {{"负责人": "张三"}}}}
    ]
}}
```

如果信息不足，返回：
```json
{{"error": "缺少必要信息，请提供要批量操作的数据"}}
```
"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "用户输入：{user_input}\n\n请解析并返回JSON："),
        ])

        chain = prompt | self.llm | StrOutputParser()

        try:
            result = await chain.ainvoke({"user_input": user_input})

            logger.debug(f"解析批量请求原始结果: {result}")

            parsed = safe_json_loads(result)

            if "error" in parsed:
                return {"success": False, "message": parsed["error"]}

            return {"success": True, **parsed}

        except Exception as e:
            logger.error(f"解析批量请求失败: {str(e)}")
            return {"success": False, "message": f"解析请求时出错: {str(e)}"}

    async def _create_bitable(self, name: str, fields: Optional[List[Dict[str, Any]]] = None) -> str:
        """
        创建多维表格

        Args:
            name: 表格名称
            fields: 字段定义列表

        Returns:
            执行结果
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法创建多维表格。"

        try:
            logger.info(f"创建多维表格: name={name}")

            result = await self.feishu_client.create_bitable(name=name)

            if not result.get("success"):
                return f"创建多维表格失败: {result.get('message', '未知错误')}"

            token = result.get("token")
            table_name = result.get("name")
            url = result.get("url")

            tables_result = await self.feishu_client.list_tables(token)
            existing_tables = tables_result.get("tables", []) if tables_result.get("success") else []

            logger.info(f"多维表格创建后有 {len(existing_tables)} 个默认数据表: {[t.get('name') for t in existing_tables]}")

            response = f"# 多维表格创建成功！🎉\n\n"
            response += f"**表格名称**：{table_name}\n"
            response += f"**表格Token**：{token}\n"
            if url:
                response += f"**访问链接**：{url}\n"

            if fields and len(fields) > 0:
                try:
                    target_table_name = "Sheet1"

                    table_to_use = None
                    for table in existing_tables:
                        if table.get("name") == target_table_name:
                            table_to_use = table
                            break

                    if table_to_use is None and len(existing_tables) > 0:
                        table_to_use = existing_tables[0]
                        logger.info(f"将使用第一个默认表 '{table_to_use.get('name')}' 作为目标表")

                    tables_to_delete = []
                    for table in existing_tables:
                        if table_to_use and table.get("table_id") != table_to_use.get("table_id"):
                            tables_to_delete.append(table)

                    for table in tables_to_delete:
                        delete_result = await self.feishu_client.delete_table(
                            app_token=token,
                            table_id=table.get("table_id"),
                        )
                        if delete_result.get("success"):
                            logger.info(f"已删除多余的数据表: {table.get('name')} (ID: {table.get('table_id')})")
                            response += f"\nℹ️ 已删除多余的默认数据表: {table.get('name')}"
                        else:
                            logger.warning(f"删除数据表失败: {table.get('name')}, 错误: {delete_result.get('message')}")

                    create_table_result = await self.feishu_client.create_table(
                        app_token=token,
                        table_name=target_table_name,
                        fields=fields,
                    )

                    if create_table_result.get("success"):
                        response += f"\n**数据表创建成功**：{target_table_name}\n"
                        field_names = ', '.join([field.get('field_name') for field in fields])
                        response += f"**字段**：{field_names}\n"

                        if table_to_use:
                            delete_old_result = await self.feishu_client.delete_table(
                                app_token=token,
                                table_id=table_to_use.get("table_id"),
                            )
                            if delete_old_result.get("success"):
                                logger.info(f"已删除旧的默认表: {table_to_use.get('name')}")
                            else:
                                logger.warning(f"删除旧表失败: {delete_old_result.get('message')}")
                    else:
                        response += f"\n⚠️ 数据表创建失败: {create_table_result.get('message', '未知错误')}\n"
                except Exception as e:
                    logger.error(f"创建数据表时出错: {str(e)}", exc_info=True)
                    response += f"\n⚠️ 创建数据表时出错: {str(e)}\n"
            else:
                if len(existing_tables) > 1:
                    table_to_keep = existing_tables[0]
                    tables_to_delete = existing_tables[1:]

                    for table in tables_to_delete:
                        delete_result = await self.feishu_client.delete_table(
                            app_token=token,
                            table_id=table.get("table_id"),
                        )
                        if delete_result.get("success"):
                            logger.info(f"已删除多余的数据表: {table.get('name')}")
                            response += f"\nℹ️ 已删除多余的数据表: {table.get('name')}"
                        else:
                            logger.warning(f"删除数据表失败: {table.get('name')}")

            return response

        except Exception as e:
            logger.error(f"创建多维表格失败: {str(e)}", exc_info=True)
            return f"创建多维表格时出错: {str(e)}"

    async def _read_records(self, app_token: str, table_id: str = "") -> str:
        """
        读取表格记录

        Args:
            app_token: 多维表格token
            table_id: 数据表ID（可选）

        Returns:
            记录列表
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法读取表格数据。"

        try:
            if not table_id:
                tables_result = await self.feishu_client.list_tables(app_token)
                if not tables_result.get("success"):
                    return f"获取数据表列表失败: {tables_result.get('message', '未知错误')}"

                tables = tables_result.get("tables", [])
                if len(tables) == 0:
                    return "该多维表格中没有数据表。"

                table_id = tables[0]["table_id"]
                table_name = tables[0]["name"]
            else:
                table_name = table_id

            logger.info(f"读取表格记录: app_token={app_token}, table_id={table_id}")

            records_result = await self.feishu_client.list_records(
                app_token=app_token,
                table_id=table_id,
                max_results=20,
            )

            if not records_result.get("success"):
                return f"读取记录失败: {records_result.get('message', '未知错误')}"

            records = records_result.get("records", [])
            has_more = records_result.get("has_more", False)

            if len(records) == 0:
                return f"数据表 '{table_name}' 中没有记录。"

            response = f"# 数据表：{table_name}\n\n"
            response += f"共 {len(records)} 条记录{', 还有更多...' if has_more else ''}\n\n"

            for i, record in enumerate(records[:10], 1):
                response += f"## 记录 {i} (ID: {record.get('record_id')})\n"
                fields = record.get("fields", {})
                for field_name, value in fields.items():
                    response += f"- **{field_name}**: {value}\n"
                response += "\n"

            if len(records) > 10:
                response += f"\n... 还有 {len(records) - 10} 条记录未显示\n"

            return response

        except Exception as e:
            logger.error(f"读取表格记录失败: {str(e)}", exc_info=True)
            return f"读取表格记录时出错: {str(e)}"

    async def _write_record(self, app_token: str, table_id: str, fields: Dict[str, Any]) -> str:
        """
        写入单条记录

        Args:
            app_token: 多维表格token
            table_id: 数据表ID
            fields: 字段数据

        Returns:
            执行结果
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法写入数据。"

        try:
            logger.info(f"写入记录: app_token={app_token}, table_id={table_id}")

            match_result = await self._match_field_names(app_token, table_id, fields)
            if not match_result.get("success"):
                return f"字段匹配失败: {match_result.get('message', '未知错误')}"

            matched_fields = match_result.get("fields", {})
            unmatched = match_result.get("unmatched", [])
            actual_fields = match_result.get("actual_fields", [])

            if not matched_fields:
                if actual_fields:
                    return f"没有匹配到任何字段。表格实际字段: {', '.join(actual_fields)}"
                else:
                    return "没有匹配到任何字段，且无法获取表格字段信息。"

            if unmatched:
                logger.warning(f"部分字段未匹配: {unmatched}，实际字段: {actual_fields}")

            result = await self.feishu_client.create_record(
                app_token=app_token,
                table_id=table_id,
                fields=matched_fields,
            )

            if not result.get("success"):
                error_msg = f"写入记录失败: {result.get('message', '未知错误')}"
                if unmatched:
                    error_msg += f"\n\n⚠️ 注意：以下字段未匹配（可能名称不一致）：{', '.join(unmatched)}"
                    error_msg += f"\n表格实际字段：{', '.join(actual_fields)}"
                return error_msg

            record_id = result.get("record_id")

            response = f"# 记录写入成功！✅\n\n"
            response += f"**记录ID**：{record_id}\n"
            response += f"**写入数据**：\n"
            for field_name, value in matched_fields.items():
                response += f"- {field_name}: {value}\n"

            if unmatched:
                response += f"\n⚠️ **注意**：以下字段未找到匹配，已忽略：\n"
                response += f"- 未匹配字段：{', '.join(unmatched)}\n"
                response += f"- 表格实际字段：{', '.join(actual_fields)}\n"

            return response

        except Exception as e:
            logger.error(f"写入记录失败: {str(e)}", exc_info=True)
            return f"写入记录时出错: {str(e)}"

    async def _update_record(self, app_token: str, table_id: str, record_id: str, fields: Dict[str, Any]) -> str:
        """
        更新单条记录

        Args:
            app_token: 多维表格token
            table_id: 数据表ID
            record_id: 记录ID
            fields: 字段数据

        Returns:
            执行结果
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法更新数据。"

        try:
            logger.info(f"更新记录: app_token={app_token}, table_id={table_id}, record_id={record_id}")

            match_result = await self._match_field_names(app_token, table_id, fields)
            if not match_result.get("success"):
                return f"字段匹配失败: {match_result.get('message', '未知错误')}"

            matched_fields = match_result.get("fields", {})
            unmatched = match_result.get("unmatched", [])
            actual_fields = match_result.get("actual_fields", [])

            if not matched_fields:
                if actual_fields:
                    return f"没有匹配到任何字段。表格实际字段: {', '.join(actual_fields)}"
                else:
                    return "没有匹配到任何字段，且无法获取表格字段信息。"

            if unmatched:
                logger.warning(f"部分字段未匹配: {unmatched}，实际字段: {actual_fields}")

            result = await self.feishu_client.update_record(
                app_token=app_token,
                table_id=table_id,
                record_id=record_id,
                fields=matched_fields,
            )

            if not result.get("success"):
                error_msg = f"更新记录失败: {result.get('message', '未知错误')}"
                if unmatched:
                    error_msg += f"\n\n⚠️ 注意：以下字段未匹配（可能名称不一致）：{', '.join(unmatched)}"
                    error_msg += f"\n表格实际字段：{', '.join(actual_fields)}"
                return error_msg

            response = f"# 记录更新成功！✅\n\n"
            response += f"**记录ID**：{record_id}\n"
            response += f"**更新数据**：\n"
            for field_name, value in matched_fields.items():
                response += f"- {field_name}: {value}\n"

            if unmatched:
                response += f"\n⚠️ **注意**：以下字段未找到匹配，已忽略：\n"
                response += f"- 未匹配字段：{', '.join(unmatched)}\n"
                response += f"- 表格实际字段：{', '.join(actual_fields)}\n"

            return response

        except Exception as e:
            logger.error(f"更新记录失败: {str(e)}", exc_info=True)
            return f"更新记录时出错: {str(e)}"

    async def _match_batch_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        对批量记录的字段进行匹配

        Args:
            app_token: 多维表格token
            table_id: 数据表ID
            records: 记录列表，每条记录格式为 {"fields": {...}}

        Returns:
            匹配后的记录数据
        """
        if self.feishu_client is None:
            return {"success": False, "message": "飞书客户端未配置", "records": []}

        fields_result = await self.feishu_client.list_fields(app_token, table_id)
        if not fields_result.get("success"):
            return {
                "success": False,
                "message": f"获取表格字段列表失败: {fields_result.get('message', '未知错误')}",
                "records": []
            }

        actual_fields = fields_result.get("fields", [])
        if not actual_fields:
            return {"success": False, "message": "表格中没有字段", "records": []}

        actual_field_map = {}
        for field in actual_fields:
            field_name = field.get("field_name", "")
            normalized = self._normalize_field_name(field_name)
            actual_field_map[normalized] = field_name

        matched_records = []
        all_unmatched = set()
        actual_field_names = [f.get("field_name", "") for f in actual_fields]

        for record in records:
            fields = record.get("fields", {})
            matched_fields = {}

            for input_name, value in fields.items():
                normalized_input = self._normalize_field_name(input_name)

                if normalized_input in actual_field_map:
                    actual_name = actual_field_map[normalized_input]
                    matched_fields[actual_name] = value
                else:
                    all_unmatched.add(input_name)

            if matched_fields:
                matched_records.append({"fields": matched_fields})

        result = {
            "success": True,
            "records": matched_records,
            "unmatched": list(all_unmatched),
            "actual_fields": actual_field_names
        }

        if all_unmatched:
            result["message"] = f"以下字段未找到匹配: {', '.join(all_unmatched)}。表格实际字段: {', '.join(actual_field_names)}"
        else:
            result["message"] = "所有字段匹配成功"

        logger.info(f"批量字段匹配结果: {len(matched_records)} 条记录匹配成功, {len(all_unmatched)} 个字段未匹配")

        return result

    async def _batch_create(self, app_token: str, table_id: str, records: List[Dict[str, Any]]) -> str:
        """
        批量创建记录

        Args:
            app_token: 多维表格token
            table_id: 数据表ID
            records: 记录列表

        Returns:
            执行结果
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法批量写入数据。"

        try:
            logger.info(f"批量创建记录: app_token={app_token}, table_id={table_id}, count={len(records)}")

            match_result = await self._match_batch_records(app_token, table_id, records)
            if not match_result.get("success"):
                return f"字段匹配失败: {match_result.get('message', '未知错误')}"

            matched_records = match_result.get("records", [])
            unmatched = match_result.get("unmatched", [])
            actual_fields = match_result.get("actual_fields", [])

            if not matched_records:
                if actual_fields:
                    return f"没有匹配到任何有效记录。表格实际字段: {', '.join(actual_fields)}"
                else:
                    return "没有匹配到任何有效记录，且无法获取表格字段信息。"

            if unmatched:
                logger.warning(f"部分字段未匹配: {unmatched}，实际字段: {actual_fields}")

            result = await self.feishu_client.batch_create_records(
                app_token=app_token,
                table_id=table_id,
                records=matched_records,
            )

            if not result.get("success"):
                error_msg = f"批量创建记录失败: {result.get('message', '未知错误')}"
                if unmatched:
                    error_msg += f"\n\n⚠️ 注意：以下字段未匹配（可能名称不一致）：{', '.join(unmatched)}"
                    error_msg += f"\n表格实际字段：{', '.join(actual_fields)}"
                return error_msg

            created_records = result.get("records", [])

            response = f"# 批量创建成功！✅\n\n"
            response += f"成功创建 {len(created_records)} 条记录\n\n"
            response += f"**记录ID列表**：\n"
            for i, record in enumerate(created_records, 1):
                response += f"{i}. {record.get('record_id')}\n"

            if unmatched:
                response += f"\n⚠️ **注意**：以下字段未找到匹配，已忽略：\n"
                response += f"- 未匹配字段：{', '.join(unmatched)}\n"
                response += f"- 表格实际字段：{', '.join(actual_fields)}\n"

            return response

        except Exception as e:
            logger.error(f"批量创建记录失败: {str(e)}", exc_info=True)
            return f"批量创建记录时出错: {str(e)}"

    async def _match_batch_update_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        对批量更新记录的字段进行匹配

        Args:
            app_token: 多维表格token
            table_id: 数据表ID
            records: 记录列表，每条记录格式为 {"record_id": "...", "fields": {...}}

        Returns:
            匹配后的记录数据
        """
        if self.feishu_client is None:
            return {"success": False, "message": "飞书客户端未配置", "records": []}

        fields_result = await self.feishu_client.list_fields(app_token, table_id)
        if not fields_result.get("success"):
            return {
                "success": False,
                "message": f"获取表格字段列表失败: {fields_result.get('message', '未知错误')}",
                "records": []
            }

        actual_fields = fields_result.get("fields", [])
        if not actual_fields:
            return {"success": False, "message": "表格中没有字段", "records": []}

        actual_field_map = {}
        for field in actual_fields:
            field_name = field.get("field_name", "")
            normalized = self._normalize_field_name(field_name)
            actual_field_map[normalized] = field_name

        matched_records = []
        all_unmatched = set()
        actual_field_names = [f.get("field_name", "") for f in actual_fields]

        for record in records:
            record_id = record.get("record_id", "")
            fields = record.get("fields", {})
            matched_fields = {}

            for input_name, value in fields.items():
                normalized_input = self._normalize_field_name(input_name)

                if normalized_input in actual_field_map:
                    actual_name = actual_field_map[normalized_input]
                    matched_fields[actual_name] = value
                else:
                    all_unmatched.add(input_name)

            if matched_fields and record_id:
                matched_records.append({
                    "record_id": record_id,
                    "fields": matched_fields
                })

        result = {
            "success": True,
            "records": matched_records,
            "unmatched": list(all_unmatched),
            "actual_fields": actual_field_names
        }

        if all_unmatched:
            result["message"] = f"以下字段未找到匹配: {', '.join(all_unmatched)}。表格实际字段: {', '.join(actual_field_names)}"
        else:
            result["message"] = "所有字段匹配成功"

        logger.info(f"批量更新字段匹配结果: {len(matched_records)} 条记录匹配成功, {len(all_unmatched)} 个字段未匹配")

        return result

    async def _batch_update(self, app_token: str, table_id: str, records: List[Dict[str, Any]]) -> str:
        """
        批量更新记录

        Args:
            app_token: 多维表格token
            table_id: 数据表ID
            records: 记录列表

        Returns:
            执行结果
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法批量更新数据。"

        try:
            logger.info(f"批量更新记录: app_token={app_token}, table_id={table_id}, count={len(records)}")

            match_result = await self._match_batch_update_records(app_token, table_id, records)
            if not match_result.get("success"):
                return f"字段匹配失败: {match_result.get('message', '未知错误')}"

            matched_records = match_result.get("records", [])
            unmatched = match_result.get("unmatched", [])
            actual_fields = match_result.get("actual_fields", [])

            if not matched_records:
                if actual_fields:
                    return f"没有匹配到任何有效记录。表格实际字段: {', '.join(actual_fields)}"
                else:
                    return "没有匹配到任何有效记录，且无法获取表格字段信息。"

            if unmatched:
                logger.warning(f"部分字段未匹配: {unmatched}，实际字段: {actual_fields}")

            result = await self.feishu_client.batch_update_records(
                app_token=app_token,
                table_id=table_id,
                records=matched_records,
            )

            if not result.get("success"):
                error_msg = f"批量更新记录失败: {result.get('message', '未知错误')}"
                if unmatched:
                    error_msg += f"\n\n⚠️ 注意：以下字段未匹配（可能名称不一致）：{', '.join(unmatched)}"
                    error_msg += f"\n表格实际字段：{', '.join(actual_fields)}"
                return error_msg

            updated_records = result.get("records", [])

            response = f"# 批量更新成功！✅\n\n"
            response += f"成功更新 {len(updated_records)} 条记录\n\n"
            response += f"**更新的记录ID**：\n"
            for i, record in enumerate(updated_records, 1):
                response += f"{i}. {record.get('record_id')}\n"

            if unmatched:
                response += f"\n⚠️ **注意**：以下字段未找到匹配，已忽略：\n"
                response += f"- 未匹配字段：{', '.join(unmatched)}\n"
                response += f"- 表格实际字段：{', '.join(actual_fields)}\n"

            return response

        except Exception as e:
            logger.error(f"批量更新记录失败: {str(e)}", exc_info=True)
            return f"批量更新记录时出错: {str(e)}"

    async def _get_table_info(self, app_token: str) -> str:
        """
        获取表格信息

        Args:
            app_token: 多维表格token

        Returns:
            表格信息
        """
        if self.feishu_client is None:
            return "抱歉，飞书客户端未配置，无法获取表格信息。"

        try:
            logger.info(f"获取表格信息: app_token={app_token}")

            bitable_result = await self.feishu_client.get_bitable_info(app_token)
            if not bitable_result.get("success"):
                return f"获取多维表格信息失败: {bitable_result.get('message', '未知错误')}"

            tables_result = await self.feishu_client.list_tables(app_token)
            tables = tables_result.get("tables", []) if tables_result.get("success") else []

            response = f"# 多维表格信息\n\n"
            response += f"**表格名称**：{bitable_result.get('name')}\n"
            response += f"**表格Token**：{bitable_result.get('token')}\n"
            if bitable_result.get('url'):
                response += f"**访问链接**：{bitable_result.get('url')}\n"
            response += f"\n---\n\n"
            response += f"**数据表列表**（共 {len(tables)} 个）：\n\n"

            for i, table in enumerate(tables, 1):
                response += f"## {i}. {table.get('name')}\n"
                response += f"- 数据表ID: {table.get('table_id')}\n"

                fields_result = await self.feishu_client.list_fields(app_token, table.get("table_id"))
                if fields_result.get("success"):
                    fields = fields_result.get("fields", [])
                    response += f"- 字段数量: {len(fields)}\n"
                    if fields:
                        response += f"- 字段列表:\n"
                        for field in fields:
                            field_type_name = "未知"
                            for name, code in self.FIELD_TYPE_MAP.items():
                                if code == field.get("type"):
                                    field_type_name = name
                                    break
                            response += f"  - {field.get('field_name')} ({field_type_name})"
                            if field.get("is_primary"):
                                response += " [主键]"
                            response += "\n"
                response += "\n"

            return response

        except Exception as e:
            logger.error(f"获取表格信息失败: {str(e)}", exc_info=True)
            return f"获取表格信息时出错: {str(e)}"

    async def execute(
        self,
        user_input: str,
        conversation_history: List[BaseMessage],
        **kwargs: Any
    ) -> str:
        """
        执行电子表格管理功能

        Args:
            user_input: 用户输入
            conversation_history: 对话历史
            **kwargs: 其他参数

        Returns:
            执行结果字符串
        """
        logger.info(f"电子表格模块处理用户输入: {user_input}")

        msg_lower = user_input.lower()

        if "创建" in msg_lower or "新建" in msg_lower or "建立" in msg_lower:
            if "表格" in msg_lower or "多维表格" in msg_lower:
                if "数据表" in msg_lower:
                    return "我理解您想创建数据表，但需要知道具体的多维表格Token。请提供多维表格的链接或Token，我来帮您创建数据表。"
                else:
                    parse_result = await self._parse_create_bitable_request(user_input, conversation_history)
                    if not parse_result.get("success"):
                        return f"解析请求时遇到问题：{parse_result.get('message')}。请告诉我您想创建的表格名称和字段。"

                    return await self._create_bitable(
                        name=parse_result.get("name"),
                        fields=parse_result.get("fields"),
                    )

        app_token = self._extract_bitable_token(user_input)

        if not app_token:
            return "我理解您想操作电子表格，但需要知道具体的多维表格。请提供多维表格的链接或Token，我来帮您处理。"

        if "读取" in msg_lower or "查看" in msg_lower or "查询" in msg_lower or "显示" in msg_lower or "列表" in msg_lower:
            if "信息" in msg_lower or "结构" in msg_lower or "字段" in msg_lower:
                return await self._get_table_info(app_token)
            else:
                table_id = await self._get_target_table_id(app_token, user_input)
                return await self._read_records(app_token, table_id)

        if "写入" in msg_lower or "添加" in msg_lower or "新增" in msg_lower or "插入" in msg_lower:
            if "批量" in msg_lower:
                parse_result = await self._parse_batch_request(user_input, conversation_history)
                if not parse_result.get("success"):
                    return f"解析请求时遇到问题：{parse_result.get('message')}。请提供要批量添加的数据。"

                table_id = await self._get_target_table_id(app_token, user_input)
                if not table_id:
                    return "请提供数据表ID或表名，格式：数据表ID: xxx 或 表名: xxx"

                return await self._batch_create(app_token, table_id, parse_result.get("records", []))
            else:
                parse_result = await self._parse_write_request(user_input, conversation_history)
                if not parse_result.get("success"):
                    return f"解析请求时遇到问题：{parse_result.get('message')}。请提供要添加的数据。"

                table_id = await self._get_target_table_id(app_token, user_input)
                if not table_id:
                    return "请提供数据表ID或表名，格式：数据表ID: xxx 或 表名: xxx"

                return await self._write_record(app_token, table_id, parse_result.get("fields", {}))

        if "更新" in msg_lower or "修改" in msg_lower or "编辑" in msg_lower:
            if "批量" in msg_lower:
                parse_result = await self._parse_batch_request(user_input, conversation_history)
                if not parse_result.get("success"):
                    return f"解析请求时遇到问题：{parse_result.get('message')}。请提供要批量更新的数据。"

                table_id = await self._get_target_table_id(app_token, user_input)
                if not table_id:
                    return "请提供数据表ID或表名，格式：数据表ID: xxx 或 表名: xxx"

                return await self._batch_update(app_token, table_id, parse_result.get("records", []))
            else:
                parse_result = await self._parse_write_request(user_input, conversation_history)
                if not parse_result.get("success"):
                    return f"解析请求时遇到问题：{parse_result.get('message')}。请提供要更新的数据和记录ID。"

                table_id = await self._get_target_table_id(app_token, user_input)
                if not table_id:
                    return "请提供数据表ID或表名，格式：数据表ID: xxx 或 表名: xxx"

                record_id = parse_result.get("record_id")
                if not record_id:
                    return "更新记录需要指定记录ID。请提供记录ID，格式：记录ID: xxx"

                return await self._update_record(app_token, table_id, record_id, parse_result.get("fields", {}))

        if "信息" in msg_lower or "结构" in msg_lower:
            return await self._get_table_info(app_token)

        return "我理解您想操作电子表格。您可以告诉我：\n\n" \
               "1. **创建表格**：\"创建一个名为'客户管理'的多维表格，包含姓名、电话、状态字段\"\n" \
               "2. **读取数据**：\"读取表格xxx的数据\"\n" \
               "3. **写入数据**：\"在表格xxx中添加一条记录：姓名=张三\"\n" \
               "4. **更新数据**：\"更新表格xxx中记录rec1的状态为已完成\"\n" \
               "5. **批量操作**：\"批量添加3条记录...\""
