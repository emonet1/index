#!/usr/bin/env python3
# /home/master_monitor.py
import os
import sys
import subprocess
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ✅ 导入统一脱敏模块（带降级方案）
try:
    from sanitizer import LogSanitizer
except ImportError:
    print("⚠️  未找到 sanitizer.py，使用内置脱敏模块")
    import re
    class LogSanitizer:
        """轻量级内置脱敏器"""
        @staticmethod
        def sanitize(text):
            if not text:
                return ""
            # 邮箱
            text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.com', text)
            # IP地址
            text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '*.*.*.*', text)
            # Token/Key
            text = re.sub(r'(?:sk-|pk-|ghp_|gho_)[A-Za-z0-9_+\-=]{20,}', '***KEY***', text)
            # JWT
            text = re.sub(r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', 'eyJ***JWT***', text)
            return text

# ==================== 配置区 ====================
SERVICE_MAP = {
    "pocketbase": "/home/pb/error.log",
    "ai-proxy":   "/home/ai-proxy/error.log",
    "websocket":  "/home/websocket-server/error.log"
}

# ⚡ 冷却期缩短为 2 分钟 (平衡响应速度与防刷屏)
COOLDOWN_SECONDS = 120  

# 🚨 严重故障阈值: 5分钟内崩溃超过5次
CRASH_WINDOW = 300
CRASH_LIMIT = 5
# ================================================

# 状态追踪
file_positions = {}
last_fix_time = {}
crash_history = {} # 记录崩溃时间戳列表: {'pocketbase': [t1, t2...]}

def log(msg, level="INFO"):
    """带时间戳的日志"""
    icon = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}.get(level, "")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {icon} {msg}", flush=True)

def contains_real_error(new_content, service_name):
    # 忽略 PB 正常启动日志
    if service_name == "pocketbase" and "PocketBase v" in new_content and "started" in new_content:
        return False
        
    error_keywords = ["error", "Error", "ERROR", "panic", "PANIC", "fatal", "FATAL", "exception", "Traceback"]
    return any(kw in new_content for kw in error_keywords)

def check_critical_state(service_name):
    """检测是否发生严重连续崩溃"""
    now = time.time()
    if service_name not in crash_history:
        crash_history[service_name] = []
    
    # 清理过期记录 (保留最近 CRASH_WINDOW 秒内的)
    crash_history[service_name] = [t for t in crash_history[service_name] if now - t < CRASH_WINDOW]
    
    # 添加本次记录
    crash_history[service_name].append(now)
    
    count = len(crash_history[service_name])
    if count >= CRASH_LIMIT:
        log(f"[{service_name}] 严重故障! {CRASH_WINDOW/60}分钟内崩溃 {count} 次! 请人工介入!", "CRITICAL")
        # TODO: 这里可以接入邮件或短信通知接口
        return True
    return False

def trigger_fix_process(service_name):
    now = time.time()
    
    # 1. 检测严重故障（如果达到阈值则阻止自动修复）
    if check_critical_state(service_name):
        log(f"[{service_name}] 🔥 进入紧急模式：暂停自动修复，等待人工干预!", "CRITICAL")
        return  # 阻止继续执行

    # 2. 冷却期检查
    last_time = last_fix_time.get(service_name, 0)
    if (now - last_time) < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (now - last_time))
        log(f"[{service_name}] 修复冷却中 (剩余 {remaining}s)，跳过上报", "WARN")
        return

    log(f"[{service_name}] 触发自动上报流程...", "INFO")
    
    try:
        # 调用 universal_fix.py
        subprocess.run(["python3", "/home/universal_fix.py", service_name], check=False)
        last_fix_time[service_name] = now
        log(f"[{service_name}] 上报完成，进入冷却", "INFO")
    except Exception as e:
        log(f"调用修复脚本失败: {e}", "ERROR")

class LogHandler(FileSystemEventHandler):
    def __init__(self, service_name, log_path):
        self.service_name = service_name
        self.log_path = log_path

    def on_modified(self, event):
        if event.src_path != self.log_path: return
        
        try:
            current_pos = file_positions.get(self.log_path, 0)
            if not os.path.exists(self.log_path): return

            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(current_pos)
                new_content = f.read()
                
                # ✅ 修复：始终更新文件指针，避免重复读取旧日志
                file_positions[self.log_path] = f.tell()
                
                if not new_content: return
                
                # ✅ 修复：预览日志前进行脱敏
                preview = new_content[:80].replace("\n", " ")
                safe_preview = LogSanitizer.sanitize(preview)
                log(f"[{self.service_name}] 新日志: {safe_preview}...", "INFO")

                if contains_real_error(new_content, self.service_name):
                    trigger_fix_process(self.service_name)

        except Exception as e:
            log(f"读取日志出错: {e}", "ERROR")

def init_file_positions():
    for service, path in SERVICE_MAP.items():
        if os.path.exists(path):
            with open(path, "rb") as f:
                f.seek(0, 2)
                file_positions[path] = f.tell()
        else:
            file_positions[path] = 0

if __name__ == "__main__":
    log("===================================")
    log("🚀 智能监控启动 (脱敏+防刷屏+严重故障检测)")
    log("===================================")
    
    init_file_positions()
    observer = Observer()
    
    for service, path in SERVICE_MAP.items():
        directory = os.path.dirname(path)
        if os.path.exists(directory):
            observer.schedule(LogHandler(service, path), path=directory, recursive=False)
            log(f"正在监控: {service}", "INFO")
            
    observer.start()
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
