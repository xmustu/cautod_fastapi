from pydantic import BaseModel
from config import Settings

settings = Settings()

class AuthConfig(BaseModel):
    client_id: str = settings.GITHUB_CLIENT_ID
    client_srecret: str = settings.GITHUB_CLIENT_SECRET
    redirect_url: str = "http://localhost:8080/auth/github/callback"
    token_url: str = "https://github.com/login/oauth/access_token"
    user_url: str = "https://api.github.com/user"