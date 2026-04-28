/**
 * 前端集成示例 - 用户注册表单验证
 * 框架: Vue 3 / React (通用逻辑)
 */

// ==================== 1. 验证规则 ====================

/**
 * 用户名验证
 */
export const validateUsername = (username) => {
  const errors = [];
  
  // 去除首尾空格
  const trimmed = username.trim();
  
  // 长度检查
  if (trimmed.length < 3) {
    errors.push('用户名至少需要3个字符');
  }
  if (trimmed.length > 50) {
    errors.push('用户名不能超过50个字符');
  }
  
  // 格式检查:字母、数字、下划线、中文
  if (!/^[\w\u4e00-\u9fa5]+$/.test(trimmed)) {
    errors.push('用户名只能包含字母、数字、下划线和中文字符');
  }
  
  // 纯数字检查
  if (/^\d+$/.test(trimmed)) {
    errors.push('用户名不能为纯数字');
  }
  
  // 保留名称检查
  const reserved = ['admin', 'root', 'system', 'test', 'guest', 'administrator'];
  if (reserved.includes(trimmed.toLowerCase())) {
    errors.push('该用户名为保留名称,无法使用');
  }
  
  return {
    valid: errors.length === 0,
    errors,
    value: trimmed
  };
};

/**
 * 密码强度验证
 */
export const validatePassword = (password) => {
  const errors = [];
  let strength = 0; // 0-5分
  
  // 长度检查
  if (password.length < 8) {
    errors.push('密码至少需要8个字符');
  } else if (password.length >= 12) {
    strength += 1; // 长度奖励
  }
  
  if (password.length > 128) {
    errors.push('密码不能超过128个字符');
  }
  
  // 大写字母
  if (!/[A-Z]/.test(password)) {
    errors.push('密码必须包含至少一个大写字母');
  } else {
    strength += 1;
  }
  
  // 小写字母
  if (!/[a-z]/.test(password)) {
    errors.push('密码必须包含至少一个小写字母');
  } else {
    strength += 1;
  }
  
  // 数字
  if (!/\d/.test(password)) {
    errors.push('密码必须包含至少一个数字');
  } else {
    strength += 1;
  }
  
  // 特殊字符
  if (!/[!@#$%^&*()_+\-=\[\]{};:'",.<>?/\\|`~]/.test(password)) {
    errors.push('密码必须包含至少一个特殊字符 (!@#$%^&*等)');
  } else {
    strength += 1;
  }
  
  // 常见弱密码
  const commonPasswords = [
    'password', 'Password123!', '12345678', 'qwerty', 'abc123',
    'password1', 'Password1!', '123456789', 'Aa123456!', 'Admin123!'
  ];
  if (commonPasswords.includes(password)) {
    errors.push('密码过于简单,请使用更复杂的密码');
    strength = Math.min(strength, 2);
  }
  
  // 连续字符
  if (/(012|123|234|345|456|567|678|789|abc|bcd|cde)/i.test(password)) {
    errors.push('密码不应包含连续的字符序列');
    strength = Math.min(strength, 3);
  }
  
  return {
    valid: errors.length === 0,
    errors,
    strength, // 0-5
    strengthText: ['极弱', '弱', '一般', '良好', '强', '极强'][strength]
  };
};

/**
 * 邮箱验证
 */
export const validateEmail = (email) => {
  const errors = [];
  
  // 基本格式检查
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    errors.push('请输入有效的邮箱地址');
  }
  
  // 更严格的邮箱验证
  const strictEmailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  if (email && !strictEmailRegex.test(email)) {
    errors.push('邮箱格式不正确');
  }
  
  return {
    valid: errors.length === 0,
    errors,
    value: email.toLowerCase() // 统一小写
  };
};


// ==================== 2. Vue 3 组件示例 ====================

