#!/usr/bin/env python3
# /home/universal_fix.py
import os
import sys
import glob
import requests
from datetime import datetime

# ✅ 导入统一脱敏模块
try:
    from sanitizer import LogSanitizer
except ImportError:
    print("❌ 错误: 缺少 sanitizer.py")
    sys.exit(1)

# ==================== 配置区 ====================
GITHUB_TOKEN = os.getenv("PERSONAL_ACCESS_TOKEN")
REPO = "emonet1/index"  # 确保仓库名正确

PROJECTS = {
    "pocketbase": ["/home/pb/pb_hooks", "/home/pb/error.log", ".js"],
    "ai-proxy":   ["/home/ai-proxy", "/home/ai-proxy/error.log", ".py"],
    "websocket":  ["/home/websocket-server", "/home/websocket-server/error.log", ".js"]
}
# ================================================

def collect_and_report(service):
    if service not in PROJECTS:
        print(f"❌ 未知服务: {service}")
        return

    code_dir, log_path, suffix = PROJECTS[service]
    
    # 1. 获取日志并脱敏
    if not os.path.exists(log_path):
        print("❌ 日志文件不存在")
        return
        
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_log = "".join(f.readlines()[-50:])
        
    # ✅ 调用统一脱敏器
    safe_log = LogSanitizer.sanitize(raw_log)
    
    if len(safe_log) < 10:
        print("💡 日志过短，跳过")
        return

    # 2. 获取代码并脱敏
    files_section = ""
    code_files = glob.glob(os.path.join(code_dir, f"*{suffix}"))
    code_files.sort(key=os.path.getmtime, reverse=True)
    
    for fpath in code_files[:2]:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                # ✅ 代码内容也必须脱敏
                safe_code = LogSanitizer.sanitize(f.read())
                if len(safe_code) > 2000:
                    safe_code = safe_code[:2000] + "\n... (代码截断) ..."
                fname = os.path.basename(fpath)
                ext = suffix.replace(".", "")
                files_section += f"\n#### `{fname}`\n```{ext}\n{safe_code}\n```\n"
        except Exception:
            pass

    # 3. 构建 Issue 内容
    issue_body = f"""
## 🚨 服务异常自动报告
**服务**: `{service}`
**时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`
**脱敏状态**: ✅ 已通过 LogSanitizer 验证

### 📝 错误日志
