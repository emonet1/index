import time
import os
import subprocess

# 路径配置
LOG_FILE = "/home/pb/error.log"
FIX_SCRIPT = "/home/pb/ai_fix.py"

def monitor_log():
    print("--- AI 监控守卫启动成功 ---")
    
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f: f.write("Log initialized\n")
        
    with open(LOG_FILE, "r") as f:
        # 移到文件末尾开始看
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(1)
                continue
            
            print(f"DEBUG: 读到日志 -> {line.strip()}")
            
            # 只要包含这些词，就触发 AI
            msg = line.lower()
            keywords = ["error", "panic", "syntax", "failed", "invalid"]
            if any(k in msg for k in keywords):
                print(f"🚨 发现错误！正在启动 AI 修复脚本...")
                try:
                    # 启动修复脚本，并把报错行传给它
                    subprocess.Popen(["python3", FIX_SCRIPT, line.strip()])
                except Exception as e:
                    print(f"❌ 启动修复脚本失败: {e}")

if __name__ == "__main__":
    try:
        monitor_log()
    except Exception as e:
        print(f"🔥 监控脚本发生异常: {e}")