export const RegisterFormVue = `
<template>
  <div class="register-form">
    <h2>用户注册</h2>
    
    <!-- 用户名 -->
    <div class="form-group" :class="{ 'has-error': usernameErrors.length }">
      <label>用户名 *</label>
      <input 
        v-model="username" 
        @input="validateUsernameField"
        @blur="validateUsernameField"
        placeholder="3-50个字符,支持字母/数字/下划线/中文"
        :class="{ 'is-valid': usernameValid, 'is-invalid': usernameErrors.length }"
      />
      <div v-if="usernameErrors.length" class="error-messages">
        <p v-for="error in usernameErrors" :key="error">{{ error }}</p>
      </div>
      <div v-else-if="usernameValid" class="success-message">
        ✓ 用户名可用
      </div>
    </div>
    
    <!-- 邮箱 -->
    <div class="form-group" :class="{ 'has-error': emailErrors.length }">
      <label>邮箱 *</label>
      <input 
        v-model="email" 
        @input="validateEmailField"
        @blur="validateEmailField"
        type="email"
        placeholder="example@domain.com"
        :class="{ 'is-valid': emailValid, 'is-invalid': emailErrors.length }"
      />
      <div v-if="emailErrors.length" class="error-messages">
        <p v-for="error in emailErrors" :key="error">{{ error }}</p>
      </div>
    </div>
    
    <!-- 密码 -->
    <div class="form-group" :class="{ 'has-error': passwordErrors.length }">
      <label>密码 *</label>
      <div class="password-input">
        <input 
          v-model="password" 
          @input="validatePasswordField"
          :type="showPassword ? 'text' : 'password'"
          placeholder="8-128个字符,包含大小写字母/数字/特殊字符"
          :class="{ 'is-invalid': passwordErrors.length }"
        />
        <button 
          type="button" 
          @click="showPassword = !showPassword"
          class="toggle-password"
        >
          {{ showPassword ? '隐藏' : '显示' }}
        </button>
      </div>
      
      <!-- 密码强度指示器 -->
      <div v-if="password" class="password-strength">
        <div class="strength-bar">
          <div 
            :class="['strength-fill', 'strength-' + passwordStrength]"
            :style="{ width: (passwordStrength / 5 * 100) + '%' }"
          ></div>
        </div>
        <span :class="'strength-text-' + passwordStrength">
          {{ passwordStrengthText }}
        </span>
      </div>
      
      <div v-if="passwordErrors.length" class="error-messages">
        <p v-for="error in passwordErrors" :key="error">{{ error }}</p>
      </div>
      
      <!-- 密码要求提示 -->
      <div class="password-requirements">
        <p :class="{ 'met': password.length >= 8 }">✓ 至少8个字符</p>
        <p :class="{ 'met': /[A-Z]/.test(password) }">✓ 包含大写字母</p>
        <p :class="{ 'met': /[a-z]/.test(password) }">✓ 包含小写字母</p>
        <p :class="{ 'met': /\d/.test(password) }">✓ 包含数字</p>
        <p :class="{ 'met': /[!@#$%^&*()_+]/.test(password) }">✓ 包含特殊字符</p>
      </div>
    </div>
    
    <!-- 提交按钮 -->
    <button 
      @click="handleRegister" 
      :disabled="!canSubmit || isSubmitting"
      class="submit-button"
    >
      {{ isSubmitting ? '注册中...' : '注册' }}
    </button>
    
    <!-- 错误提示 -->
    <div v-if="submitError" class="submit-error">
      {{ submitError }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { validateUsername, validatePassword, validateEmail } from './validators';

const username = ref('');
const email = ref('');
const password = ref('');
const showPassword = ref(false);

const usernameErrors = ref([]);
const emailErrors = ref([]);
const passwordErrors = ref([]);
const passwordStrength = ref(0);
const passwordStrengthText = ref('');

const usernameValid = ref(false);
const emailValid = ref(false);

const isSubmitting = ref(false);
const submitError = ref('');

// 验证方法
const validateUsernameField = () => {
  const result = validateUsername(username.value);
  usernameErrors.value = result.errors;
  usernameValid.value = result.valid;
  username.value = result.value;
};

const validateEmailField = () => {
  const result = validateEmail(email.value);
  emailErrors.value = result.errors;
  emailValid.value = result.valid;
  email.value = result.value;
};

const validatePasswordField = () => {
  const result = validatePassword(password.value);
  passwordErrors.value = result.errors;
  passwordStrength.value = result.strength;
  passwordStrengthText.value = result.strengthText;
};

// 是否可以提交
const canSubmit = computed(() => {
  return usernameValid.value && 
         emailValid.value && 
         passwordErrors.value.length === 0 &&
         password.value.length >= 8;
});

// 注册处理
const handleRegister = async () => {
  if (!canSubmit.value) return;
  
  isSubmitting.value = true;
  submitError.value = '';
  
  try {
    const response = await fetch('/api/v2/users/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: username.value,
        email: email.value,
        password: password.value,
      }),
    });
    
    const data = await response.json();
    
    if (response.ok) {
      // 注册成功
      alert('注册成功!');
      // 跳转到登录页或自动登录
    } else {
      // 处理错误
      if (data.detail?.error === 'username_exists') {
        usernameErrors.value = ['该用户名已被注册'];
      } else if (data.detail?.error === 'email_exists') {
        emailErrors.value = ['该邮箱已被注册'];
      } else if (data.detail?.error === 'validation_error') {
        submitError.value = '输入数据验证失败,请检查表单';
      } else {
        submitError.value = data.detail?.message || '注册失败,请稍后重试';
      }
    }
  } catch (error) {
    submitError.value = '网络错误,请检查网络连接';
  } finally {
    isSubmitting.value = false;
  }
};
</script>

<style scoped>
/* 样式省略,请根据实际项目调整 */
.form-group { margin-bottom: 20px; }
.error-messages { color: #ff4444; font-size: 12px; }
.success-message { color: #00aa00; font-size: 12px; }
.password-strength { margin-top: 8px; }
.strength-bar { height: 4px; background: #eee; border-radius: 2px; }
.strength-fill { height: 100%; transition: all 0.3s; }
.strength-0, .strength-1 { background: #ff4444; }
.strength-2 { background: #ff8800; }
.strength-3 { background: #ffcc00; }
.strength-4 { background: #88cc00; }
.strength-5 { background: #00aa00; }
.password-requirements p { font-size: 12px; color: #999; }
.password-requirements p.met { color: #00aa00; }
</style>
`;


