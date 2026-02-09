import os
import sys
import requests
import glob
import subprocess
from datetime import datetime

# === 需要你在 Supervisor 环境变量里填好 AI_API_KEY ===
API_KEY = os.getenv("AI_API_KEY") 
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 项目配置 [目录, 日志, 后缀]
PROJECTS = {
    "pocketbase": ["/home/pb/pb_hooks", "/home/pb/error.log", ".js"],
    "ai-proxy": ["/home/ai-proxy", "/home/ai-proxy/error.log", ".py"],
    "websocket": ["/home/websocket-server", "/home/websocket-server/error.log", ".js"]
}

def clean_ai_code(text):
    lines = text.split('\n')
    return "\n".join([l for l in lines if not l.strip().startswith("```")])

def run_fix(service):
    if service not in PROJECTS: return
    code_dir, log_path, suffix = PROJECTS[service]
    
    print(f"🛠 开始修复: {service}")
    
    if not os.path.exists(log_path):
        print("❌ 没找到日志文件")
        return
    
    with open(log_path, "r") as f: errors = "".join(f.readlines()[-30:])
    
    # 忽略 PB 的正常启动日志
    if service == "pocketbase" and "PocketBase v" in errors and "started" in errors:
        print("💡 忽略正常启动日志")
        return

    files = glob.glob(f"{code_dir}/*{suffix}")
    if not files: return
    target_file = max(files, key=os.path.getmtime)
    
    with open(target_file, "r") as f: old_code = f.read()

    prompt = f"修复代码错误。\n日志：{errors}\n代码：{old_code}\n只返回修复后的代码，不要解释。"
    
    try:
        # 如果没有 API KEY，这里会报错
        if not API_KEY:
            print("❌ 错误：未读取到 AI_API_KEY，请在 Supervisor 配置中设置环境变量！")
            return

        res = requests.post(API_URL, headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}, json={"model": "qwen-plus", "messages": [{"role": "user", "content": prompt}]})
        new_code = clean_ai_code(res.json()['choices'][0]['message']['content'])
        
        with open(target_file, "w") as f: f.write(new_code)
        print("✅ 代码已修复写入")
        
        # 简单的 Git 提交（防止出错先简化）
        subprocess.run(["git", "add", "."], cwd="/home")
        subprocess.run(["git", "commit", "-m", f"AI Fix {service}"], cwd="/home")
        subprocess.run(["git", "push"], cwd="/home")
        
    except Exception as e:
        print(f"❌ 修复失败: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1: run_fix(sys.argv[1])