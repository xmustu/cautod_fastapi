from typing import Optional
from pydantic_settings import BaseSettings,SettingsConfigDict

from pydantic import (
    AnyUrl,
    BeforeValidator,
    EmailStr,
    HttpUrl,
    PostgresDsn,
    computed_field,
    model_validator,
)

class Settings(BaseSettings):
    PROJECT_NAME: str
    FRONTEND_HOST: str
    DEBUG_MODE: bool =False

    
    DIRECTORY: str
    STATIC_DIR:str 
    STATIC_URL:str 
    STATIC_NAME:str 
    SQLMODE: str
    MYSQL_HOST:str = "240e:3bc:266:b4d0:8ed2:275a:f1a9:7b4d"
    MYSQL_PORT:str = '3306'
    MYSQL_USER:str = 'lwx'
    MYSQL_PASSWORD:str = "i4AIi4AI"
    MYSQL_DATABASE:str = "cautod"

    TEMPLATES_DIR:str ="/templates"

    
    # SMTP 邮件服务配置
    EMAILS_ENABLED: bool = False
    SMTP_HOST: Optional[str] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: Optional[EmailStr] = None
    EMAILS_FROM_NAME: Optional[str] = None
    SMTP_TLS: bool = False
    SMTP_SSL: bool = True
    SMTP_PORT: int = 465
    EMAIL_RESET_TOKEN_EXPIRE_HOURS: int
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS: int
    EMAIL_VERIFICATION_CODE_EXPIRE_MINUTES: int = 10

    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_REDIRECT_URL: str
    GITHUB_TOKEN_URL: str
    GITHUB_USER_URL: str

    
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URL: str
    GOOGLE_AUTHORIZATION_URL: str
    GOOGLE_TOKEN_URL: str
    GOOGLE_USER_INFO_URL: str

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str = None
    REDIS_DB : int
    REDIS_AVAILABLE: bool

    OPTIMIZE_API_URL: str
    DIFY_API_BASE_URL: str
    DIFY_API_KEY: str
    DIFY_LISTEN_HOST: str
    DIFY_LISTEN_PORT: int
    DIFY_TARGET_HOST: str
    DIFY_TARGET_PORT: int
    
    # Dify Chat Embedding Configuration
    DIFY_CHAT_TOKEN: str
    DIFY_CHAT_BASE_URL: str
    
    # 系统配置默认值（用于初始化数据库配置）
    SYSTEM_MAX_TASKS_PER_USER: int = 100
    SYSTEM_MAX_CONVERSATIONS_PER_USER: int = 50
    SYSTEM_ENABLE_REGISTRATION: bool = True
    SYSTEM_ENABLE_EMAIL_VERIFICATION: bool = True
    SYSTEM_ENABLE_EMAIL_NOTIFICATIONS: bool = True
    SYSTEM_MAINTENANCE_MODE: bool = False
    SYSTEM_MAX_FILE_SIZE_MB: int = 100
    SYSTEM_API_RATE_LIMIT: int = 100
    SYSTEM_SESSION_TIMEOUT_MINUTES: int = 60
    SYSTEM_DEFAULT_USER_ROLE: str = "user"
    
    model_config = SettingsConfigDict(env_file=".env.prod")

    # class Settings:
    #     env_file = ".env"



settings = Settings()