// ==================== 3. React 组件示例 ====================

export const RegisterFormReact = `
import React, { useState, useMemo } from 'react';
import { validateUsername, validatePassword, validateEmail } from './validators';

export const RegisterForm = () => {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  
  const [usernameErrors, setUsernameErrors] = useState([]);
  const [emailErrors, setEmailErrors] = useState([]);
  const [passwordErrors, setPasswordErrors] = useState([]);
  
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');
  
  // 验证处理
  const handleUsernameChange = (e) => {
    const value = e.target.value;
    setUsername(value);
    const result = validateUsername(value);
    setUsernameErrors(result.errors);
  };
  
  const handleEmailChange = (e) => {
    const value = e.target.value;
    setEmail(value);
    const result = validateEmail(value);
    setEmailErrors(result.errors);
  };
  
  const handlePasswordChange = (e) => {
    const value = e.target.value;
    setPassword(value);
    const result = validatePassword(value);
    setPasswordErrors(result.errors);
  };
  
  // 密码强度
  const passwordStrength = useMemo(() => {
    return validatePassword(password);
  }, [password]);
  
  // 是否可提交
  const canSubmit = useMemo(() => {
    return usernameErrors.length === 0 && 
           emailErrors.length === 0 && 
           passwordErrors.length === 0 &&
           username && email && password;
  }, [usernameErrors, emailErrors, passwordErrors, username, email, password]);
  
  // 注册处理
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    
    setIsSubmitting(true);
    setSubmitError('');
    
    try {
      const response = await fetch('/api/v2/users/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password }),
      });
      
      const data = await response.json();
      
      if (response.ok) {
        alert('注册成功!');
      } else {
        if (data.detail?.error === 'username_exists') {
          setUsernameErrors(['该用户名已被注册']);
        } else if (data.detail?.error === 'email_exists') {
          setEmailErrors(['该邮箱已被注册']);
        } else {
          setSubmitError(data.detail?.message || '注册失败');
        }
      }
    } catch (error) {
      setSubmitError('网络错误');
    } finally {
      setIsSubmitting(false);
    }
  };
  
  return (
    <form onSubmit={handleSubmit} className="register-form">
      <h2>用户注册</h2>
      
      {/* 用户名 */}
      <div className="form-group">
        <label>用户名 *</label>
        <input 
          value={username}
          onChange={handleUsernameChange}
          placeholder="3-50个字符"
        />
        {usernameErrors.map((error, i) => (
          <p key={i} className="error">{error}</p>
        ))}
      </div>
      
      {/* 邮箱 */}
      <div className="form-group">
        <label>邮箱 *</label>
        <input 
          type="email"
          value={email}
          onChange={handleEmailChange}
          placeholder="example@domain.com"
        />
        {emailErrors.map((error, i) => (
          <p key={i} className="error">{error}</p>
        ))}
      </div>
      
      {/* 密码 */}
      <div className="form-group">
        <label>密码 *</label>
        <div className="password-input">
          <input 
            type={showPassword ? 'text' : 'password'}
            value={password}
            onChange={handlePasswordChange}
            placeholder="8-128个字符"
          />
          <button 
            type="button"
            onClick={() => setShowPassword(!showPassword)}
          >
            {showPassword ? '隐藏' : '显示'}
          </button>
        </div>
        
        {password && (
          <div className="password-strength">
            <div className={\`strength-bar strength-\${passwordStrength.strength}\`}>
              <div style={{ width: \`\${passwordStrength.strength / 5 * 100}%\` }} />
            </div>
            <span>{passwordStrength.strengthText}</span>
          </div>
        )}
        
        {passwordErrors.map((error, i) => (
          <p key={i} className="error">{error}</p>
        ))}
      </div>
      
      {/* 提交按钮 */}
      <button 
        type="submit" 
        disabled={!canSubmit || isSubmitting}
      >
        {isSubmitting ? '注册中...' : '注册'}
      </button>
      
      {submitError && <p className="submit-error">{submitError}</p>}
    </form>
  );
};
`;

console.log('前端集成示例已创建');
console.log('- Vue 3 组件: RegisterFormVue');
console.log('- React 组件: RegisterFormReact');
console.log('- 验证函数: validateUsername, validatePassword, validateEmail');
