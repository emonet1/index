#!/usr/bin/env python3
"""
服务器端日志监控脚本（修复版）
✅ 特性：事件驱动、增量读取、防止死循环、冷却期保护
"""
import os
import sys
import subprocess
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ==================== 配置区 ====================
# 格式： "Supervisor服务名": "日志文件的绝对路径"
SERVICE_MAP = {
    "pocketbase": "/home/pb/error.log",
    "ai-proxy":   "/home/ai-proxy/error.log",
    "websocket":  "/home/websocket-server/error.log"
}

# ❄️ 冷却期（秒）：同一服务在此时间内不会重复触发 Issue
# 设置为 600秒（10分钟），给予 AI 足够的时间修复代码并部署
COOLDOWN_SECONDS = 600
# ================================================

# 记录文件读取位置和上次修复时间
file_positions = {}
last_fix_time = {}

def log(msg):
    """带时间戳的日志"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def contains_real_error(new_content, service_name):
    """判断是否包含真实错误（过滤掉正常启动日志）"""
    # 忽略 PocketBase 正常启动日志
    if service_name == "pocketbase":
        if "PocketBase v" in new_content and "started" in new_content:
            return False

    error_keywords = [
        "error", "Error", "ERROR",
        "exception", "Exception",
        "traceback", "Traceback",
        "panic", "PANIC",
        "fatal", "FATAL"
    ]
    return any(kw in new_content for kw in error_keywords)

def trigger_fix_process(service_name):
    """调用 universal_fix.py 上报错误"""
    now = time.time()
    last_time = last_fix_time.get(service_name, 0)
    
    # ❄️ 冷却期检查
    if (now - last_time) < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (now - last_time))
        log(f"⏳ [{service_name}] 正在冷却中 (剩余 {remaining}s)，跳过上报")
        return

    log(f"🚨 [{service_name}] 发现错误！正在触发自动上报...")
    
    try:
        # 调用修复脚本（只上报 Issue，不重启服务，重启由 deploy.yml 负责）
        subprocess.run(
            ["python3", "/home/universal_fix.py", service_name],
            check=False
        )
        # 更新冷却时间
        last_fix_time[service_name] = now
        log(f"✅ [{service_name}] 上报完成，进入 {COOLDOWN_SECONDS}s 冷却期")
    except Exception as e:
        log(f"❌ 调用 universal_fix.py 失败: {e}")

class LogHandler(FileSystemEventHandler):
    def __init__(self, service_name, log_path):
        self.service_name = service_name
        self.log_path = log_path

    def on_modified(self, event):
        if event.src_path != self.log_path:
            return

        current_pos = file_positions.get(self.log_path, 0)
        try:
            if not os.path.exists(self.log_path):
                return

            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(current_pos)
                new_content = f.read()
                if not new_content:
                    return
                
                # 更新位置
                file_positions[self.log_path] = f.tell()
                
                # 简单预览（脱敏）
                preview = new_content[:50].replace("\n", " ")
                log(f"📄 [{self.service_name}] 新日志: {preview}...")

                if contains_real_error(new_content, self.service_name):
                    trigger_fix_process(self.service_name)

        except Exception as e:
            log(f"⚠️ 读取日志出错: {e}")

def init_file_positions():
    """初始化文件指针到末尾，忽略历史日志"""
    for service, path in SERVICE_MAP.items():
        if os.path.exists(path):
            with open(path, "rb") as f:
                f.seek(0, 2)
                file_positions[path] = f.tell()
            log(f"📍 [{service}] 已定位到日志末尾")
        else:
            file_positions[path] = 0

if __name__ == "__main__":
    log("===================================")
    log("🚀 监控服务启动 (Watchdog模式 + 冷却保护)")
    log("===================================")
    
    init_file_positions()
    
    observer = Observer()
    for service, path in SERVICE_MAP.items():
        directory = os.path.dirname(path)
        if os.path.exists(directory):
            handler = LogHandler(service, path)
            observer.schedule(handler, path=directory, recursive=False)
            log(f"👀 正在监控: {service} -> {path}")
        else:
            log(f"⚠️ 目录不存在，跳过: {directory}")

    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
