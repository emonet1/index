import time
import os
import subprocess
from datetime import datetime

# 监控目标列表
SERVICE_LIST = ["pocketbase", "ai-proxy", "websocket"]

def check_and_fix():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 👀 巡逻中...")
    
    for service_name in SERVICE_LIST:
        # 1. 针对 PocketBase 的日志监控
        fix_triggered = False 
        if service_name == "pocketbase":
            log_path = "/home/pb/error.log"
            if os.path.exists(log_path):
                if (time.time() - os.path.getmtime(log_path)) < 60:
                    print(f"🚨 警报: {service_name} 日志刚刚更新，疑似报错！")
                    subprocess.run(["python3", "/home/universal_fix.py", service_name])
                    subprocess.run(["supervisorctl", "restart", service_name])
                    fix_triggered = True
        
        if fix_triggered: continue

        # 2. 针对所有服务的进程状态监控
        try:
            res = subprocess.run(["supervisorctl", "status", service_name], capture_output=True, text=True)
            status = res.stdout.strip()
            # 如果状态包含服务名，但不是 RUNNING 也不是 STOPPED，就是挂了
            if service_name in status and not any(s in status for s in ["RUNNING", "STOPPED"]):
                print(f"🚨 警报: {service_name} 状态异常！正在修复...")
                subprocess.run(["python3", "/home/universal_fix.py", service_name])
                subprocess.run(["supervisorctl", "restart", service_name])
                print(f"✅ {service_name} 修复流程已触发")

        except Exception as e:
            print(f"❌ 监控报错: {e}")

if __name__ == "__main__":
    print("===================================")
    print("🚀 监工程序启动成功！")
    print("===================================")
    # 这一句是防止程序退出的关键
    while True:
        check_and_fix()
        time.sleep(5)