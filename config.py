from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
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
    model_config = SettingsConfigDict(env_file=".env")






