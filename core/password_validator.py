"""
密码强度验证工具模块
提供密码强度验证策略和验证函数
"""
import re
from typing import List, Tuple


class PasswordStrength:
    """密码强度等级"""
    WEAK = "weak"
    MEDIUM = "medium"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class PasswordValidator:
    """密码验证器类"""
    
    # 常见弱密码列表（可根据需要扩展）
    COMMON_WEAK_PASSWORDS = [
        'password', 'Password', 'PASSWORD', 'password123', 'Password123',
        '12345678', '123456789', '1234567890', 'qwerty', 'qwerty123',
        'abc123', 'abc123456', 'password1', 'Password1', 'Password123',
        'Password123!', 'Aa123456', 'Aa123456!', 'Admin123', 'Admin123!',
        'welcome', 'welcome123', 'letmein', 'monkey', 'dragon',
        'master', 'sunshine', 'princess', 'football', 'iloveyou'
    ]
    
    # 连续字符模式（数字和字母）
    SEQUENTIAL_PATTERNS = [
        r'012', r'123', r'234', r'345', r'456', r'567', r'678', r'789',
        r'abc', r'bcd', r'cde', r'def', r'efg', r'fgh', r'ghi', r'hij',
        r'ijk', r'jkl', r'klm', r'lmn', r'mno', r'nop', r'opq', r'pqr',
        r'qrs', r'rst', r'stu', r'tuv', r'uvw', r'vwx', r'wxy', r'xyz',
        r'987', r'876', r'765', r'654', r'543', r'432', r'321', r'210',
        r'zyx', r'yxw', r'xwv', r'wvu', r'vut', r'uts', r'tsr', r'srq',
        r'rqp', r'qpo', r'pon', r'onm', r'nml', r'mlk', r'lkj', r'kji',
        r'jih', r'ihg', r'hgf', r'gfe', r'fed', r'edc', r'dcb', r'cba'
    ]
    
    # 重复字符模式（如 aaa, 111）
    REPEAT_PATTERNS = [
        r'(.)\1{2,}',  # 连续3个或更多相同字符
    ]
    
    @staticmethod
    def validate_password_strength(
        password: str,
        min_length: int = 8,
        min_strength: str = "medium",  # 最低强度要求: weak, medium, strong, very_strong
        max_length: int = 128,
        check_common_passwords: bool = True,
        check_sequential: bool = True,
        check_repeat: bool = True
    ) -> Tuple[bool, List[str], str]:
        """
        验证密码强度（不硬性要求字符类型，基于强度评分）
        
        Args:
            password: 待验证的密码
            min_length: 最小长度（默认8）
            min_strength: 最低强度要求（默认medium），可选: weak, medium, strong, very_strong
            max_length: 最大长度（默认128）
            check_common_passwords: 是否检查常见弱密码（默认True）
            check_sequential: 是否检查连续字符（默认True）
            check_repeat: 是否检查重复字符（默认True）
        
        Returns:
            Tuple[bool, List[str], str]:
                - bool: 验证是否通过
                - List[str]: 错误消息列表
                - str: 密码强度等级
        """
        errors = []
        password_lower = password.lower()
        
        # 1. 长度检查
        if len(password) < min_length:
            errors.append(f'密码至少需要{min_length}个字符')
        if len(password) > max_length:
            errors.append(f'密码不能超过{max_length}个字符')
        
        # 2. 常见弱密码检查
        if check_common_passwords and password in PasswordValidator.COMMON_WEAK_PASSWORDS:
            errors.append('密码过于简单，请使用更复杂的密码')
        
        # 3. 连续字符检查
        if check_sequential:
            for pattern in PasswordValidator.SEQUENTIAL_PATTERNS:
                if re.search(pattern, password_lower):
                    errors.append('密码不应包含连续的字符序列（如123、abc等）')
                    break
        
        # 4. 重复字符检查
        if check_repeat:
            for pattern in PasswordValidator.REPEAT_PATTERNS:
                if re.search(pattern, password):
                    errors.append('密码不应包含重复的字符序列（如aaa、111等）')
                    break
        
        # 5. 计算密码强度
        strength = PasswordValidator.calculate_strength(password)
        
        # 6. 强度等级检查（不硬性要求字符类型，只检查强度等级）
        strength_levels = {
            PasswordStrength.WEAK: 1,
            PasswordStrength.MEDIUM: 2,
            PasswordStrength.STRONG: 3,
            PasswordStrength.VERY_STRONG: 4
        }
        
        min_strength_level = strength_levels.get(min_strength, 2)  # 默认 medium
        current_strength_level = strength_levels.get(strength, 0)
        
        if current_strength_level < min_strength_level:
            strength_names = {
                PasswordStrength.WEAK: "弱",
                PasswordStrength.MEDIUM: "中等",
                PasswordStrength.STRONG: "强",
                PasswordStrength.VERY_STRONG: "非常强"
            }
            min_strength_name = strength_names.get(min_strength, "中等")
            errors.append(f'密码强度不足，当前强度为{PasswordValidator.get_strength_description(strength)}，需要至少{min_strength_name}强度')
        
        # 验证通过
        is_valid = len(errors) == 0
        
        return is_valid, errors, strength
    
    @staticmethod
    def calculate_strength(password: str) -> str:
        """
        计算密码强度等级（基于长度、字符多样性、复杂度，不硬性要求特定字符类型）
        
        Returns:
            str: 密码强度等级 (weak, medium, strong, very_strong)
        """
        score = 0
        length = len(password)
        
        # 1. 长度评分（权重较高）
        if length >= 16:
            score += 4
        elif length >= 12:
            score += 3
        elif length >= 10:
            score += 2
        elif length >= 8:
            score += 1
        
        # 2. 字符类型多样性评分（不强制要求，但多样性越高分数越高）
        has_upper = bool(re.search(r'[A-Z]', password))
        has_lower = bool(re.search(r'[a-z]', password))
        has_digit = bool(re.search(r'\d', password))
        has_special = bool(re.search(r'[!@#$%^&*()_+\-=\[\]{};\'",.<>?/\\|`~]', password))
        
        char_types = sum([has_upper, has_lower, has_digit, has_special])
        
        # 字符类型多样性加分
        if char_types >= 4:
            score += 3
        elif char_types >= 3:
            score += 2
        elif char_types >= 2:
            score += 1
        
        # 3. 复杂度评分（长度和多样性的组合）
        if length >= 16 and char_types >= 3:
            score += 2
        elif length >= 12 and char_types >= 2:
            score += 1
        
        # 4. 字符唯一性评分（密码中不同字符的比例）
        unique_chars = len(set(password))
        uniqueness_ratio = unique_chars / length if length > 0 else 0
        
        if uniqueness_ratio >= 0.8:  # 80%以上字符不重复
            score += 2
        elif uniqueness_ratio >= 0.6:  # 60%以上字符不重复
            score += 1
        
        # 5. 根据总分判断强度
        if score >= 8:
            return PasswordStrength.VERY_STRONG
        elif score >= 5:
            return PasswordStrength.STRONG
        elif score >= 3:
            return PasswordStrength.MEDIUM
        else:
            return PasswordStrength.WEAK
    
    @staticmethod
    def get_strength_description(strength: str) -> str:
        """获取密码强度描述"""
        descriptions = {
            PasswordStrength.WEAK: "弱",
            PasswordStrength.MEDIUM: "中等",
            PasswordStrength.STRONG: "强",
            PasswordStrength.VERY_STRONG: "非常强"
        }
        return descriptions.get(strength, "未知")

