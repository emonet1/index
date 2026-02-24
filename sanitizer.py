# /home/sanitizer.py
import re

class LogSanitizer:
    """
    统一日志脱敏处理器 (增强版)
    ✅ 包含: PII (邮箱/IP/手机), 凭证 (API Key/AWS/JWT), Web传输 (URL/Cookie/Auth)
    """

    PATTERNS = {
        # === 1. 基础个人信息 (PII) ===
        'email':     r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'ip':        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        'phone':     r'\b1[3-9]\d{9}\b',
        'id_card':   r'\b\d{17}[\dXx]\b',
        'path':      r'(/home/[a-z0-9_-]+|/root|C:\\Users\\[^\\]+)',

        # === 2. 核心凭证 (Keys & Secrets) ===
        'api_key':   r'\b(?:sk-|pk-|token-|ghp_|gho_|ssh-rsa)[A-Za-z0-9_+\-=]{20,}\b',
        'jwt':       r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
        'aws_key':   r'(?i)(AKIA|ASIA)[A-Z0-9]{16}',
        'private_key': r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----.*?-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----',
        
        # === 3. 基础设施连接 ===
        'db_connection': r'(?i)(mongodb|mysql|postgresql|redis)://[^\s]+',

        # === 4. Web 传输敏感数据 (本次增强) ===
        # URL 参数中的 token/key (例如: ?token=abcde...)
        'url_params': r'(?i)[?&](token|key|secret|password|pwd|api_key|access_token)=([^&\s]+)',
        # Basic/Bearer 认证头
        'basic_auth': r'Basic\s+[A-Za-z0-9+/]+=*',
        'bearer_token': r'Bearer\s+[A-Za-z0-9_\-\.]+',
        # Cookie 会话
        'cookie':    r'(?i)(sessionid|session|jsessionid|phpsessid|connect\.sid)=([^;\s]+)',
        # JSON/Form 字段中的密码
        'password_field': r'(?i)(password|passwd|pwd|secret)["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
    }

    @classmethod
    def sanitize(cls, text):
        """执行全量脱敏"""
        if not text:
            return ""
        
        s = text
        
        # --- 第一轮：特定格式脱敏 (优先处理长串) ---
        
        # 1. URL 参数 (?token=abc -> ?token=***)
        s = re.sub(cls.PATTERNS['url_params'], r'\1=***REDACTED***', s)
        
        # 2. 认证头
        s = re.sub(cls.PATTERNS['basic_auth'], 'Basic ***REDACTED***', s)
        s = re.sub(cls.PATTERNS['bearer_token'], 'Bearer ***REDACTED***', s)
        
        # 3. Cookie
        s = re.sub(cls.PATTERNS['cookie'], r'\1=***REDACTED***', s)
        
        # 4. 数据库连接串
        s = re.sub(cls.PATTERNS['db_connection'], r'\1://***DB_CREDS_REDACTED***', s)

        # --- 第二轮：通用凭证脱敏 ---
        
        s = re.sub(cls.PATTERNS['aws_key'], '***AWS_KEY_REDACTED***', s)
        s = re.sub(cls.PATTERNS['private_key'], '***PRIVATE_KEY_REDACTED***', s)
        s = re.sub(cls.PATTERNS['jwt'], 'eyJ***JWT_REDACTED***', s)
        s = re.sub(cls.PATTERNS['api_key'], '***API_KEY_REDACTED***', s)
        
        # --- 第三轮：字段与 PII 脱敏 ---
        
        # 密码字段
        s = re.sub(cls.PATTERNS['password_field'], r'\1=***PASS_REDACTED***', s)
        
        # 邮箱 (保留首尾)
        s = re.sub(cls.PATTERNS['email'], lambda m: cls._mask_email(m.group(0)), s)
        
        # IP (保留前两段)
        s = re.sub(cls.PATTERNS['ip'], lambda m: cls._mask_ip(m.group(0)), s)
        
        # 手机号/身份证
        s = re.sub(cls.PATTERNS['phone'], r'***PHONE***', s)
        s = re.sub(cls.PATTERNS['id_card'], r'***ID_CARD***', s)
        s = re.sub(cls.PATTERNS['path'], '/***/', s)

        return s

    @staticmethod
    def _mask_email(email):
        try:
            if '@' not in email: return email
            username, domain = email.split('@')
            if len(username) <= 2:
                return f"***@{domain}"
            return f"{username[0]}***{username[-1]}@{domain}"
        except:
            return "***@***.com"

    @staticmethod
    def _mask_ip(ip):
        try:
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.*.*"
            return "***.*.*.*"
        except:
            return "***.*.*.*"

    @classmethod
    def validate(cls, text):
        """
        二次验证：检查是否仍包含极其危险的敏感特征
        注意：不检查邮箱/IP，因为脱敏后的格式可能仍会被正则匹配，导致误报
        """
        issues = []
        # 检查高危 Key
        if re.search(r'sk-[a-zA-Z0-9]{20,}', text):
            issues.append("可能泄露 OpenAI Key")
        if re.search(r'ghp_[a-zA-Z0-9]{20,}', text):
            issues.append("可能泄露 GitHub Token")
        if re.search(r'(?i)(AKIA|ASIA)[A-Z0-9]{16}', text):
            issues.append("可能泄露 AWS Access Key")
        if re.search(r'-----BEGIN PRIVATE KEY-----', text):
            issues.append("可能泄露 RSA 私钥")
            
        return issues

# --- 本地测试块 (仅直接运行时执行) ---
if __name__ == "__main__":
    test_log = """
    [INFO] Request to http://api.com?token=abcdef123456&user=admin
    [INFO] Cookie: sessionid=xyz987654321; path=/
    [ERROR] DB Connection failed: postgresql://user:pass123@localhost:5432/db
    [ERROR] AWS Error: AccessDenied for AKIAIOSFODNN7EXAMPLE
    [ERROR] User test@example.com login failed from 192.168.1.1
    [DEBUG] Auth: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig
    """
    
    print("--- 原始日志 ---")
    print(test_log)
    print("\n--- 脱敏后日志 ---")
    sanitized = LogSanitizer.sanitize(test_log)
    print(sanitized)
    
    print("\n--- 安全验证 ---")
    issues = LogSanitizer.validate(sanitized)
    if issues:
        print("❌ 验证失败:", issues)
    else:
        print("✅ 验证通过: 未发现高危敏感信息")
