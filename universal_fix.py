import os
import sys
import requests
import json
import glob
import subprocess
from datetime import datetime

# ================= 配置区 =================
# 确保在 Supervisor 的 environment 中设置了 AI_API_KEY
API_KEY = os.getenv("AI_API_KEY")
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 仓库根目录
REPO_PATH = "/home"

# Git 身份配置
GIT_USER_EMAIL = "ErnstGabona148@gmail.com"
GIT_USER_NAME = "emonet1"

# 项目配置图：[代码目录, 错误日志路径, 文件后缀]
PROJECTS = {
    "pocketbase": ["/home/pb/pb_hooks", "/home/pb/error.log", ".js"],
    "ai-proxy": ["/home/ai-proxy", "/home/ai-proxy/error.log", ".py"],
    "websocket": ["/home/websocket-server", "/home/websocket-server/error.log", ".js"]
}
# ==========================================

def clean_ai_code(text):
    """移除 AI 返回内容中的 Markdown 代码块标签"""
    lines = text.split('\n')
    new_lines = []
    for line in lines:
        strip_line = line.strip()
        if not (strip_line.startswith("```") or strip_line.endswith("```")):
            new_lines.append(line)
    return "\n".join(new_lines).strip()

def sync_github(service):
    """强力同步逻辑：确保在 Supervisor 环境下也能正确 PUSH"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"📤 启动 GitHub 同步流程...")
    
    try:
        # 强制注入 HOME 变量，确保 Git 能找到 Token
        env_vars = os.environ.copy()
        env_vars["HOME"] = "/root"

        # 1. 强制身份配置
        subprocess.run(["git", "config", "user.email", GIT_USER_EMAIL], cwd=REPO_PATH, check=True, env=env_vars)
        subprocess.run(["git", "config", "user.name", GIT_USER_NAME], cwd=REPO_PATH, check=True, env=env_vars)

        # 2. Add
        subprocess.run(["git", "add", "."], cwd=REPO_PATH, check=True, env=env_vars)
        
        # 3. Commit (必须带时间戳，确保记录更新)
        commit_msg = f"AI Auto-fix [{service}]: {now}"
        subprocess.run(["git", "commit", "--allow-empty", "-m", commit_msg], cwd=REPO_PATH, check=True, env=env_vars)
        
        # 4. Push (明确指定远程和分支)
        result = subprocess.run(
            ["git", "push", "origin", "main"], 
            cwd=REPO_PATH, check=True, capture_output=True, text=True, env=env_vars
        )
        
        print(f"✅ GitHub 同步成功！")
        if result.stdout: print(f"🚀 Git 输出: {result.stdout.strip()}")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Git 同步失败！")
        print(f"  - 错误指令: {' '.join(e.cmd)}")
        print(f"  - 详细报错: {e.stderr.strip() if e.stderr else '未知错误'}")
        return False

def run_fix(service):
    if service not in PROJECTS:
        print(f"❌ 未知服务名: {service}")
        return
    
    code_dir, log_path, suffix = PROJECTS[service]
    print(f"\n" + "="*40)
    print(f"🛠 医生脚本收到求助信号: {service}")
    print(f"⏰ 时间: {datetime.now().strftime('%H:%M:%S')}")
    
    # 1. 读取最新的报错日志
    if not os.path.exists(log_path):
        print(f"❌ 找不到日志文件: {log_path}")
        return
    with open(log_path, "r") as f:
        errors = "".join(f.readlines()[-30:]) # 读取末尾30行

    # ========== 核心智能判断：忽略正常重启日志 ==========
    # 如果日志里有 PocketBase 启动成功的关键词，且没有明显的错误，则忽略
    if service == "pocketbase" and ("PocketBase v" in errors and "started" in errors and len(errors.split('\n')) < 5):
        print("💡 忽略：日志仅包含 PocketBase 正常启动信息，不触发 AI 修复。")
        return
    # =======================================================
    
    # 2. 寻找该服务下最近修改的代码文件
    files = glob.glob(f"{code_dir}/*{suffix}")
    if not files:
        print(f"❌ 在 {code_dir} 下没找到 {suffix} 代码文件")
        return
    target_file = max(files, key=os.path.getmtime)
    print(f"🔍 锁定待修复文件: {target_file}")

    with open(target_file, "r") as f:
        old_code = f.read()

    # 3. 请求 AI 修复
    print(f"📝 正在向 AI 发送修复请求...")
    prompt = f"""
    你是代码修复专家。该项目是 {service}。
    【报错日志】：
    {errors}
    
    【当前源代码】：
    {old_code}
    
    请直接返回修复后的完整代码，不要包含任何解释、不要 Markdown 格式。
    """
    
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "qwen-plus",
        "messages": [{"role": "user", "content": prompt}]
    }
    
    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=40)
        res.raise_for_status()
        full_res = res.json()
        raw_ai_code = full_res['choices'][0]['message']['content']
        fixed_code = clean_ai_code(raw_ai_code)
        
        # 4. 写入修复代码
        with open(target_file, "w") as f:
            f.write(fixed_code)
        print(f"✅ AI 修复完成，已写入文件")

        # 5. 同步至 GitHub
        sync_github(service)

        # 6. 重启受损服务
        print(f"🔄 正在重启服务: {service}...")
        subprocess.run(["supervisorctl", "restart", service], check=True)
        print(f"✨ {service} 流程全部结束，系统已恢复健康！")

    except Exception as e:
        print(f"❌ 运行过程中发生严重错误: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_fix(sys.argv[1])
    else:
        print("💡 请传入要修复的服务名，例如: python3 universal_fix.py pocketbase")