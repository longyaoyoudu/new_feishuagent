# 飞书智能体 (Feishu Agent)

> 基于 Langchain 的飞书/Lark 智能机器人,支持自然语言驱动的日程管理、云文档总结、聊天记录总结、多维表格操作等能力。

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Langchain](https://img.shields.io/badge/Langchain-0.2%2B-green)
![License](https://img.shields.io/badge/license-Internal-lightgrey)
![Version](https://img.shields.io/badge/version-1.0.0-orange)

---

## ✨ 功能特性

- **📅 日程管理(Calendar)**:自然语言解析时间(如"下周三下午3点开会"),自动创建飞书日历事件
- **📄 云文档总结(Document)**:读取飞书云文档内容,自动总结、问答
- **📊 多维表格(Bitable)**:飞书多维表格的增删改查、批量操作、模糊匹配
- **💬 智能对话(Chat)**:基于 LLM 的多轮对话,自带 20 轮上下文记忆
- **📝 聊天总结(Chat Summary)**:群聊/单聊消息自动总结,提取关键信息
- **🔌 多种接入方式**:支持 WebSocket、HTTP、SDK 三种事件接入模式

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| LLM 框架 | Langchain 0.2+ / LangGraph |
| LLM | OpenAI 兼容接口(默认 `gpt-4o`,可通过 `OPENAI_API_BASE` 切换) |
| 飞书 SDK | lark-oapi 1.5+ |
| 异步 | asyncio + aiohttp + httpx |
| 配置 | pydantic-settings + python-dotenv |
| 日志 | loguru |
| 重试 | tenacity |

## 🏗️ 架构

```
feishu_cli_manage/
├── main.py                    # CLI 入口(本地对话测试)
├── bot_server.py              # HTTP bot 服务
├── bot_ws_server.py           # WebSocket bot 服务
├── agents/
│   └── feishu_agent.py        # 智能体核心,统一调度各模块
├── bot/                       # 飞书事件接入层
│   ├── server.py              # HTTP 服务
│   ├── sdk_server.py          # SDK 模式服务
│   ├── ws_handler.py          # WebSocket 长连接
│   └── message_handler.py     # 事件分发与处理
├── modules/                   # 业务模块(各功能解耦,可独立调用)
│   ├── base_module.py         # 模块基类
│   ├── calendar_module.py     # 日程管理(1029 行)
│   ├── document_module.py     # 云文档(348 行)
│   ├── spreadsheet_module.py  # 多维表格(1356 行)
│   ├── chat_module.py         # 智能对话(177 行)
│   └── chat_summary_module.py # 聊天总结(698 行)
├── utils/
│   ├── feishu_client.py       # 飞书 OpenAPI 客户端封装(单例 + 令牌缓存)
│   ├── event_utils.py         # 飞书事件工具
│   ├── text_utils.py          # 文本处理
│   ├── exceptions.py          # 异常体系
│   └── logger.py              # 日志配置
├── config/settings.py         # 基于 pydantic 的配置
├── session/                   # 会话状态管理
└── test_*.py                  # 测试文件
```

模块设计原则:

- **单一职责**:每个模块只负责一个业务领域
- **继承基类**:统一从 `BaseModule` 继承,实现 `process()` 接口
- **可插拔**:新增模块只需继承基类并在 `FeishuAgent` 中注册

## 🚀 快速开始

### 1. 克隆并安装

```bash
git clone https://github.com/longyaoyoudu/new_feishuagent.git
cd new_feishuagent

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`,填入以下必需项:

```ini
# ===== LLM =====
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# ===== 飞书应用 =====
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_VERIFICATION_TOKEN=xxx
FEISHU_ENCRYPT_KEY=xxx                # 可选

# ===== Bot 服务 =====
HTTP_HOST=0.0.0.0
HTTP_PORT=8000
```

> 飞书应用配置可在 [飞书开放平台](https://open.feishu.cn) → 应用后台获取。

### 3. 启动方式

**CLI 本地对话测试**(不需要飞书应用):

```bash
python main.py
```

**WebSocket Bot 服务**:

```bash
python bot_ws_server.py
```

**HTTP Bot 服务**:

```bash
python bot_server.py
```

## 💡 使用示例

### 日程管理

```
用户: 帮我下周三下午3点安排一个产品评审会议
智能体: 已为您创建日历事件:
       📅 产品评审会议
       ⏰ 2026-06-17 15:00 - 16:00
       📍 [默认日历]
```

支持的时间表达:

- 相对时间:"明天下午3点"、"下周一"、"下个月第一天"
- 绝对时间:"2026-07-01 10:00"
- 口语表达:"后天晚上8点"、"下下周五上午"

### 云文档总结

```
用户: 帮我总结这个文档 https://feishu.cn/docs/xxxxx
智能体: 📄 文档总结:
       1. 核心观点:......
       2. 关键决策:......
       3. 待办事项:......
```

### 智能对话

支持多轮上下文,自动记忆 20 轮对话历史。

## 🧪 测试

```bash
# 全部测试
pytest test_*.py -v

# 单个测试
pytest test_calendar_time_parse.py -v
pytest test_document_module.py -v
pytest test_agent_chat.py -v
```

测试覆盖范围:

| 测试文件 | 覆盖范围 |
|---------|---------|
| `test_calendar_time_parse.py` | 时间关键词解析 |
| `test_document_module.py` | 文档模块 |
| `test_agent_chat.py` / `simple_chat_test.py` | 智能体对话 |
| `test_connection_stability.py` | WebSocket 长连接稳定性 |
| `test_text_filter.py` | 文本过滤 |
| `test_ws_import.py` | WS 导入 |

## 🔧 开发指南

### 新增一个业务模块

1. 在 `modules/` 下创建 `my_module.py`,继承 `BaseModule`:

```python
from modules.base_module import BaseModule

class MyModule(BaseModule):
    name = "my_module"

    async def process(self, message: str, context: dict) -> str:
        # 实现业务逻辑
        return "处理结果"
```

2. 在 `agents/feishu_agent.py` 的 `_setup_modules()` 中注册:

```python
from modules.my_module import MyModule
# ...
self.modules["my_module"] = MyModule()
```

3. 编写测试:`test_my_module.py`

### 切换 LLM

修改 `.env`:

```ini
# 切换到 DeepSeek
OPENAI_API_BASE=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat

# 切换到本地 Ollama
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_MODEL=qwen2.5
```

## 📋 待办与规划

- [ ] 引入 LangGraph 替换简单 chain,实现更复杂的工作流
- [ ] 完善单元测试覆盖率(当前测试以集成/手工为主)
- [ ] 抽象插件注册机制,降低新增模块成本
- [ ] Docker 镜像和 docker-compose 部署
- [ ] CI 流水线(lint + test)
- [ ] 接入向量数据库,支持文档语义检索
- [ ] 飞书卡片消息优化(交互式按钮)

## 🐛 常见问题

**Q: 启动时报 `OPENAI_API_KEY 未配置`?**
A: 检查 `.env` 文件是否存在于项目根目录,且 `OPENAI_API_KEY` 已正确填写。

**Q: 飞书事件接收不到?**
A: 飞书应用需要开启"事件订阅"能力,回调 URL 配置为公网可访问的 `https://your-domain/webhook`。

**Q: WebSocket 连接频繁断开?**
A: 检查网络环境,或调整 `ws_handler.py` 中的心跳间隔。

## 📄 License

本项目为内部项目,暂不开源。

## 🤝 贡献

目前由项目所有者维护。如需提交代码,请:

1. Fork 仓库
2. 创建特性分支 (`git checkout -b feat/amazing-feature`)
3. 提交改动 (`git commit -m 'feat: add amazing feature'`)
4. 推送分支 (`git push origin feat/amazing-feature`)
5. 创建 Pull Request

---

**Made with ❤️ by bryant**
