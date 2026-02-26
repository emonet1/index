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
REPO = "emonet1/index"

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
        if not text:
            return ""
        
        # 1. 邮箱
        text = re.sub(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            '***@***.com',
            text
        )
        
        # 2. IP地址
        text = re.sub(
            r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
            '*.*.*.*',
            text
        )
        
        # 3. 各种Token (sk-, pk-, ghp_)
        text = re.sub(
            r'(?:sk-|pk-|ghp_|gho_|ssh-rsa)[A-Za-z0-9_+\-=]{20,}',
            '***SECRET_REDACTED***',
            text
        )
        
        # 4. 密码字段
        text = re.sub(
            r'(?i)(password|passwd|pwd|secret)["\']?\s*[:=]\s*["\']?([^"\'\s]+)',
            r'\1=***',
            text
        )
        
        # 5. JWT Token
        text = re.sub(
            r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
            'eyJ***REDACTED***',
            text
        )
        
        # 6. 手机号
        text = re.sub(
            r'\b1[3-9]\d{9}\b',
            lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:],
            text
        )
        
        # 7. 身份证号
        text = re.sub(
            r'\b\d{17}[\dXx]\b',
            lambda m: m.group(0)[:6] + "********" + m.group(0)[-4:],
            text
        )
        
        return text
    
    @staticmethod
    def validate(text):
        """验证是否还有敏感信息"""
        sensitive_patterns = [
            (r'sk-[a-zA-Z0-9]{20,}', 'API密钥'),
            (r'ghp_[a-zA-Z0-9]{36}', 'GitHub Token'),
            (r'\b\d{17}[\dXx]\b', '身份证号'),
        ]
        
        found_issues = []
        for pattern, name in sensitive_patterns:
            if re.search(pattern, text):
                found_issues.append(name)
        
        return found_issues


def collect_and_report(service):
    """收集信息并上报到 GitHub Issue"""
    
    # ✅ 修复：提前检查环境变量，避免无效处理
    if not GITHUB_TOKEN:
        print("❌ 缺少环境变量 PERSONAL_ACCESS_TOKEN，跳过上报", flush=True)
        return
    
    if service not in PROJECTS:
        print(f"❌ 未知服务: {service}", flush=True)
        return

    code_dir, log_path, suffix = PROJECTS[service]
    print(f"📋 [{service}] 开始收集错误信息...", flush=True)

    # ========== 第1步：读取日志 ==========
    if not os.path.exists(log_path):
        print(f"❌ 日志不存在: {log_path}", flush=True)
        return

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[-50:]
            raw_content = "".join(lines)
    except Exception as e:
        print(f"❌ 读取文件失败: {e}", flush=True)
        return

    # ========== 第2步：脱敏处理 ==========
    safe_log = LogSanitizer.sanitize(raw_content)
    
    if len(safe_log) < 10:
        print("💡 日志内容为空，跳过", flush=True)
        return

    # ========== 第3步：读取相关代码 ==========
    files_section = ""
    code_files = glob.glob(os.path.join(code_dir, f"*{suffix}"))
    code_files.sort(key=os.path.getmtime, reverse=True)
    
    for fpath in code_files[:2]:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                safe_code = LogSanitizer.sanitize(content)
                
                if len(safe_code) > 2000:
                    safe_code = safe_code[:2000] + "\n... (代码截断) ..."
                
                fname = os.path.basename(fpath)
                ext = suffix.replace(".", "")
                files_section += f"\n#### `{fname}`\n```{ext}\n{safe_code}\n```\n"
        except Exception as e:
            print(f"⚠️ 读取代码文件失败: {e}", flush=True)
            pass

    # ========== 第4步：构建 Issue 内容 ==========
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    title_time = datetime.now().strftime('%m/%d %H:%M')
    title = f"[AUTO-FIX] {service} - {title_time} 服务异常"
    
    # 使用多行字符串构建 issue_body（注意正确的语法）
    issue_body = (
        "## 🚨 服务异常自动报告\n"
        f"**服务**: `{service}`\n"
        f"**时间**: `{time_str}`\n"
        "**脱敏状态**: ✅ 已通过 LogSanitizer 验证\n\n"
        "### 📋 错误日志（已脱敏）\n"
        "```\n"
        + safe_log[:3000] +
        "\n```\n\n"
        "### 📁 相关代码文件（已脱敏）\n"
        + files_section +
        "\n---\n"
        "*此 Issue 由服务器 `universal_fix.py` 自动创建*\n"
        "*修复将由 GitHub Actions AI 智能体自动完成并创建 PR*\n"
        "*⚠️ 日志已自动脱敏，不包含真实敏感信息*\n"
    )
    
    # ========== 第5步：二次验证脱敏 ==========
    validation_issues = LogSanitizer.validate(issue_body)
    if validation_issues:
        print("❌ 检测到可能的敏感信息泄漏，终止上报！", flush=True)
        for issue in validation_issues:
            print(f"  - {issue}", flush=True)
        return

    # ========== 第6步：调用 GitHub API ==========
    url = f"https://api.github.com/repos/{REPO}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    }
    data = {
        "title": title,
        "body": issue_body,
        "labels": ["auto-fix", "security-sanitized"]
    }

    try:
        print("📤 正在创建 GitHub Issue...", flush=True)
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        
        result = resp.json()
        issue_url = result.get("html_url", "")
        issue_number = result.get("number", "")
        
        print(f"✅ 已创建 GitHub Issue: {issue_url}", flush=True)
        print(f"   Issue 编号: #{issue_number}", flush=True)
        print("🔒 敏感信息已自动脱敏，可安全公开", flush=True)
        print("⏳ 等待 GitHub Actions AI 自动修复...", flush=True)
        
    except requests.exceptions.Timeout:
        print("❌ 创建 Issue 超时（30秒）", flush=True)
        
    except requests.exceptions.HTTPError as e:
        print(f"❌ GitHub API 错误: {str(e)}", flush=True)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
                print(f"   错误详情: {error_detail.get('message', 'Unknown')}", flush=True)
            except:
                print(f"   HTTP 状态码: {e.response.status_code}", flush=True)
                
    except Exception as e:
        print(f"❌ 创建 Issue 失败: {str(e)}", flush=True)


if __name__ == "__main__":
    print("=" * 60, flush=True)
    print("🚀 Universal Fix 脚本启动", flush=True)
    print("🔒 已启用日志脱敏功能", flush=True)
    print("=" * 60, flush=True)
    
    if len(sys.argv) > 1:
        service_name = sys.argv[1]
        print(f"目标服务: {service_name}", flush=True)
        collect_and_report(service_name)
    else:
        print("❌ 错误: 缺少服务名参数", flush=True)
        print("用法: python3 /home/universal_fix.py <服务名>", flush=True)
        print(f"服务名可选: {', '.join(PROJECTS.keys())}", flush=True)
        sys.exit(1)
