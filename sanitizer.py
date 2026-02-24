import re

class LogSanitizer:
    """日志脱敏处理器 - 自动隐藏敏感信息"""
    
    PATTERNS = {
        'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'ip': r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        'api_key': r'\b(?:sk-|pk-|token-)[A-Za-z0-9]{20,}\b',
        'password': r'(?i)(password|passwd|pwd)["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
        'jwt': r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
        'phone': r'\b1[3-9]\d{9}\b',
        'id_card': r'\b\d{17}[\dXx]\b',
        'path': r'(/home/[a-z0-9_-]+|/root|C:\\Users\\[^\\]+)',
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
            lambda m: m.group(0)[:6] + "***" + m.group(0)[-4:],
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


# 测试代码
if __name__ == "__main__":
    test_log = """
    [ERROR] email=test@gmail.com, ip=192.168.1.100
    [ERROR] API Key: sk-86c77a39ce87413f8502d80e02408779
    [ERROR] password="secret123"
    """
    print("脱敏测试:")
    print(LogSanitizer.sanitize(test_log))
