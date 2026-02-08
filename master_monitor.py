import time, os, subprocess

# 监控名单
WATCH_LIST = [
    {"name": "pocketbase", "log": "/home/pb/error.log"},
    {"name": "ai-proxy", "log": "/home/ai-proxy/error.log"},
    {"name": "websocket", "log": "/home/websocket-server/error.log"},
]

def get_size(p): return os.path.getsize(p) if os.path.exists(p) else 0

# 初始记录
last_sizes = {item['name']: get_size(item['log']) for item in WATCH_LIST}

print("👀 超级监工正在巡逻 (PB, AI-Proxy, WebSocket)...")

while True:
    for item in WATCH_LIST:
        current_size = get_size(item['log'])
        # 如果日志文件变大了，说明有新报错
        if current_size > last_sizes[item['name']]:
            print(f"🚨 警告：检测到 {item['name']} 报错日志有更新！")
            # 立即启动对应的医生脚本进行修复
            subprocess.run(["python3", "/home/universal_fix.py", item['name']])
            # 更新大小，避免重复触发
            last_sizes[item['name']] = current_size
    
    time.sleep(5) # 每5秒巡视一圈
