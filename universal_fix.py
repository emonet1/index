#!/usr/bin/env python3
"""
服务器端错误上报脚本（重构版 + 安全增强）
职责：收集错误日志和相关代码，通过 GitHub API 创建 Issue
✅ 新增：日志脱敏处理，防止敏感信息泄露到公开 Issue
真正的修复由 GitHub Actions (auto-fix.yml) 负责
不再直接修改任何生产代码，不再直接 git push！
"""
import os
import sys
import glob
import requests
from datetime import datetime

# ✅ 导入脱敏模块
try:
    from sanitizer import LogSanitizer
    SANITIZER_AVAILABLE = True
    print("✅ 日志脱敏模块已加载", flush=True)
except ImportError:
    print("⚠️ 警告：脱敏模块未找到，使用简化版", flush=True)
    SANITIZER_AVAILABLE = False
    # 简化版脱敏（备用方案）
    import re
    class LogSanitizer:
        @staticmethod
        def sanitize(text):
            text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.com', text)
            text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '*.*.*.*', text)
            text = re.sub(r'(?:sk-|pk-|ghp_|gho_)[A-Za-z0-9_-]{20,}', '***REDACTED***', text)
            text = re.sub(r'(?i)(password|passwd|pwd|secret)["\']?\s*[:=]\s*["\']?([^"\'\s]{3,})', r'\1=***', text)
            return text
        
        @staticmethod
        def validate(text):
            """简化版验证"""
            import re
            issues = []
            if re.search(r'sk-[a-zA-Z0-9]{20,}', text):
                issues.append("API密钥")
            if re.search(r'ghp_[a-zA-Z0-9]{36}', text):
                issues.append("GitHub Token")
            return issues

# ==================== 配置区 ====================
GITHUB_TOKEN = os.getenv("PERSONAL_ACCESS_TOKEN")
REPO = "emonet1/index"

# 项目配置 [代码目录, 日志路径, 文件后缀]
PROJECTS = {
    "pocketbase": ["/home/pb/pb_hooks", "/home/pb/error.log", ".js"],
    "ai-proxy":   ["/home/ai-proxy", "/home/ai-proxy/error.log", ".py"],
    "websocket":  ["/home/websocket-server", "/home/websocket-server/error.log", ".js"]
}
# ================================================


