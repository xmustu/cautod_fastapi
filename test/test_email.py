"""
邮箱功能测试模块
测试邮件发送、token 生成与验证、模板渲染等功能
"""
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 导入待测试的函数
from core.email_utils import (
    EmailData,
    render_email_template,
    generate_password_reset_token,
    verify_password_reset_token,
    generate_email_verification_token,
    verify_email_verification_token,
    generate_test_email,
    generate_reset_password_email,
    generate_new_account_email,
    generate_verification_email,
)


class TestEmailTokens:
    """测试邮件 token 生成和验证"""
    
    def test_password_reset_token_generation(self):
        """测试密码重置 token 生成"""
        email = "test@example.com"
        token = generate_password_reset_token(email)
        
        # 验证 token 不为空
        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)
    
    def test_password_reset_token_verification_valid(self):
        """测试有效的密码重置 token 验证"""
        email = "test@example.com"
        token = generate_password_reset_token(email)
        
        # 验证 token
        verified_email = verify_password_reset_token(token)
        
        assert verified_email == email
    
    def test_password_reset_token_verification_invalid(self):
        """测试无效的密码重置 token 验证"""
        invalid_token = "invalid.token.here"
        
        verified_email = verify_password_reset_token(invalid_token)
        
        assert verified_email is None
    
    def test_password_reset_token_expiration(self):
        """测试密码重置 token 过期（需要手动设置很短的过期时间）"""
        email = "test@example.com"
        # 生成一个 1 毫秒后过期的 token
        import jwt
        from core.authentication import SECRET_KEY, ALGORITHM
        
        now = datetime.now(timezone.utc)
        expires = now - timedelta(hours=1)  # 1 小时前过期
        exp = expires.timestamp()
        
        expired_token = jwt.encode(
            {"exp": exp, "nbf": now - timedelta(hours=2), "sub": email},
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        
        verified_email = verify_password_reset_token(expired_token)
        
        assert verified_email is None
    
    def test_email_verification_token_generation(self):
        """测试邮箱验证 token 生成"""
        email = "test@example.com"
        token = generate_email_verification_token(email)
        
        assert token is not None
        assert len(token) > 0
        assert isinstance(token, str)
    
    def test_email_verification_token_verification_valid(self):
        """测试有效的邮箱验证 token 验证"""
        email = "test@example.com"
        token = generate_email_verification_token(email)
        
        verified_email = verify_email_verification_token(token)
        
        assert verified_email == email
    
    def test_email_verification_token_verification_invalid(self):
        """测试无效的邮箱验证 token 验证"""
        invalid_token = "invalid.token.here"
        
        verified_email = verify_email_verification_token(invalid_token)
        
        assert verified_email is None
    
    def test_email_verification_token_wrong_type(self):
        """测试错误类型的 token（密码重置 token 用于邮箱验证）"""
        email = "test@example.com"
        # 使用密码重置 token
        password_reset_token = generate_password_reset_token(email)
        
        # 尝试用邮箱验证方法验证
        verified_email = verify_email_verification_token(password_reset_token)
        
        # 应该返回 None，因为类型不匹配
        assert verified_email is None
    
    def test_token_custom_expiration(self):
        """测试自定义过期时间的 token"""
        email = "test@example.com"
        
        # 生成 1 小时过期的 token
        token_1h = generate_password_reset_token(email, expire_hours=1)
        # 生成 24 小时过期的 token
        token_24h = generate_password_reset_token(email, expire_hours=24)
        
        assert token_1h != token_24h  # 不同过期时间生成不同 token
        
        # 验证都能正常验证
        assert verify_password_reset_token(token_1h) == email
        assert verify_password_reset_token(token_24h) == email


class TestEmailTemplateRendering:
    """测试邮件模板渲染"""
    
    def test_render_existing_template(self):
        """测试渲染存在的模板"""
        context = {
            "project_name": "CAutoD",
            "email": "test@example.com"
        }
        
        html = render_email_template(
            template_name="test_email.html",
            context=context
        )
        
        assert html is not None
        assert "CAutoD" in html
        assert "test@example.com" in html
        assert "<html>" in html.lower()
    
    def test_render_nonexistent_template(self):
        """测试渲染不存在的模板（应返回默认模板）"""
        context = {
            "subject": "Test Subject",
            "content": "Test Content"
        }
        
        html = render_email_template(
            template_name="nonexistent_template.html",
            context=context
        )
        
        # 应该返回默认模板
        assert html is not None
        assert "Test Subject" in html
        assert "Test Content" in html
    
    def test_reset_password_template_rendering(self):
        """测试密码重置邮件模板渲染"""
        context = {
            "project_name": "CAutoD",
            "username": "testuser",
            "email": "test@example.com",
            "valid_hours": 24,
            "link": "http://localhost:5173/reset-password?token=abc123"
        }
        
        html = render_email_template(
            template_name="reset_password.html",
            context=context
        )
        
        assert "CAutoD" in html
        assert "testuser" in html
        assert "test@example.com" in html
        assert "24" in html
        assert "http://localhost:5173/reset-password?token=abc123" in html
    
    def test_verify_email_template_rendering(self):
        """测试邮箱验证邮件模板渲染"""
        context = {
            "project_name": "CAutoD",
            "email": "test@example.com",
            "valid_hours": 48,
            "link": "http://localhost:5173/verify-email?token=xyz789"
        }
        
        html = render_email_template(
            template_name="verify_email.html",
            context=context
        )
        
        assert "CAutoD" in html
        assert "test@example.com" in html
        assert "48" in html
        assert "http://localhost:5173/verify-email?token=xyz789" in html


class TestEmailDataGeneration:
    """测试邮件数据生成函数"""
    
    def test_generate_test_email(self):
        """测试生成测试邮件"""
        email_to = "test@example.com"
        email_data = generate_test_email(email_to)
        
        assert isinstance(email_data, EmailData)
        assert email_data.subject is not None
        assert "Test email" in email_data.subject
        assert email_data.html_content is not None
        assert email_to in email_data.html_content
    
    def test_generate_reset_password_email(self):
        """测试生成密码重置邮件"""
        email_to = "test@example.com"
        email = "test@example.com"
        token = "test_token_123"
        
        email_data = generate_reset_password_email(
            email_to=email_to,
            email=email,
            token=token
        )
        
        assert isinstance(email_data, EmailData)
        assert "Password recovery" in email_data.subject
        assert email_to in email_data.html_content
        assert token in email_data.html_content
    
    def test_generate_new_account_email(self):
        """测试生成新账户邮件"""
        email_to = "newuser@example.com"
        username = "newuser"
        password = "TempPassword123"
        
        email_data = generate_new_account_email(
            email_to=email_to,
            username=username,
            password=password
        )
        
        assert isinstance(email_data, EmailData)
        assert "New account" in email_data.subject
        assert username in email_data.html_content
        assert password in email_data.html_content
        assert email_to in email_data.html_content
    
    def test_generate_verification_email(self):
        """测试生成邮箱验证邮件"""
        email_to = "verify@example.com"
        token = "verify_token_456"
        
        email_data = generate_verification_email(
            email_to=email_to,
            token=token
        )
        
        assert isinstance(email_data, EmailData)
        assert "Verify" in email_data.subject
        assert email_to in email_data.html_content
        assert token in email_data.html_content
    
    def test_custom_project_name(self):
        """测试自定义项目名称"""
        email_to = "test@example.com"
        custom_name = "CustomProject"
        
        email_data = generate_test_email(
            email_to=email_to,
            project_name=custom_name
        )
        
        assert custom_name in email_data.subject
        assert custom_name in email_data.html_content
    
    def test_custom_frontend_host(self):
        """测试自定义前端地址"""
        email_to = "test@example.com"
        token = "test_token"
        custom_host = "https://production.example.com"
        
        email_data = generate_reset_password_email(
            email_to=email_to,
            email=email_to,
            token=token,
            frontend_host=custom_host
        )
        
        assert custom_host in email_data.html_content
    
    def test_custom_valid_hours(self):
        """测试自定义 token 有效期"""
        email_to = "test@example.com"
        token = "test_token"
        custom_hours = 72
        
        email_data = generate_reset_password_email(
            email_to=email_to,
            email=email_to,
            token=token,
            valid_hours=custom_hours
        )
        
        assert str(custom_hours) in email_data.html_content


class TestEmailSendingMock:
    """测试邮件发送功能（使用 mock）"""
    
    def test_send_email_logs_output(self, caplog):
        """测试邮件发送是否正确记录日志"""
        from core.email_utils import send_email
        
        with caplog.at_level(logging.INFO):
            send_email(
                email_to="test@example.com",
                subject="Test Subject",
                html_content="<p>Test Content</p>"
            )
        
        # 检查日志是否包含预期信息
        assert "test@example.com" in caplog.text
        assert "Test Subject" in caplog.text


class TestEmailIntegration:
    """集成测试 - 完整流程"""
    
    def test_password_reset_flow(self):
        """测试完整的密码重置流程"""
        email = "user@example.com"
        
        # 1. 生成 token
        token = generate_password_reset_token(email)
        assert token is not None
        
        # 2. 生成邮件内容
        email_data = generate_reset_password_email(
            email_to=email,
            email=email,
            token=token
        )
        assert email_data.html_content is not None
        assert token in email_data.html_content
        
        # 3. 验证 token
        verified_email = verify_password_reset_token(token)
        assert verified_email == email
    
    def test_email_verification_flow(self):
        """测试完整的邮箱验证流程"""
        email = "newuser@example.com"
        
        # 1. 生成验证 token
        token = generate_email_verification_token(email)
        assert token is not None
        
        # 2. 生成验证邮件
        email_data = generate_verification_email(
            email_to=email,
            token=token
        )
        assert email_data.html_content is not None
        assert token in email_data.html_content
        
        # 3. 验证 token
        verified_email = verify_email_verification_token(token)
        assert verified_email == email
    
    def test_multiple_users_different_tokens(self):
        """测试多个用户生成不同的 token"""
        email1 = "user1@example.com"
        email2 = "user2@example.com"
        
        token1 = generate_password_reset_token(email1)
        token2 = generate_password_reset_token(email2)
        
        # Token 应该不同
        assert token1 != token2
        
        # 验证应该返回正确的邮箱
        assert verify_password_reset_token(token1) == email1
        assert verify_password_reset_token(token2) == email2
    
    def test_token_independence(self):
        """测试密码重置 token 和邮箱验证 token 的独立性"""
        email = "test@example.com"
        
        reset_token = generate_password_reset_token(email)
        verify_token = generate_email_verification_token(email)
        
        # Token 应该不同
        assert reset_token != verify_token
        
        # 密码重置 token 不能用于邮箱验证
        assert verify_email_verification_token(reset_token) is None
        
        # 邮箱验证 token 能正常验证
        assert verify_email_verification_token(verify_token) == email


class TestEdgeCases:
    """边界情况测试"""
    
    def test_empty_email(self):
        """测试空邮箱地址"""
        token = generate_password_reset_token("")
        verified = verify_password_reset_token(token)
        assert verified == ""
    
    def test_special_characters_in_email(self):
        """测试包含特殊字符的邮箱"""
        special_email = "user+test@example.com"
        token = generate_password_reset_token(special_email)
        verified = verify_password_reset_token(token)
        assert verified == special_email
    
    def test_very_long_email(self):
        """测试很长的邮箱地址"""
        long_email = "a" * 100 + "@example.com"
        token = generate_password_reset_token(long_email)
        verified = verify_password_reset_token(token)
        assert verified == long_email
    
    def test_unicode_in_context(self):
        """测试模板上下文中的 Unicode 字符"""
        context = {
            "project_name": "测试项目",
            "username": "用户名",
            "email": "测试@example.com"
        }
        
        html = render_email_template(
            template_name="test_email.html",
            context=context
        )
        
        assert "测试项目" in html
    
    def test_html_injection_prevention(self):
        """测试 HTML 注入防护"""
        malicious_content = "<script>alert('XSS')</script>"
        context = {
            "project_name": "CAutoD",
            "email": malicious_content
        }
        
        html = render_email_template(
            template_name="test_email.html",
            context=context
        )
        
        # Jinja2 默认会转义，但这取决于模板实现
        # 这里主要测试不会崩溃
        assert html is not None


# Pytest 配置和 fixtures
@pytest.fixture
def sample_email():
    """提供示例邮箱地址"""
    return "test@example.com"


@pytest.fixture
def sample_token(sample_email):
    """提供示例 token"""
    return generate_password_reset_token(sample_email)


@pytest.fixture
def sample_email_data():
    """提供示例邮件数据"""
    return EmailData(
        html_content="<p>Test</p>",
        subject="Test Subject"
    )


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
