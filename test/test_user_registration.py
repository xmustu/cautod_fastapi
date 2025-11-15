"""
用户注册改进功能测试示例
运行: pytest test_user_registration.py -v
"""
import pytest
from pydantic import ValidationError
from apps.schemas.user_improved import UserRegisterRequest


class TestUsernameValidation:
    """用户名验证测试"""
    
    def test_valid_username(self):
        """测试有效的用户名"""
        valid_usernames = [
            "alice",
            "alice123",
            "alice_bob",
            "张三",
            "user_123",
            "alice王小明"
        ]
        for username in valid_usernames:
            data = {
                "username": username,
                "email": "test@example.com",
                "password": "SecurePass123!"
            }
            user = UserRegisterRequest(**data)
            assert user.username == username.strip()
    
    def test_username_too_short(self):
        """测试用户名太短"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="ab",
                email="test@example.com",
                password="SecurePass123!"
            )
        assert "用户名至少需要3个字符" in str(exc_info.value)
    
    def test_username_too_long(self):
        """测试用户名太长"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="a" * 51,
                email="test@example.com",
                password="SecurePass123!"
            )
        assert "用户名不能超过50个字符" in str(exc_info.value)
    
    def test_username_invalid_chars(self):
        """测试用户名包含非法字符"""
        invalid_usernames = [
            "user@name",
            "user name",
            "user-name",
            "user.name",
            "user#123"
        ]
        for username in invalid_usernames:
            with pytest.raises(ValidationError) as exc_info:
                UserRegisterRequest(
                    username=username,
                    email="test@example.com",
                    password="SecurePass123!"
                )
            assert "只能包含字母、数字、下划线和中文字符" in str(exc_info.value)
    
    def test_username_all_digits(self):
        """测试纯数字用户名"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="123456",
                email="test@example.com",
                password="SecurePass123!"
            )
        assert "用户名不能为纯数字" in str(exc_info.value)
    
    def test_username_reserved(self):
        """测试保留用户名"""
        reserved = ["admin", "root", "system", "test"]
        for username in reserved:
            with pytest.raises(ValidationError) as exc_info:
                UserRegisterRequest(
                    username=username,
                    email="test@example.com",
                    password="SecurePass123!"
                )
            assert "保留名称" in str(exc_info.value)


class TestPasswordValidation:
    """密码验证测试"""
    
    def test_valid_password(self):
        """测试有效的密码"""
        valid_passwords = [
            "SecurePass123!",
            "MyP@ssw0rd",
            "C0mpl3x!Pass",
            "Str0ng&P@ss"
        ]
        for password in valid_passwords:
            user = UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password=password
            )
            assert user.password == password
    
    def test_password_too_short(self):
        """测试密码太短"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="Pass1!"
            )
        assert "密码至少需要8个字符" in str(exc_info.value)
    
    def test_password_no_uppercase(self):
        """测试缺少大写字母"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="password123!"
            )
        assert "必须包含至少一个大写字母" in str(exc_info.value)
    
    def test_password_no_lowercase(self):
        """测试缺少小写字母"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="PASSWORD123!"
            )
        assert "必须包含至少一个小写字母" in str(exc_info.value)
    
    def test_password_no_digit(self):
        """测试缺少数字"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="SecurePass!"
            )
        assert "必须包含至少一个数字" in str(exc_info.value)
    
    def test_password_no_special_char(self):
        """测试缺少特殊字符"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="SecurePass123"
            )
        assert "必须包含至少一个特殊字符" in str(exc_info.value)
    
    def test_password_common_weak(self):
        """测试常见弱密码"""
        weak_passwords = [
            "Password123!",
            "Aa123456!",
            "Admin123!"
        ]
        for password in weak_passwords:
            with pytest.raises(ValidationError) as exc_info:
                UserRegisterRequest(
                    username="testuser",
                    email="test@example.com",
                    password=password
                )
            assert "密码过于简单" in str(exc_info.value)
    
    def test_password_sequential_chars(self):
        """测试连续字符"""
        with pytest.raises(ValidationError) as exc_info:
            UserRegisterRequest(
                username="testuser",
                email="test@example.com",
                password="Pass123word!"
            )
        assert "不应包含连续的字符序列" in str(exc_info.value)


class TestEmailValidation:
    """邮箱验证测试"""
    
    def test_valid_email(self):
        """测试有效的邮箱"""
        valid_emails = [
            "user@example.com",
            "test.user@example.com",
            "user+tag@example.co.uk",
            "user123@test-domain.com"
        ]
        for email in valid_emails:
            user = UserRegisterRequest(
                username="testuser",
                email=email,
                password="SecurePass123!"
            )
            assert user.email == email
    
    def test_invalid_email(self):
        """测试无效的邮箱"""
        invalid_emails = [
            "notanemail",
            "@example.com",
            "user@",
            "user@.com",
            "user space@example.com"
        ]
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                UserRegisterRequest(
                    username="testuser",
                    email=email,
                    password="SecurePass123!"
                )


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
