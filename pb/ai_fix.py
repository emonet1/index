import os
import requests
import json
import glob
import sys
import subprocess
from datetime import datetime

# ================= 配置区 =================
# 请确保你的环境变量中设置了 AI_API_KEY
API_KEY = os.getenv("AI_API_KEY")
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 路径配置
REPO_PATH = "/home/pb"
HOOKS_DIR = os.path.join(REPO_PATH, "pb_hooks")
ERROR_LOG = os.path.join(REPO_PATH, "error.log")

# Git 身份配置 (防止 Supervisor 环境下识别不到全局配置)
GIT_USER_EMAIL = "ErnstGabona148@gmail.com"
GIT_USER_NAME = "emonet1"
# ==========================================

def get_latest_error():
    """从日志中提取最新的错误信息"""
    if os.path.exists(ERROR_LOG):
        try:
            with open(ERROR_LOG, "r") as f:
                lines = f.readlines()
                # 提取最后20行，这通常包含了崩溃堆栈
                return "".join(lines[-20:])
        except Exception:
            return "Read error.log failed"
    return "No log found"

def clean_ai_code(text):
    """移除 AI 返回内容中的 Markdown 标签 (如 ```javascript)"""
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        if not line.strip().startswith("```"):
            new_lines.append(line)
    return "\n".join(new_lines).strip()

def run_git_sync():
    """强制在本地执行 Git 身份配置并同步到 GitHub"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"📤 正在启动 Git 同步... (记录时间: {now_str})")
    
    try:
        # 1. 在当前仓库环境下强制设置身份 (解决 status 128 核心逻辑)
        subprocess.run(["git", "config", "user.email", GIT_USER_EMAIL], cwd=REPO_PATH, check=True)
        subprocess.run(["git", "config", "user.name", GIT_USER_NAME], cwd=REPO_PATH, check=True)
        
        # 2. 认可当前目录为安全目录
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", REPO_PATH],
            capture_output=True, text=True
        )

        # 3. 添加更改
        subprocess.run(["git", "add", "."], cwd=REPO_PATH, check=True, capture_output=True)
        
        # 4. 提交更改 (使用 --allow-empty 确保即使代码内容一样，也会产生新提交记录)
        commit_msg = f"AI Auto-fix: {now_str}"
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", commit_msg], 
            cwd=REPO_PATH, check=True, capture_output=True, text=True
        )
        
        # 5. 推送到远程
        subprocess.run(
            ["git", "push", "origin", "main"], 
            cwd=REPO_PATH, check=True, capture_output=True, text=True
        )
        
        print(f"✅ GitHub 同步成功！最新提交: {commit_msg}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Git 操作失败！")
        print(f"  - 状态码: {e.returncode}")
        print(f"  - 错误详情: {e.stderr.strip() if e.stderr else '无详细输出'}")
        return False

def run_fix():
    print(f"\n" + "="*50)
    print(f"🚀 AI 自愈系统启动 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*50)
    
    if not API_KEY:
        print("❌ 错误: 未检测到环境变量 AI_API_KEY。")
        return

    # 1. 查找目标文件
    files = glob.glob(f"{HOOKS_DIR}/*.js")
    if not files:
        print(f"❌ 错误: 在 {HOOKS_DIR} 未找到代码文件。")
        return
    
    target_file = files[0]
    print(f"🔍 诊断文件: {target_file}")
    
    with open(target_file, "r") as f:
        old_code = f.read()

    # 2. 提取报错
    error_context = get_latest_error()
    print("📝 正在请求 AI 修复方案 (通义千问 qwen-plus)...")

    # 3. 构建 Prompt
    prompt = f"""
    你是 PocketBase 专家。修复以下代码中的语法或逻辑错误，确保它能正常运行。
    【报错日志】：
    {error_context}
    
    【源代码】：
    {old_code}
    
    要求：
    1. 直接输出修复后的完整 JS 代码。
    2. 不要包含解释文字，不要使用 ``` 这种 Markdown 代码块。
    """

    # 4. 调用通义千问 API
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "qwen-plus",
        "messages": [{"role": "user", "content": prompt}]
    }

    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=40)
        res.raise_for_status()
        raw_code = res.json()['choices'][0]['message']['content']
        fixed_code = clean_ai_code(raw_code)
        
        # 5. 写入修复后的代码
        with open(target_file, "w") as f:
            f.write(fixed_code)
        print("✅ AI 修复方案已写入文件")

        # 6. 同步到 GitHub
        run_git_sync()
        
        # 7. 重启 PocketBase 使代码生效
        print("🔄 正在通过 Supervisor 重启 PocketBase...")
        subprocess.run(["supervisorctl", "restart", "pocketbase"], check=True)
        print("✨ 自动化修复流程全部完成！")

    except Exception as e:
        print(f"❌ 运行过程中发生异常: {str(e)}")

if __name__ == "__main__":
    run_fix()