"""
登录认证路由集成测试
测试登录、密码重置、邮箱验证等 API 端点
"""
import pytest
from httpx import AsyncClient
from fastapi import status

# 这些测试需要在实际运行的 FastAPI 应用中执行
# 可以使用 pytest-asyncio 和 httpx 进行异步测试


@pytest.mark.asyncio
class TestLoginRoutes:
    """测试登录相关路由"""
    
    async def test_login_with_valid_credentials(self, async_client: AsyncClient, test_user):
        """测试使用有效凭证登录"""
        response = await async_client.post(
            "/api/auth/login/access-token",
            data={
                "username": test_user["email"],
                "password": test_user["password"]
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0
    
    async def test_login_with_invalid_email(self, async_client: AsyncClient):
        """测试使用不存在的邮箱登录"""
        response = await async_client.post(
            "/api/auth/login/access-token",
            data={
                "username": "nonexistent@example.com",
                "password": "anypassword"
            }
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Incorrect email or password" in response.json()["detail"]
    
    async def test_login_with_wrong_password(self, async_client: AsyncClient, test_user):
        """测试使用错误密码登录"""
        response = await async_client.post(
            "/api/auth/login/access-token",
            data={
                "username": test_user["email"],
                "password": "wrongpassword"
            }
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Incorrect email or password" in response.json()["detail"]
    
    async def test_login_missing_credentials(self, async_client: AsyncClient):
        """测试缺少凭证的登录请求"""
        response = await async_client.post(
            "/api/auth/login/access-token",
            data={}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
class TestTokenValidation:
    """测试 token 验证"""
    
    async def test_test_token_with_valid_token(self, async_client: AsyncClient, auth_headers):
        """测试使用有效 token 访问测试端点"""
        response = await async_client.post(
            "/api/auth/login/test-token",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "user_id" in data
        assert "email" in data
        assert "role" in data
    
    async def test_test_token_with_invalid_token(self, async_client: AsyncClient):
        """测试使用无效 token 访问测试端点"""
        response = await async_client.post(
            "/api/auth/login/test-token",
            headers={"Authorization": "Bearer invalid_token"}
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_test_token_without_token(self, async_client: AsyncClient):
        """测试不提供 token 访问测试端点"""
        response = await async_client.post(
            "/api/auth/login/test-token"
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
class TestPasswordRecovery:
    """测试密码找回功能"""
    
    async def test_password_recovery_existing_user(self, async_client: AsyncClient, test_user):
        """测试为存在的用户请求密码重置"""
        response = await async_client.post(
            "/api/auth/password-recovery",
            json={"email": test_user["email"]}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "Password recovery email sent" in data["message"]
    
    async def test_password_recovery_nonexistent_user(self, async_client: AsyncClient):
        """测试为不存在的用户请求密码重置（应返回相同消息以防枚举）"""
        response = await async_client.post(
            "/api/auth/password-recovery",
            json={"email": "nonexistent@example.com"}
        )
        
        # 即使用户不存在也应返回成功（安全考虑）
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "email" in data["message"].lower()
    
    async def test_password_recovery_invalid_email_format(self, async_client: AsyncClient):
        """测试使用无效邮箱格式请求密码重置"""
        response = await async_client.post(
            "/api/auth/password-recovery",
            json={"email": "not-an-email"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
class TestPasswordReset:
    """测试密码重置功能"""
    
    async def test_reset_password_with_valid_token(
        self, 
        async_client: AsyncClient, 
        test_user, 
        password_reset_token
    ):
        """测试使用有效 token 重置密码"""
        new_password = "NewSecurePassword123!"
        
        response = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": password_reset_token,
                "new_password": new_password
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "Password updated successfully" in data["message"]
        
        # 验证可以使用新密码登录
        login_response = await async_client.post(
            "/api/auth/login/access-token",
            data={
                "username": test_user["email"],
                "password": new_password
            }
        )
        assert login_response.status_code == status.HTTP_200_OK
    
    async def test_reset_password_with_invalid_token(self, async_client: AsyncClient):
        """测试使用无效 token 重置密码"""
        response = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": "invalid_token",
                "new_password": "NewPassword123!"
            }
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid or expired token" in response.json()["detail"]
    
    async def test_reset_password_with_expired_token(
        self, 
        async_client: AsyncClient, 
        expired_password_reset_token
    ):
        """测试使用过期 token 重置密码"""
        response = await async_client.post(
            "/api/auth/reset-password",
            json={
                "token": expired_password_reset_token,
                "new_password": "NewPassword123!"
            }
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid or expired token" in response.json()["detail"]


@pytest.mark.asyncio
class TestEmailVerification:
    """测试邮箱验证功能"""
    
    async def test_send_verification_email(self, async_client: AsyncClient, auth_headers):
        """测试发送邮箱验证邮件"""
        response = await async_client.post(
            "/api/auth/send-verification-email",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "Verification email sent" in data["message"]
    
    async def test_send_verification_email_unauthorized(self, async_client: AsyncClient):
        """测试未登录时发送验证邮件"""
        response = await async_client.post(
            "/api/auth/send-verification-email"
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_verify_email_with_valid_token(
        self, 
        async_client: AsyncClient, 
        email_verification_token
    ):
        """测试使用有效 token 验证邮箱"""
        response = await async_client.post(
            "/api/auth/verify-email",
            json={"token": email_verification_token}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "verified successfully" in data["message"]
    
    async def test_verify_email_with_invalid_token(self, async_client: AsyncClient):
        """测试使用无效 token 验证邮箱"""
        response = await async_client.post(
            "/api/auth/verify-email",
            json={"token": "invalid_token"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid or expired" in response.json()["detail"]
    
    async def test_verify_email_html_success(
        self, 
        async_client: AsyncClient, 
        email_verification_token
    ):
        """测试邮箱验证成功页面"""
        response = await async_client.get(
            f"/api/auth/verify-email-html/{email_verification_token}"
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
        assert "✅" in response.text or "success" in response.text.lower()
    
    async def test_verify_email_html_invalid_token(self, async_client: AsyncClient):
        """测试邮箱验证失败页面"""
        response = await async_client.get(
            "/api/auth/verify-email-html/invalid_token"
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "text/html" in response.headers["content-type"]
        assert "❌" in response.text or "failed" in response.text.lower()


@pytest.mark.asyncio
class TestPasswordRecoveryHTML:
    """测试密码找回 HTML 预览功能"""
    
    async def test_get_password_recovery_html(
        self, 
        async_client: AsyncClient, 
        auth_headers,
        test_user
    ):
        """测试获取密码找回邮件 HTML 内容"""
        response = await async_client.get(
            f"/api/auth/password-recovery-html/{test_user['email']}",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
        assert "Password" in response.text or "password" in response.text
    
    async def test_get_password_recovery_html_unauthorized(
        self, 
        async_client: AsyncClient,
        test_user
    ):
        """测试未登录时获取密码找回邮件 HTML"""
        response = await async_client.get(
            f"/api/auth/password-recovery-html/{test_user['email']}"
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_get_password_recovery_html_nonexistent_user(
        self, 
        async_client: AsyncClient, 
        auth_headers
    ):
        """测试获取不存在用户的密码找回邮件 HTML"""
        response = await async_client.get(
            "/api/auth/password-recovery-html/nonexistent@example.com",
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND


# Pytest fixtures
@pytest.fixture
async def async_client(app):
    """提供异步 HTTP 客户端"""
    from httpx import AsyncClient
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def test_user(database):
    """创建测试用户"""
    from database.models import Users
    from core.hashing import Hasher
    
    email = "testuser@example.com"
    password = "TestPassword123!"
    
    user = await Users.create(
        email=email,
        username="testuser",
        password_hash=Hasher.get_password_hash(password)
    )
    
    yield {
        "user_id": user.user_id,
        "email": email,
        "password": password
    }
    
    # 清理
    await user.delete()


@pytest.fixture
async def auth_headers(async_client: AsyncClient, test_user):
    """提供认证头"""
    response = await async_client.post(
        "/api/auth/login/access-token",
        data={
            "username": test_user["email"],
            "password": test_user["password"]
        }
    )
    token = response.json()["access_token"]
    
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def password_reset_token(test_user):
    """提供密码重置 token"""
    from core.email_utils import generate_password_reset_token
    return generate_password_reset_token(test_user["email"])


@pytest.fixture
def expired_password_reset_token(test_user):
    """提供过期的密码重置 token"""
    import jwt
    from datetime import datetime, timedelta, timezone
    from core.authentication import SECRET_KEY, ALGORITHM
    
    now = datetime.now(timezone.utc)
    expires = now - timedelta(hours=1)  # 1 小时前过期
    exp = expires.timestamp()
    
    return jwt.encode(
        {"exp": exp, "nbf": now - timedelta(hours=2), "sub": test_user["email"]},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


@pytest.fixture
def email_verification_token(test_user):
    """提供邮箱验证 token"""
    from core.email_utils import generate_email_verification_token
    return generate_email_verification_token(test_user["email"])


@pytest.fixture
async def database():
    """设置测试数据库"""
    from tortoise import Tortoise
    from database.settings import TORTOISE_ORM_SQLITE
    
    await Tortoise.init(config=TORTOISE_ORM_SQLITE)
    await Tortoise.generate_schemas()
    
    yield
    
    await Tortoise.close_connections()


@pytest.fixture
def app():
    """提供 FastAPI 应用实例"""
    from main import app
    return app


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
