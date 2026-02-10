import time
import os
import subprocess
from datetime import datetime

# ================= 配置区 =================
# 格式： "Supervisor服务名": "日志文件的绝对路径"
SERVICE_MAP = {
    "pocketbase": "/home/pb/error.log",
    "ai-proxy":   "/home/ai-proxy/error.log",
    "websocket":  "/home/websocket-server/error.log"
}
# ==========================================

def check_and_fix():
    # 打印日志时强制刷新缓冲区，确保 supervisor 能实时捕获
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 👀 巡逻中...", flush=True)
    
    for service_name, log_path in SERVICE_MAP.items():
        fix_triggered = False 

        # ===========================
        # 🔍 1. 检查日志是否刚刚更新
        # ===========================
        if os.path.exists(log_path):
            try:
                # 检查过去 60 秒内是否有新日志
                if (time.time() - os.path.getmtime(log_path)) < 60:
                    print(f"\n🚨 警报: [{service_name}] 日志刚刚更新，疑似报错！", flush=True)
                    
                    # 触发修复
                    subprocess.run(["python3", "/home/universal_fix.py", service_name])
                    subprocess.run(["supervisorctl", "restart", service_name])
                    
                    fix_triggered = True
                    print(f"✅ {service_name} 修复流程完成 (基于日志)\n", flush=True)
            except Exception as e:
                print(f"⚠️ 读取日志失败: {e}", flush=True)
        
        if fix_triggered: continue

        # ===========================
        # 🔍 2. 检查进程状态
        # ===========================
        try:
            res = subprocess.run(["supervisorctl", "status", service_name], capture_output=True, text=True)
            status = res.stdout.strip()
            
            # 如果状态不是 RUNNING
            if service_name in status and not any(s in status for s in ["RUNNING"]):
                print(f"\n🚨 警报: [{service_name}] 进程状态异常！\n📉 当前状态: {status}", flush=True)
                
                # 触发修复
                subprocess.run(["python3", "/home/universal_fix.py", service_name])
                subprocess.run(["supervisorctl", "restart", service_name])
                
                print(f"✅ {service_name} 修复流程完成 (基于状态)\n", flush=True)

        except Exception as e:
            print(f"❌ 监控报错: {e}", flush=True)

if __name__ == "__main__":
    print("===================================", flush=True)
    print("🚀 全能监工已启动 (Websocket 路径已修正)", flush=True)
    print("===================================", flush=True)
    
    while True:
        check_and_fix()
        time.sleep(5)
