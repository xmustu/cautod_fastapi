from pydantic_settings import BaseSettings,SettingsConfigDict


class Settings(BaseSettings):
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
    REDIS_AVAILABLE: bool

    OPTIMIZE_API_URL: str
    DIFY_API_BASE_URL: str
    DIFY_API_KEY: str
    DIFY_LISTEN_HOST: str
    DIFY_LISTEN_PORT: int
    DIFY_TARGET_HOST: str
    DIFY_TARGET_PORT: int
    model_config = SettingsConfigDict(env_file=".env")

    # class Settings:
    #     env_file = ".env"



settings = Settings()






