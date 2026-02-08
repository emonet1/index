import os, sys, requests, glob, subprocess
from datetime import datetime

# === 配置区 ===
API_KEY = os.getenv("AI_API_KEY")
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
REPO_PATH = "/home"

# 项目配置图：[代码目录, 错误日志, 文件后缀]
PROJECTS = {
    "pocketbase": ["/home/pb/pb_hooks", "/home/pb/error.log", ".js"],
    "ai-proxy": ["/home/ai-proxy", "/home/ai-proxy/error.log", ".py"],
    "websocket": ["/home/websocket-server", "/home/websocket-server/error.log", ".js"]
}

def sync_github(service):
    """同步到 GitHub"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        subprocess.run(["git", "config", "user.email", "ErnstGabona148@gmail.com"], cwd=REPO_PATH)
        subprocess.run(["git", "config", "user.name", "emonet1"], cwd=REPO_PATH)
        subprocess.run(["git", "add", "."], cwd=REPO_PATH)
        subprocess.run(["git", "commit", "--allow-empty", "-m", f"AI Fix [{service}]: {now}"], cwd=REPO_PATH)
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_PATH)
        print(f"✅ GitHub 同步成功")
    except Exception as e:
        print(f"❌ Git 同步失败: {e}")

def run_fix(service):
    if service not in PROJECTS: return
    code_dir, log_path, suffix = PROJECTS[service]
    
    if not os.path.exists(log_path): return
    with open(log_path, "r") as f:
        errors = "".join(f.readlines()[-30:]) # 读取最后30行报错

    # 寻找目录下最新修改的代码文件进行修复
    files = glob.glob(f"{code_dir}/*{suffix}")
    if not files: return
    target_file = max(files, key=os.path.getmtime)

    with open(target_file, "r") as f:
        old_code = f.read()

    print(f"正在请求 AI 修复 {service}...")
    prompt = f"你是一个代码修复专家。该项目是 {service}。\n报错内容：\n{errors}\n当前代码：\n{old_code}\n直接返回修复后的完整 JS/Python 代码，不要任何解释。"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "qwen-plus", "messages": [{"role": "user", "content": prompt}]}
    
    try:
        res = requests.post(API_URL, headers=headers, json=payload, timeout=40).json()
        new_code = res['choices'][0]['message']['content'].replace("```javascript", "").replace("```python", "").replace("```", "").strip()
        
        with open(target_file, "w") as f:
            f.write(new_code)
        
        sync_github(service)
        subprocess.run(["supervisorctl", "restart", service])
        print(f"✨ {service} 自动修复并重启完成！")
    except Exception as e:
        print(f"❌ 修复服务 {service} 时出错: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_fix(sys.argv[1])
