#!/usr/bin/env python3
"""
服务器端错误上报脚本（安全增强版）
职责：收集错误日志和相关代码，脱敏后通过 GitHub API 创建 Issue
"""
import os
import sys
import glob
import requests
import re
from datetime import datetime

# ==================== 配置区 ====================
GITHUB_TOKEN = os.getenv("PERSONAL_ACCESS_TOKEN")
REPO = "emonet1/index"  # 请确认仓库名正确

PROJECTS = {
    "pocketbase": ["/home/pb/pb_hooks", "/home/pb/error.log", ".js"],
    "ai-proxy":   ["/home/ai-proxy", "/home/ai-proxy/error.log", ".py"],
    "websocket":  ["/home/websocket-server", "/home/websocket-server/error.log", ".js"]
}
# ================================================

class LogSanitizer:
    """内置日志脱敏器，确保不依赖外部文件"""
    
    @staticmethod
    def sanitize(text):
        if not text: return ""
        # 1. 邮箱
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.com', text)
        # 2. IP地址
        text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '*.*.*.*', text)
        # 3. 各种Token (sk-, pk-, ghp_)
        text = re.sub(r'(?:sk-|pk-|ghp_|gho_|ssh-rsa)[A-Za-z0-9_+\-=]{20,}', '***SECRET_REDACTED***', text)
        # 4. 密码字段
        text = re.sub(r'(?i)(password|passwd|pwd|secret)["\']?\s*[:=]\s*["\']?([^"\'\s]+)', r'\1=***', text)
        return text

def collect_and_report(service):
    """收集信息并上报"""
    if service not in PROJECTS:
        print(f"❌ 未知服务: {service}", flush=True)
        return

    code_dir, log_path, suffix = PROJECTS[service]
    print(f"📋 [{service}] 开始收集错误信息...", flush=True)

    # 1. 读取日志
    if not os.path.exists(log_path):
        print(f"❌ 日志不存在: {log_path}", flush=True)
        return

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            # 读取最后 50 行
            lines = f.readlines()[-50:]
            raw_content = "".join(lines)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}", flush=True)
        return

    # 2. 关键：脱敏处理
    safe_log = LogSanitizer.sanitize(raw_content)
    
    # 忽略无内容或过短的日志
    if len(safe_log) < 10:
        print("💡 日志内容为空，跳过", flush=True)
        return

    # 3. 读取相关代码（同样脱敏）
    files_section = ""
    code_files = glob.glob(os.path.join(code_dir, f"*{suffix}"))
    # 取最近修改的 2 个文件
    code_files.sort(key=os.path.getmtime, reverse=True)
    
    for fpath in code_files[:2]:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # 代码也要脱敏，防止硬编码的密钥泄露
                safe_code = LogSanitizer.sanitize(content)
                # 截断过长的代码
                if len(safe_code) > 2000:
                    safe_code = safe_code[:2000] + "\n... (截断) ..."
                
                fname = os.path.basename(fpath)
                ext = suffix.replace(".", "")
                files_section += f"\n#### `{fname}`\n```{ext}\n{safe_code}\n```\n"
        except Exception:
            pass

    # 4. 检查 Token
    if not GITHUB_TOKEN:
        print("❌ 缺少环境变量 PERSONAL_ACCESS_TOKEN", flush=True)
        return

    # 5. 构建 Issue
    title = f"[AUTO-FIX] {service} 服务异常报告 {datetime.now().strftime('%m/%d %H:%M')}"
    body = f"""
## 🚨 服务异常自动报告
**服务**: `{service}`
**时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
**状态**: 🔒 已自动脱敏 (LogSanitizer Active)

### 📝 错误日志片段