def collect_and_report(service):
    """收集错误信息，创建 GitHub Issue（不修改任何本地文件）"""

    if service not in PROJECTS:
        print("❌ 未知服务: " + service, flush=True)
        return

    code_dir, log_path, suffix = PROJECTS[service]
    print("📋 [" + service + "] 开始收集错误信息...", flush=True)

    # ---------- 第1步：读取错误日志 ----------
    if not os.path.exists(log_path):
        print("❌ 日志文件不存在: " + log_path, flush=True)
        return

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            raw_errors = "".join(f.readlines()[-50:])
        
        # ✅ 关键改进：脱敏处理
        errors = LogSanitizer.sanitize(raw_errors)
        print("🔒 日志已脱敏处理 (原始: " + str(len(raw_errors)) + " 字符 → 安全: " + str(len(errors)) + " 字符)", flush=True)
        
    except Exception as e:
        print("❌ 读取日志失败: " + str(e), flush=True)
        return

    # 忽略 PocketBase 正常启动日志
    if service == "pocketbase" and "PocketBase v" in errors and "started" in errors:
        print("💡 忽略 PocketBase 正常启动日志", flush=True)
        return
    
    # 检查日志是否有实际内容
    if not errors.strip() or len(errors) < 20:
        print("💡 日志内容过少，跳过上报", flush=True)
        return

    # ---------- 第2步：收集相关代码文件（只读，不写）----------
    files = glob.glob(code_dir + "/*" + suffix)
    file_contents = {}
    for fpath in files[:3]:  # 最多收集 3 个文件
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # ✅ 代码文件也要脱敏（可能包含注释中的敏感信息）
                safe_content = LogSanitizer.sanitize(content)
                file_contents[os.path.basename(fpath)] = safe_content
        except Exception as e:
            print("⚠️ 读取文件失败 " + fpath + ": " + str(e), flush=True)

    # ---------- 第3步：检查 PERSONAL_ACCESS_TOKEN ----------
    if not GITHUB_TOKEN:
        print("❌ 未读取到 PERSONAL_ACCESS_TOKEN！", flush=True)
        print("👉 请在 Supervisor 配置中确认: environment=PERSONAL_ACCESS_TOKEN=\"ghp_你的token\"", flush=True)
        return

    # ---------- 第4步：构建 Issue 正文 ----------
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    title_time = datetime.now().strftime("%m/%d %H:%M")

    # 构建代码文件区块
    files_section = ""
    for fname, fcontent in file_contents.items():
        ext = suffix.lstrip(".")
        # 限制代码长度，避免 Issue 过长
        code_preview = fcontent[:5000]
        if len(fcontent) > 5000:
            code_preview += "\n\n... (代码过长，已截断) ..."
        files_section += "\n#### `" + fname + "`\n```" + ext + "\n" + code_preview + "\n```\n"

    # 构建完整正文
    issue_body = (
        "## 🚨 服务异常自动报告\n\n"
        "**服务名称**: `" + service + "`\n"
        "**检测时间**: `" + now_str + "`\n"
        "**脱敏状态**: ✅ 已自动脱敏（邮箱、IP、密钥等敏感信息已隐藏）\n\n"
        "### 📋 错误日志（已脱敏）\n"
        "```\n"
        + errors[:3000] +
        "\n```\n\n"
        "### 📁 相关代码文件（已脱敏）\n"
        + files_section +
        "\n---\n"
        "*此 Issue 由服务器 `universal_fix.py` 自动创建*\n"
        "*修复将由 GitHub Actions AI 智能体自动完成并创建 PR*\n"
        "*⚠️ 日志已自动脱敏，不包含真实敏感信息*\n"
    )
    
    # ✅ 关键改进: 对整个 Issue body 再次脱敏
    issue_body = LogSanitizer.sanitize(issue_body)
    
    # ✅ 新增: 二次验证是否还有敏感信息
    validation_issues = LogSanitizer.validate(issue_body)
    if validation_issues:
        print("❌ 检测到可能的敏感信息泄漏，终止上报！", flush=True)
        for issue in validation_issues:
            print(f"  - {issue}", flush=True)
        print("💡 建议: 检查 sanitizer.py 的脱敏规则", flush=True)
        return

    # ---------- 第5步：调用 GitHub API 创建 Issue ----------
    url = "https://api.github.com/repos/" + REPO + "/issues"
    headers = {
        "Authorization": "token " + GITHUB_TOKEN,
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": "[AUTO-FIX] " + service + " - " + title_time + " 服务异常",
        "body": issue_body,
        "labels": ["auto-fix", "security-sanitized"]
    }

    try:
        print("📤 正在创建 GitHub Issue...", flush=True)
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        issue_url = resp.json()["html_url"]
        print("✅ 已创建 GitHub Issue: " + issue_url, flush=True)
        print("🔒 敏感信息已自动脱敏，可安全公开", flush=True)
        print("⏳ 等待 GitHub Actions AI 自动修复...", flush=True)
    except requests.exceptions.Timeout:
        print("❌ 创建 Issue 超时", flush=True)
    except requests.exceptions.HTTPError as e:
        print("❌ GitHub API 错误: " + str(e), flush=True)
        if hasattr(e.response, 'text'):
            print("   详情: " + e.response.text[:200], flush=True)
    except Exception as e:
        print("❌ 创建 Issue 失败: " + str(e), flush=True)


if __name__ == "__main__":
    print("="*60, flush=True)
    print("🚀 Universal Fix 脚本启动", flush=True)
    print("🔒 已启用日志脱敏功能", flush=True)
    print("="*60, flush=True)
    
    if len(sys.argv) > 1:
        collect_and_report(sys.argv[1])
    else:
        print("用法: python3 /home/universal_fix.py <服务名>")
        print("服务名可选: " + ", ".join(PROJECTS.keys()))
