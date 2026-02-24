import re

class LogSanitizer:
    """日志脱敏处理器 - 自动隐藏敏感信息"""
    
    PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'ip': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        'api_key': r'\b(?:sk-|pk-|token-|ghp_|gho_)[A-Za-z0-9_-]{20,}\b',  # ✅ 扩展支持 GitHub token
        'password': r'(?i)(password|passwd|pwd|secret|api_key|token)["\']?\s*[:=]\s*["\']?([^"\'\s]{3,})',
        'jwt': r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
        'phone': r'\b1[3-9]\d{9}\b',
        'id_card': r'\b\d{17}[\dXx]\b',
        'path': r'(/home/[a-z0-9_-]+|/root|C:\\Users\\[^\\]+)',
        # ✅ 新增: 数据库连接串
        'db_connection': r'(?i)(mongodb|mysql|postgresql|redis)://[^\s]+',
        # ✅ 新增: AWS/云服务密钥
        'aws_key': r'(?i)(AKIA|ASIA)[A-Z0-9]{16}',
    }
    
    @classmethod
    def sanitize(cls, log_text):
        """对日志进行脱敏处理"""
        if not log_text:
            return log_text
            
        sanitized = log_text
        
        # 脱敏邮箱
        sanitized = re.sub(
            cls.PATTERNS['email'],
            lambda m: cls._mask_email(m.group(0)),
            sanitized
        )
        
        # 脱敏 IP
        sanitized = re.sub(
            cls.PATTERNS['ip'],
            lambda m: cls._mask_ip(m.group(0)),
            sanitized
        )
        
        # 脱敏 API 密钥
        sanitized = re.sub(
            cls.PATTERNS['api_key'],
            lambda m: m.group(0)[:6] + "***" + m.group(0)[-4:] if len(m.group(0)) > 10 else "***REDACTED***",
            sanitized
        )
        
        # 脱敏密码
        sanitized = re.sub(
            cls.PATTERNS['password'],
            r'\1=***REDACTED***',
            sanitized
        )
        
        # 脱敏 JWT
        sanitized = re.sub(
            cls.PATTERNS['jwt'],
            'eyJ***REDACTED***',
            sanitized
        )
        
        # 脱敏手机号
        sanitized = re.sub(
            cls.PATTERNS['phone'],
            lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:],
            sanitized
        )
        
        # 脱敏身份证
        sanitized = re.sub(
            cls.PATTERNS['id_card'],
            lambda m: m.group(0)[:6] + "********" + m.group(0)[-4:],
            sanitized
        )
        
        # 脱敏路径
        sanitized = re.sub(
            cls.PATTERNS['path'],
            '/***/',
            sanitized
        )
        
        # ✅ 脱敏数据库连接串
        sanitized = re.sub(
            cls.PATTERNS['db_connection'],
            lambda m: m.group(1) + '://***REDACTED***',
            sanitized
        )
        
        # ✅ 脱敏 AWS 密钥
        sanitized = re.sub(
            cls.PATTERNS['aws_key'],
            '***AWS_KEY_REDACTED***',
            sanitized
        )
        
        return sanitized
    
    @staticmethod
    def _mask_email(email):
        """邮箱脱敏：保留首尾字符"""
        try:
            username, domain = email.split('@')
            if len(username) <= 2:
                return f"***@{domain}"
            return f"{username[0]}***{username[-1]}@{domain}"
        except:
            return "***@***.com"
    
    @staticmethod
    def _mask_ip(ip):
        """IP 地址脱敏：只保留前两段"""
        try:
            parts = ip.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.*.*"
            return "***.*.*.*"
        except:
            return "***.*.*.*"
    
    @classmethod
    def validate(cls, text):
        """✅ 新增: 验证文本是否仍包含敏感信息"""
        sensitive_patterns = [
            (r'sk-[a-zA-Z0-9]{20,}', 'API密钥'),
            (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Token'),
            (r'\b\d{17}[\dXx]\b', '身份证号'),
            (r'(?:\d{1,3}\.){3}\d{1,3}', 'IP地址'),
            (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '邮箱地址'),
        ]
        
        found_issues = []
        for pattern, name in sensitive_patterns:
            matches = re.findall(pattern, text)
            if matches:
                found_issues.append(f"{name}: 发现 {len(matches)} 处")
        
        return found_issues


# 测试代码
if __name__ == "__main__":
    test_log = """
    [ERROR] email=test@gmail.com, ip=192.168.1.100
    [ERROR] API Key: sk-86c77a39ce87413f8502d80e02408779
    [ERROR] password="secret123"
    [ERROR] GitHub Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz
    [ERROR] Database: mongodb://user:pass@localhost:27017/db
    """
    print("="*60)
    print("脱敏测试:")
    print("="*60)
    print("\n【原始日志】:")
    print(test_log)
    
    sanitized = LogSanitizer.sanitize(test_log)
    print("\n【脱敏后日志】:")
    print(sanitized)
    
    # 验证
    issues = LogSanitizer.validate(sanitized)
    print("\n【验证结果】:")
    if issues:
        print("❌ 仍存在敏感信息:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ 未检测到敏感信息")
