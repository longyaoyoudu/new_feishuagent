from typing import Optional, Dict, Any, List
import httpx
import json

from config import settings
from utils.logger import logger
from utils.exceptions import ConfigurationError, FeishuAPIError, AuthorizationError


class FeishuClient:
    """飞书客户端封装类"""

    _instance: Optional["FeishuClient"] = None
    _access_token: Optional[str] = None
    _token_expire_time: float = 0

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not settings.FEISHU_APP_ID or not settings.FEISHU_APP_SECRET:
            raise ConfigurationError(
                "飞书应用配置缺失，请检查 FEISHU_APP_ID 和 FEISHU_APP_SECRET 配置"
            )

        self.app_id = settings.FEISHU_APP_ID
        self.app_secret = settings.FEISHU_APP_SECRET
        logger.info("飞书客户端初始化成功")

    async def _get_access_token(self) -> str:
        """获取访问令牌"""
        import time

        if self._access_token and time.time() < self._token_expire_time - 60:
            return self._access_token

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
                    json={
                        "app_id": self.app_id,
                        "app_secret": self.app_secret,
                    },
                    headers={"Content-Type": "application/json"},
                )

                data = response.json()

                if data.get("code") != 0:
                    logger.error(f"获取访问令牌失败: {data}")
                    raise AuthorizationError(f"获取访问令牌失败: {data.get('msg', '未知错误')}")

                self._access_token = data.get("tenant_access_token")
                expires_in = data.get("expire", 7200)
                self._token_expire_time = time.time() + expires_in

                logger.info("访问令牌获取成功")
                return self._access_token

        except Exception as e:
            logger.error(f"获取访问令牌异常: {str(e)}")
            raise AuthorizationError(f"获取访问令牌失败: {str(e)}")

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        need_auth: bool = True,
    ) -> Dict[str, Any]:
        """
        发送HTTP请求到飞书API

        Args:
            method: HTTP方法 (GET, POST, PUT, DELETE等)
            endpoint: API端点
            params: 查询参数
            data: 请求体数据
            need_auth: 是否需要认证

        Returns:
            API响应数据
        """
        headers = {"Content-Type": "application/json"}

        if need_auth:
            access_token = await self._get_access_token()
            headers["Authorization"] = f"Bearer {access_token}"

        url = f"{self.BASE_URL}{endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                if method.upper() == "GET":
                    response = await client.get(url, params=params, headers=headers)
                elif method.upper() == "POST":
                    response = await client.post(url, params=params, json=data, headers=headers)
                elif method.upper() == "PUT":
                    response = await client.put(url, params=params, json=data, headers=headers)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, params=params, headers=headers)
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")

                result = response.json()

                if result.get("code") != 0:
                    logger.error(f"API请求失败: {result}")
                    raise FeishuAPIError(
                        f"API请求失败: {result.get('msg', '未知错误')}",
                        code=result.get("code", -1),
                    )

                return result

        except FeishuAPIError:
            raise
        except Exception as e:
            logger.error(f"API请求异常: {str(e)}")
            raise FeishuAPIError(f"API请求异常: {str(e)}")

    async def get_calendar_events(
        self,
        calendar_id: str = "primary",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        max_results: int = 10,
    ) -> Dict[str, Any]:
        """
        获取日历事件

        Args:
            calendar_id: 日历ID，默认为 primary
            start_time: 开始时间
            end_time: 结束时间
            max_results: 最大结果数量

        Returns:
            日历事件列表
        """
        try:
            logger.info(f"获取日历事件: calendar_id={calendar_id}")

            params = {"max_results": max_results}
            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time

            result = await self._make_request(
                method="GET",
                endpoint=f"/calendar/v4/calendars/{calendar_id}/events",
                params=params,
            )

            events = []
            items = result.get("data", {}).get("items", [])

            for item in items:
                events.append({
                    "event_id": item.get("event_id"),
                    "summary": item.get("summary"),
                    "description": item.get("description"),
                    "start_time": item.get("start_time"),
                    "end_time": item.get("end_time"),
                    "location": item.get("location"),
                    "status": item.get("status"),
                })

            logger.info(f"成功获取 {len(events)} 个日历事件")
            return {"success": True, "events": events}

        except Exception as e:
            logger.error(f"获取日历事件异常: {str(e)}")
            raise FeishuAPIError(f"获取日历事件失败: {str(e)}")

    async def create_calendar_event(
        self,
        summary: str,
        description: str = "",
        start_time: str = "",
        end_time: str = "",
        start_date: str = "",
        end_date: str = "",
        timezone: str = "Asia/Shanghai",
        location: str = "",
        attendees: Optional[List[Dict[str, Any]]] = None,
        reminders: Optional[List[Dict[str, Any]]] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        创建日历事件

        Args:
            summary: 事件标题（必填）
            description: 事件描述
            start_time: 开始时间戳（Unix时间戳，秒级），与 start_date 二选一
            end_time: 结束时间戳（Unix时间戳，秒级），与 end_date 二选一
            start_date: 全天日程开始日期（格式：YYYY-MM-DD），与 start_time 二选一
            end_date: 全天日程结束日期（格式：YYYY-MM-DD），与 end_time 二选一
            timezone: 时区，默认 Asia/Shanghai
            location: 地点
            attendees: 参与者列表，每个参与者包含：
                - open_id: 用户open_id
                - email: 邮箱（可选）
            reminders: 提醒列表，每个提醒包含：
                - minutes: 提前多少分钟提醒
            calendar_id: 日历ID，默认 primary

        Returns:
            创建结果
        """
        try:
            logger.info(f"创建日历事件: summary={summary}")

            event_data: Dict[str, Any] = {
                "summary": summary,
            }

            if description:
                event_data["description"] = description
            
            if location:
                event_data["location"] = location

            if start_date and end_date:
                event_data["start_time"] = {
                    "date": start_date,
                    "timezone": timezone
                }
                event_data["end_time"] = {
                    "date": end_date,
                    "timezone": timezone
                }
            elif start_time and end_time:
                event_data["start_time"] = {
                    "timestamp": start_time,
                    "timezone": timezone
                }
                event_data["end_time"] = {
                    "timestamp": end_time,
                    "timezone": timezone
                }
            else:
                raise ValueError("必须提供 start_time/end_time 或 start_date/end_date")

            if attendees:
                event_data["attendees"] = []
                for attendee in attendees:
                    attendee_data = {}
                    if attendee.get("open_id"):
                        attendee_data["open_id"] = attendee["open_id"]
                    if attendee.get("email"):
                        attendee_data["email"] = attendee["email"]
                    if attendee_data:
                        event_data["attendees"].append(attendee_data)

            if reminders:
                event_data["reminders"] = reminders

            logger.debug(f"创建日程请求数据: {event_data}")

            result = await self._make_request(
                method="POST",
                endpoint=f"/calendar/v4/calendars/{calendar_id}/events",
                data=event_data,
            )

            event = result.get("data", {}).get("event", {})

            logger.info(f"日历事件创建成功: event_id={event.get('event_id')}")
            return {
                "success": True,
                "event_id": event.get("event_id"),
                "summary": event.get("summary"),
                "start_time": event.get("start_time"),
                "end_time": event.get("end_time"),
            }

        except FeishuAPIError:
            raise
        except Exception as e:
            logger.error(f"创建日历事件异常: {str(e)}")
            raise FeishuAPIError(f"创建日历事件失败: {str(e)}")

    async def get_document_content(
        self,
        document_token: str,
    ) -> Dict[str, Any]:
        """
        获取云文档内容

        Args:
            document_token: 文档token

        Returns:
            文档内容
        """
        try:
            logger.info(f"开始获取云文档内容: document_token={document_token}")

            # 首先获取文档基本信息（元数据）
            logger.info(f"步骤1: 获取文档元数据")
            try:
                meta_result = await self._make_request(
                    method="GET",
                    endpoint=f"/docx/v1/documents/{document_token}",
                )
                logger.debug(f"文档元数据获取成功: {meta_result}")
            except FeishuAPIError as e:
                error_msg = self._parse_document_error(e.code, e.message)
                logger.error(f"获取文档元数据失败: code={e.code}, message={e.message}, parsed={error_msg}")
                return {
                    "success": False,
                    "message": error_msg,
                    "error_code": e.code
                }

            document = meta_result.get("data", {}).get("document", {})
            title = document.get("title", "无标题")
            document_id = document.get("document_id", document_token)

            logger.info(f"获取到文档元数据: title={title}, document_id={document_id}, revision_id={document.get('revision_id')}")

            # 然后获取文档纯文本内容
            logger.info(f"步骤2: 获取文档纯文本内容")
            try:
                content_result = await self._make_request(
                    method="GET",
                    endpoint=f"/docx/v1/documents/{document_token}/raw_content",
                )
                logger.debug(f"文档内容获取成功，原始响应: {content_result}")
            except FeishuAPIError as e:
                error_msg = self._parse_document_error(e.code, e.message)
                logger.error(f"获取文档内容失败: code={e.code}, message={e.message}, parsed={error_msg}")
                return {
                    "success": False,
                    "message": error_msg,
                    "error_code": e.code
                }

            content = content_result.get("data", {}).get("content", "")

            if not content:
                logger.warning(f"文档内容为空: title={title}")

            logger.info(f"成功获取云文档内容: title={title}, content_length={len(content)}")

            result = {
                "document_id": document_id,
                "title": title,
                "revision_id": document.get("revision_id"),
                "content": content,
            }

            return {"success": True, "document": result}

        except Exception as e:
            logger.error(f"获取云文档发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取云文档时发生未知错误: {str(e)}",
                "error_code": -1
            }

    def _parse_document_error(self, code: int, default_message: str) -> str:
        """
        解析文档相关的错误码，返回友好的错误信息

        Args:
            code: 错误码
            default_message: 默认错误信息

        Returns:
            友好的错误信息
        """
        error_messages = {
            1770001: "参数不合法，请检查文档token是否正确",
            1770002: "文档不存在，请确认文档ID是否正确，或文档已被删除",
            1770003: "资源已被删除",
            1770004: "文档块数量超过上限",
            1770005: "文档层级超过上限",
            1770006: "文档结构不合法",
            1770007: "文档块的子节点数量超过上限",
            1770008: "文件大小超过上限",
            1770010: "表格列数超过上限",
            1770011: "表格单元格数量超过上限",
            1770012: "Grid列数量超过上限",
            1770013: "图片、文件等资源的关联关系不正确",
            1770014: "文档块父子关系不正确",
            1770015: "单编辑操作涉及多个文档",
            1770019: "文档中存在重复的BlockID",
            1770020: "文档正在创建副本中，请稍后再试",
            1770021: "文档版本过旧",
            1770022: "分页token不合法",
            1770024: "操作不合法",
            1770025: "操作与文档块不匹配",
            1770026: "行操作下标越界",
            1770027: "列操作下标越界",
            1770028: "该文档块不支持创建子节点",
            1770029: "该文档块不支持创建",
            1770030: "父子关系不合法",
            1770031: "该文档块不支持删除子节点",
            1770032: "权限不足，无法访问文档。请确保：1) 应用已在开放平台配置云文档权限；2) 文档已通过右上角「...」->「更多」->「添加文档应用」授权给应用",
            1770033: "纯文本内容大小超过限制",
            1770034: "请求中涉及单元格个数过多，请拆分成多次请求",
            1771001: "服务器内部错误，请稍后重试",
            1771002: "网关服务内部错误，请稍后重试",
            1771003: "网关服务解析错误",
            1771004: "网关服务反解析错误",
            1771005: "系统服务正在维护中，请稍后重试",
            1771006: "挂载文档到云空间文件夹失败",
            99991400: "请求过于频繁，请稍后重试",
            99991663: "Token无效，请检查应用凭证配置",
        }

        if code in error_messages:
            return error_messages[code]
        else:
            return default_message

    async def get_wiki_node_info(
        self,
        token: str,
        obj_type: str = "wiki",
    ) -> Dict[str, Any]:
        """
        获取知识库节点信息，用于将知识库节点token转换为实际的云文档token

        Args:
            token: 知识库节点token或云文档token
            obj_type: 文档类型，默认是wiki
                - wiki: 知识库节点
                - doc: 旧版文档
                - docx: 新版文档
                - sheet: 表格
                - mindnote: 思维导图
                - bitable: 多维表格

        Returns:
            节点信息，包含实际的文档token
        """
        try:
            logger.info(f"获取知识库节点信息: token={token}, obj_type={obj_type}")

            params = {"token": token}
            if obj_type and obj_type != "wiki":
                params["obj_type"] = obj_type

            result = await self._make_request(
                method="GET",
                endpoint="/wiki/v2/spaces/get_node",
                params=params,
            )

            node = result.get("data", {}).get("node", {})

            logger.info(f"成功获取知识库节点信息: node={node}")

            return {
                "success": True,
                "node": {
                    "node_token": node.get("node_token"),
                    "obj_type": node.get("obj_type"),
                    "obj_token": node.get("obj_token"),
                    "parent_node_token": node.get("parent_node_token"),
                    "title": node.get("title"),
                    "space_id": node.get("space_id"),
                }
            }

        except FeishuAPIError as e:
            error_msg = self._parse_wiki_error(e.code, e.message)
            logger.error(f"获取知识库节点信息失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"获取知识库节点信息发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取知识库节点信息时发生未知错误: {str(e)}",
                "error_code": -1
            }

    def _parse_wiki_error(self, code: int, default_message: str) -> str:
        """
        解析知识库相关的错误码，返回友好的错误信息

        Args:
            code: 错误码
            default_message: 默认错误信息

        Returns:
            友好的错误信息
        """
        error_messages = {
            131001: "服务报错，请稍后重试",
            131002: "参数有误，例如数据类型不匹配",
            131004: "非法用户",
            131005: "未找到相关数据，可能是知识空间不存在、节点不存在或文档不存在",
            131006: "权限拒绝。请确保：1) 应用已在开放平台配置知识库权限；2) 应用已被添加为知识空间成员或管理员；3) 文档已授权给应用访问",
            131007: "服务内部错误，请稍后重试",
        }

        if code in error_messages:
            return error_messages[code]
        else:
            return default_message

    async def send_message(
        self,
        receive_id: str,
        msg_type: str = "text",
        content: str = "",
        receive_id_type: str = "open_id",
    ) -> Dict[str, Any]:
        """
        发送消息

        Args:
            receive_id: 接收者ID
            msg_type: 消息类型
            content: 消息内容
            receive_id_type: 接收者ID类型

        Returns:
            发送结果
        """
        try:
            logger.info(f"发送消息: receive_id={receive_id}, msg_type={msg_type}")

            params = {"receive_id_type": receive_id_type}

            data = {
                "receive_id": receive_id,
                "msg_type": msg_type,
                "content": content,
            }

            result = await self._make_request(
                method="POST",
                endpoint="/im/v1/messages",
                params=params,
                data=data,
            )

            message_id = result.get("data", {}).get("message_id")

            logger.info(f"消息发送成功: message_id={message_id}")
            return {
                "success": True,
                "message_id": message_id,
            }

        except Exception as e:
            logger.error(f"发送消息异常: {str(e)}")
            raise FeishuAPIError(f"发送消息失败: {str(e)}")

    async def get_chat_history(
        self,
        chat_id: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        max_results: int = 50,
    ) -> Dict[str, Any]:
        """
        获取群聊历史消息

        Args:
            chat_id: 群聊ID
            start_time: 开始时间戳（秒级，可选）
            end_time: 结束时间戳（秒级，可选）
            max_results: 最大获取消息数量，默认50

        Returns:
            历史消息列表
        """
        try:
            logger.info(f"获取群聊历史消息: chat_id={chat_id}")

            params: Dict[str, Any] = {
                "container_id_type": "chat",
                "container_id": chat_id,
                "page_size": min(max_results, 50),
            }

            if start_time:
                params["start_time"] = start_time
            if end_time:
                params["end_time"] = end_time

            result = await self._make_request(
                method="GET",
                endpoint="/im/v1/messages",
                params=params,
            )

            items = result.get("data", {}).get("items", [])
            has_more = result.get("data", {}).get("has_more", False)
            page_token = result.get("data", {}).get("page_token")

            messages = []
            for item in items:
                body = item.get("body", {})
                content = body.get("content") if body else None
                
                message = {
                    "message_id": item.get("message_id"),
                    "chat_id": item.get("chat_id"),
                    "msg_type": item.get("msg_type"),
                    "content": content,
                    "create_time": item.get("create_time"),
                    "update_time": item.get("update_time"),
                    "sender": item.get("sender", {}),
                }
                messages.append(message)

            logger.info(f"成功获取 {len(messages)} 条历史消息")
            return {
                "success": True,
                "messages": messages,
                "has_more": has_more,
                "page_token": page_token,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_chat_history_error(e.code, e.message)
            logger.error(f"获取群聊历史消息失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"获取群聊历史消息发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取群聊历史消息时发生未知错误: {str(e)}",
                "error_code": -1
            }

    def _parse_chat_history_error(self, code: int, default_message: str) -> str:
        """
        解析群聊历史消息相关的错误码，返回友好的错误信息

        Args:
            code: 错误码
            default_message: 默认错误信息

        Returns:
            友好的错误信息
        """
        error_messages = {
            99991663: "Token无效，请检查应用凭证配置",
            99991668: "权限不足，无法获取群聊历史消息。请确保：1) 应用已在开放平台配置获取群聊历史消息的权限；2) 机器人已被添加到群聊中",
            99991664: "参数不合法，请检查chat_id是否正确",
        }

        if code in error_messages:
            return error_messages[code]
        else:
            return default_message


    async def create_bitable(
        self,
        name: str,
        folder_token: str = "",
    ) -> Dict[str, Any]:
        """
        创建多维表格

        Args:
            name: 表格名称
            folder_token: 文件夹token（可选，不传则创建在根目录）

        Returns:
            创建结果，包含表格token
        """
        try:
            logger.info(f"创建多维表格: name={name}")

            data: Dict[str, Any] = {
                "name": name,
            }
            if folder_token:
                data["folder_token"] = folder_token

            result = await self._make_request(
                method="POST",
                endpoint="/bitable/v1/apps",
                data=data,
            )

            app = result.get("data", {}).get("app", {})

            logger.info(f"多维表格创建成功: token={app.get('app_token')}")
            return {
                "success": True,
                "token": app.get("app_token"),
                "name": app.get("name"),
                "url": app.get("url"),
            }

        except FeishuAPIError:
            raise
        except Exception as e:
            logger.error(f"创建多维表格异常: {str(e)}")
            raise FeishuAPIError(f"创建多维表格失败: {str(e)}")

    async def get_bitable_info(
        self,
        app_token: str,
    ) -> Dict[str, Any]:
        """
        获取多维表格信息

        Args:
            app_token: 多维表格的token

        Returns:
            表格信息
        """
        try:
            logger.info(f"获取多维表格信息: app_token={app_token}")

            result = await self._make_request(
                method="GET",
                endpoint=f"/bitable/v1/apps/{app_token}",
            )

            app = result.get("data", {}).get("app", {})

            logger.info(f"成功获取多维表格信息: name={app.get('name')}")
            return {
                "success": True,
                "token": app.get("app_token"),
                "name": app.get("name"),
                "url": app.get("url"),
                "is_advanced": app.get("is_advanced"),
                "time_zone": app.get("time_zone"),
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"获取多维表格信息失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"获取多维表格信息发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取多维表格信息时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def list_tables(
        self,
        app_token: str,
    ) -> Dict[str, Any]:
        """
        获取多维表格的数据表列表

        Args:
            app_token: 多维表格的token

        Returns:
            数据表列表
        """
        try:
            logger.info(f"获取数据表列表: app_token={app_token}")

            result = await self._make_request(
                method="GET",
                endpoint=f"/bitable/v1/apps/{app_token}/tables",
            )

            tables = result.get("data", {}).get("items", [])

            table_list = []
            for table in tables:
                table_list.append({
                    "table_id": table.get("table_id"),
                    "name": table.get("name"),
                    "revision": table.get("revision"),
                })

            logger.info(f"成功获取 {len(table_list)} 个数据表")
            return {
                "success": True,
                "tables": table_list,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"获取数据表列表失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"获取数据表列表发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取数据表列表时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def create_table(
        self,
        app_token: str,
        table_name: str,
        fields: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        在多维表格中创建新的数据表

        Args:
            app_token: 多维表格的token
            table_name: 数据表名称
            fields: 字段定义列表，每个字段包含：
                - field_name: 字段名称
                - type: 字段类型 (1:多行文本, 2:数字, 3:单选, 4:多选, 5:日期, 7:复选框, 11:人员, 15:超链接, 20:创建人, 21:创建时间, 22:修改人, 23:修改时间, 1001:自动编号)
                - property: 字段属性（可选，不同类型有不同属性）

        Returns:
            创建结果
        """
        try:
            logger.info(f"创建数据表: app_token={app_token}, table_name={table_name}")

            data: Dict[str, Any] = {
                "table": {
                    "name": table_name,
                }
            }

            if fields:
                data["table"]["fields"] = fields

            result = await self._make_request(
                method="POST",
                endpoint=f"/bitable/v1/apps/{app_token}/tables",
                data=data,
            )

            table = result.get("data", {}).get("table", {})

            logger.info(f"数据表创建成功: table_id={table.get('table_id')}")
            return {
                "success": True,
                "table_id": table.get("table_id"),
                "name": table.get("name"),
                "revision": table.get("revision"),
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"创建数据表失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"创建数据表发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"创建数据表时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def list_records(
        self,
        app_token: str,
        table_id: str,
        view_id: str = "",
        filter: str = "",
        sort: str = "",
        field_names: Optional[List[str]] = None,
        max_results: int = 100,
    ) -> Dict[str, Any]:
        """
        获取数据表中的记录列表

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID
            view_id: 视图ID（可选）
            filter: 过滤公式（可选）
            sort: 排序方式（可选）
            field_names: 指定返回的字段名列表（可选）
            max_results: 最大返回数量

        Returns:
            记录列表
        """
        try:
            logger.info(f"获取记录列表: app_token={app_token}, table_id={table_id}")

            params: Dict[str, Any] = {
                "page_size": min(max_results, 100),
            }

            if view_id:
                params["view_id"] = view_id
            if filter:
                params["filter"] = filter
            if sort:
                params["sort"] = sort
            if field_names:
                for i, field_name in enumerate(field_names):
                    params[f"field_names[{i}]"] = field_name

            result = await self._make_request(
                method="GET",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                params=params,
            )

            items = result.get("data", {}).get("items", [])
            has_more = result.get("data", {}).get("has_more", False)
            page_token = result.get("data", {}).get("page_token")

            records = []
            for item in items:
                records.append({
                    "record_id": item.get("record_id"),
                    "fields": item.get("fields", {}),
                    "created_time": item.get("created_time"),
                    "updated_time": item.get("updated_time"),
                })

            logger.info(f"成功获取 {len(records)} 条记录")
            return {
                "success": True,
                "records": records,
                "has_more": has_more,
                "page_token": page_token,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"获取记录列表失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"获取记录列表发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取记录列表时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def get_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
    ) -> Dict[str, Any]:
        """
        获取单条记录

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID
            record_id: 记录ID

        Returns:
            记录详情
        """
        try:
            logger.info(f"获取记录: app_token={app_token}, table_id={table_id}, record_id={record_id}")

            result = await self._make_request(
                method="GET",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            )

            record = result.get("data", {})

            logger.info(f"成功获取记录: record_id={record.get('record_id')}")
            return {
                "success": True,
                "record_id": record.get("record_id"),
                "fields": record.get("fields", {}),
                "created_time": record.get("created_time"),
                "updated_time": record.get("updated_time"),
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"获取记录失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"获取记录发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取记录时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def create_record(
        self,
        app_token: str,
        table_id: str,
        fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        创建单条记录

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID
            fields: 字段数据字典，格式为 {"字段名": 值, ...}

        Returns:
            创建结果
        """
        try:
            logger.info(f"创建记录: app_token={app_token}, table_id={table_id}")

            data = {
                "fields": fields,
            }

            result = await self._make_request(
                method="POST",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/records",
                data=data,
            )

            record = result.get("data", {})

            logger.info(f"记录创建成功: record_id={record.get('record_id')}")
            return {
                "success": True,
                "record_id": record.get("record_id"),
                "fields": record.get("fields", {}),
                "created_time": record.get("created_time"),
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"创建记录失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"创建记录发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"创建记录时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def batch_create_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        批量创建记录

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID
            records: 记录列表，每条记录为 {"fields": {"字段名": 值, ...}}

        Returns:
            创建结果
        """
        try:
            logger.info(f"批量创建记录: app_token={app_token}, table_id={table_id}, count={len(records)}")

            data = {
                "records": records,
            }

            result = await self._make_request(
                method="POST",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
                data=data,
            )

            created_records = result.get("data", {}).get("records", [])

            record_list = []
            for record in created_records:
                record_list.append({
                    "record_id": record.get("record_id"),
                    "fields": record.get("fields", {}),
                    "created_time": record.get("created_time"),
                })

            logger.info(f"成功批量创建 {len(record_list)} 条记录")
            return {
                "success": True,
                "records": record_list,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"批量创建记录失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"批量创建记录发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"批量创建记录时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def update_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
        fields: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        更新单条记录

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID
            record_id: 记录ID
            fields: 需要更新的字段数据

        Returns:
            更新结果
        """
        try:
            logger.info(f"更新记录: app_token={app_token}, table_id={table_id}, record_id={record_id}")

            data = {
                "fields": fields,
            }

            result = await self._make_request(
                method="PUT",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
                data=data,
            )

            record = result.get("data", {})

            logger.info(f"记录更新成功: record_id={record.get('record_id')}")
            return {
                "success": True,
                "record_id": record.get("record_id"),
                "fields": record.get("fields", {}),
                "updated_time": record.get("updated_time"),
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"更新记录失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"更新记录发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"更新记录时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def batch_update_records(
        self,
        app_token: str,
        table_id: str,
        records: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        批量更新记录

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID
            records: 记录列表，每条记录为 {"record_id": "xxx", "fields": {"字段名": 值, ...}}

        Returns:
            更新结果
        """
        try:
            logger.info(f"批量更新记录: app_token={app_token}, table_id={table_id}, count={len(records)}")

            data = {
                "records": records,
            }

            result = await self._make_request(
                method="POST",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update",
                data=data,
            )

            updated_records = result.get("data", {}).get("records", [])

            record_list = []
            for record in updated_records:
                record_list.append({
                    "record_id": record.get("record_id"),
                    "fields": record.get("fields", {}),
                    "updated_time": record.get("updated_time"),
                })

            logger.info(f"成功批量更新 {len(record_list)} 条记录")
            return {
                "success": True,
                "records": record_list,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"批量更新记录失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"批量更新记录发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"批量更新记录时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def delete_record(
        self,
        app_token: str,
        table_id: str,
        record_id: str,
    ) -> Dict[str, Any]:
        """
        删除单条记录

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID
            record_id: 记录ID

        Returns:
            删除结果
        """
        try:
            logger.info(f"删除记录: app_token={app_token}, table_id={table_id}, record_id={record_id}")

            result = await self._make_request(
                method="DELETE",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
            )

            record = result.get("data", {})

            logger.info(f"记录删除成功: record_id={record.get('record_id')}")
            return {
                "success": True,
                "record_id": record.get("record_id"),
                "deleted": True,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"删除记录失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"删除记录发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"删除记录时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def delete_table(
        self,
        app_token: str,
        table_id: str,
    ) -> Dict[str, Any]:
        """
        删除数据表

        Args:
            app_token: 多维表格的token
            table_id: 要删除的数据表ID

        Returns:
            删除结果
        """
        try:
            logger.info(f"删除数据表: app_token={app_token}, table_id={table_id}")

            result = await self._make_request(
                method="DELETE",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}",
            )

            logger.info(f"数据表删除成功: table_id={table_id}")
            return {
                "success": True,
                "table_id": table_id,
                "deleted": True,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"删除数据表失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"删除数据表发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"删除数据表时发生未知错误: {str(e)}",
                "error_code": -1
            }

    async def list_fields(
        self,
        app_token: str,
        table_id: str,
    ) -> Dict[str, Any]:
        """
        获取数据表的字段列表

        Args:
            app_token: 多维表格的token
            table_id: 数据表ID

        Returns:
            字段列表
        """
        try:
            logger.info(f"获取字段列表: app_token={app_token}, table_id={table_id}")

            result = await self._make_request(
                method="GET",
                endpoint=f"/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
            )

            items = result.get("data", {}).get("items", [])

            fields = []
            for item in items:
                fields.append({
                    "field_id": item.get("field_id"),
                    "field_name": item.get("field_name"),
                    "type": item.get("type"),
                    "property": item.get("property", {}),
                    "description": item.get("description"),
                    "is_primary": item.get("is_primary"),
                })

            logger.info(f"成功获取 {len(fields)} 个字段")
            return {
                "success": True,
                "fields": fields,
            }

        except FeishuAPIError as e:
            error_msg = self._parse_bitable_error(e.code, e.message)
            logger.error(f"获取字段列表失败: code={e.code}, message={e.message}, parsed={error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "error_code": e.code
            }
        except Exception as e:
            logger.error(f"获取字段列表发生未知异常: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"获取字段列表时发生未知错误: {str(e)}",
                "error_code": -1
            }

    def _parse_bitable_error(self, code: int, default_message: str) -> str:
        """
        解析多维表格相关的错误码，返回友好的错误信息

        Args:
            code: 错误码
            default_message: 默认错误信息

        Returns:
            友好的错误信息
        """
        error_messages = {
            1770001: "参数不合法，请检查请求参数",
            1770002: "多维表格不存在，请确认token是否正确",
            1770003: "资源已被删除",
            1770031: "数据表不存在，请确认table_id是否正确",
            1770032: "记录不存在，请确认record_id是否正确",
            1770033: "字段不存在，请确认字段名或field_id是否正确",
            1770034: "请求中涉及单元格个数过多，请拆分成多次请求",
            1770035: "字段类型不匹配，请检查数据类型",
            1770036: "字段值格式错误",
            1770037: "数据表名重复",
            1770038: "字段名重复",
            1770039: "数据表数量超过上限",
            1770040: "记录数量超过上限",
            1770041: "字段数量超过上限",
            1770042: "单元格内容长度超过限制",
            1770043: "数字值超出范围",
            1770044: "日期格式错误",
            1770045: "超链接格式错误",
            1770046: "人员格式错误",
            1770047: "附件格式错误",
            1770048: "单选选项不存在",
            1770049: "多选选项不存在",
            1770050: "关联表格不存在",
            1770051: "表单字段不能更新",
            1770052: "公式字段不能更新",
            1770053: "自动编号字段不能更新",
            1770054: "创建人字段不能更新",
            1770055: "创建时间字段不能更新",
            1770056: "修改人字段不能更新",
            1770057: "修改时间字段不能更新",
            1770058: "不支持的字段类型",
            1770059: "不支持的操作",
            1770060: "权限不足，无法访问多维表格。请确保：1) 应用已在开放平台配置多维表格权限；2) 多维表格已授权给应用访问",
            1770061: "多维表格已被锁定",
            1770062: "多维表格正在被其他用户编辑，请稍后重试",
            1770063: "多维表格版本过旧，请刷新后重试",
            1770064: "批量操作失败，部分记录可能已成功",
        }

        if code in error_messages:
            return error_messages[code]
        else:
            return default_message


def get_feishu_client() -> FeishuClient:
    """获取飞书客户端实例"""
    return FeishuClient()
