from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # 飞书应用配置
    FEISHU_APP_ID: Optional[str] = None
    FEISHU_APP_SECRET: Optional[str] = None
    FEISHU_ENCRYPT_KEY: Optional[str] = None
    FEISHU_VERIFICATION_TOKEN: Optional[str] = None

    # 大模型配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = "https://api.openai.com/v1"
    OPENAI_MODEL: Optional[str] = "gpt-4o"

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/feishu_agent.log"

    # 应用配置
    APP_NAME: str = "FeishuSmartAgent"
    APP_VERSION: str = "1.0.0"

    # HTTP 服务器配置
    HTTP_HOST: str = "0.0.0.0"
    HTTP_PORT: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


settings = Settings()
