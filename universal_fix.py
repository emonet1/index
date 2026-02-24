#!/usr/bin/env python3
"""
服务器端错误上报脚本（重构版）
职责：收集错误日志和相关代码，通过 GitHub API 创建 Issue
真正的修复由 GitHub Actions (auto-fix.yml) 负责
不再直接修改任何生产代码，不再直接 git push！
"""
import os
import sys
import glob
import requests
from datetime import datetime

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

    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        errors = "".join(f.readlines()[-50:])

    # 忽略 PocketBase 正常启动日志
    if service == "pocketbase" and "PocketBase v" in errors and "started" in errors:
        print("💡 忽略 PocketBase 正常启动日志", flush=True)
        return

    # ---------- 第2步：收集相关代码文件（只读，不写）----------
    files = glob.glob(code_dir + "/*" + suffix)
    file_contents = {}
    for fpath in files[:3]:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                file_contents[os.path.basename(fpath)] = f.read()
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
        files_section += "\n#### `" + fname + "`\n```" + ext + "\n" + fcontent[:5000] + "\n```\n"

    # 构建完整正文（避免 f-string 嵌套三引号导致 SyntaxError）
    issue_body = (
        "## 🚨 服务异常自动报告\n\n"
        "**服务名称**: `" + service + "`\n"
        "**检测时间**: `" + now_str + "`\n\n"
        "### 📋 错误日志\n"
        "```\n"
        + errors[:3000] +
        "\n```\n\n"
        "### 📁 相关代码文件\n"
        + files_section +
        "\n---\n"
        "*此 Issue 由服务器 `universal_fix.py` 自动创建*\n"
        "*修复将由 GitHub Actions AI 智能体自动完成并创建 PR*\n"
    )

    # ---------- 第5步：调用 GitHub API 创建 Issue ----------
    url = "https://api.github.com/repos/" + REPO + "/issues"
    headers = {
        "Authorization": "token " + GITHUB_TOKEN,
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": "[AUTO-FIX] " + service + " - " + title_time + " 服务异常",
        "body": issue_body,
        "labels": ["auto-fix"]
    }

    try:
        resp = requests.post(url, headers=headers, json=data, timeout=30)
        resp.raise_for_status()
        issue_url = resp.json()["html_url"]
        print("✅ 已创建 GitHub Issue: " + issue_url, flush=True)
        print("⏳ 等待 GitHub Actions AI 自动修复...", flush=True)
    except Exception as e:
        print("❌ 创建 Issue 失败: " + str(e), flush=True)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        collect_and_report(sys.argv[1])
    else:
        print("用法: python3 /home/universal_fix.py <服务名>")
        print("服务名可选: pocketbase, ai-proxy, websocket")
