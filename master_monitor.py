#!/usr/bin/env python3
"""
服务器端日志监控脚本（重构版 + 安全增强）
改进点：
  1. 事件驱动（watchdog），废弃 while True 轮询
  2. 废弃 mtime，改用增量内容匹配
  3. 引入冷却期，防止同一服务短时间内重复触发
  4. ✅ 新增：日志输出自动脱敏，防止监控日志泄露敏感信息
"""
import os
import sys
import subprocess
import time
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ✅ 导入脱敏模块
try:
    from sanitizer import LogSanitizer
    SANITIZER_AVAILABLE = True
except ImportError:
    print("⚠️ 警告：脱敏模块未找到，将使用简化版", flush=True)
    SANITIZER_AVAILABLE = False
    # 简化版脱敏（备用方案）
    import re
    class LogSanitizer:
        @staticmethod
        def sanitize(text):
            text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.com', text)
            text = re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '*.*.*.*', text)
            text = re.sub(r'(?:sk-|pk-|ghp_|gho_)[A-Za-z0-9_]{20,}', '***', text)
            text = re.sub(r'(?i)(password|passwd|pwd|secret)["\']?\s*[:=]\s*["\']?([^"\'\s]{3,})', r'\1=***', text)
            return text

# ==================== 配置区 ====================
# 格式： "Supervisor服务名": "日志文件的绝对路径"
SERVICE_MAP = {
    "pocketbase": "/home/pb/error.log",
    "ai-proxy":   "/home/ai-proxy/error.log",
    "websocket":  "/home/websocket-server/error.log"
}

# ⭐ 冷却期（秒）：同一服务在此时间内不会重复触发
COOLDOWN_SECONDS = 300  # 5分钟
# ================================================

# 记录每个日志文件上次读到的位置（增量读取用）
file_positions = {}
# 记录每个服务上次触发修复的时间（冷却期用）
last_fix_time = {}


def log(msg):
    """统一的日志打印，带时间戳，强制刷新缓冲区"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def contains_real_error(new_content, service_name):
    """
    ⭐ 增量内容匹配：检查新写入的日志内容是否包含真实错误关键词
    不再依赖 mtime，彻底避免正常日志被误判为错误
    """
    # 忽略 PocketBase 正常启动日志
    if service_name == "pocketbase":
        if "PocketBase v" in new_content and "started" in new_content:
            return False

    error_keywords = [
        "error", "Error", "ERROR",
        "exception", "Exception", "EXCEPTION",
        "traceback", "Traceback",
        "fatal", "Fatal", "FATAL",
        "panic", "PANIC",
        "undefined", "cannot", "failed", "Failed",
        "crash", "Crash", "CRASH"
    ]
    return any(kw in new_content for kw in error_keywords)


def trigger_fix(service_name):
    """
    触发修复流程（带冷却期）
    调用 universal_fix.py 创建 GitHub Issue，由 Actions 负责后续修复
    """
    now = time.time()

    # ⭐ 冷却期检查：防止同一服务短时间内反复触发
    last_time = last_fix_time.get(service_name, 0)
    if (now - last_time) < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (now - last_time))
        log(f"⏳ [{service_name}] 冷却期中，还剩 {remaining} 秒，跳过本次触发")
        return

    log(f"🚨 [{service_name}] 检测到真实错误，触发修复流程！")
    last_fix_time[service_name] = now  # 更新冷却时间戳

    # 调用 universal_fix.py 创建 GitHub Issue（不直接改代码）
    try:
        result = subprocess.run(
            ["python3", "/home/universal_fix.py", service_name],
            timeout=60,
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            log(f"✅ [{service_name}] Issue 创建成功")
            # 从输出中提取 Issue URL（如果有）
            for line in result.stdout.split('\n'):
                if "已创建 GitHub Issue" in line or "Issue:" in line:
                    log(f"📎 {line.strip()}")
        else:
            log(f"⚠️ [{service_name}] Issue 创建失败: {result.stderr[:100]}")
            
    except subprocess.TimeoutExpired:
        log(f"⚠️ [{service_name}] universal_fix.py 执行超时")
    except Exception as e:
        log(f"❌ [{service_name}] 调用 universal_fix.py 失败: {e}")


class LogFileHandler(FileSystemEventHandler):
    """
    ⭐ 事件驱动：watchdog 监听文件修改事件
    只有日志文件真正有新内容写入时才触发，完全不轮询
    """

    def __init__(self, service_name, log_path):
        self.service_name = service_name
        self.log_path = log_path

    def on_modified(self, event):
        # 只处理目标日志文件，忽略目录下其他文件的变化
        if event.src_path != self.log_path:
            return

        # ⭐ 增量读取：只读取上次位置之后新增的内容
        current_pos = file_positions.get(self.log_path, 0)

        try:
            with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(current_pos)
                new_content = f.read()
                new_pos = f.tell()

            # 没有新内容则跳过
            if not new_content.strip():
                return

            # 更新文件读取位置，下次从这里继续读
            file_positions[self.log_path] = new_pos

            # ✅ 关键改进：脱敏后再输出日志片段
            safe_preview = LogSanitizer.sanitize(new_content[:80].strip())
            log(f"📄 [{self.service_name}] 新日志: {safe_preview}")

            # ⭐ 增量内容匹配：判断是否是真实错误
            if contains_real_error(new_content, self.service_name):
                trigger_fix(self.service_name)
            else:
                log(f"✅ [{self.service_name}] 正常日志，忽略")

        except Exception as e:
            log(f"⚠️ 读取日志失败 [{self.service_name}]: {e}")


def init_file_positions():
    """
    启动时将所有日志文件的读取位置初始化到文件末尾
    避免重启监控脚本时把历史日志重复处理一遍
    """
    for service_name, log_path in SERVICE_MAP.items():
        if os.path.exists(log_path):
            with open(log_path, "rb") as f:
                f.seek(0, 2)  # 移动到文件末尾
                file_positions[log_path] = f.tell()
            log(f"📍 [{service_name}] 初始化位置: {file_positions[log_path]} bytes")
        else:
            file_positions[log_path] = 0
            log(f"⚠️  [{service_name}] 日志文件暂不存在: {log_path}（服务启动后会自动监控）")


if __name__ == "__main__":
    log("===================================")
    log("🚀 全能监工已启动（事件驱动 + 增量匹配 + 冷却期）")
    if SANITIZER_AVAILABLE:
        log("🔒 日志脱敏功能已启用")
    else:
        log("⚠️  使用简化版脱敏（建议创建 sanitizer.py）")
    log("===================================")

    # 第一步：初始化所有文件位置，跳过历史日志
    init_file_positions()

    # 第二步：为每个服务注册 watchdog 监听
    observer = Observer()
    for service_name, log_path in SERVICE_MAP.items():
        log_dir = os.path.dirname(log_path)
        if not os.path.exists(log_dir):
            log(f"⚠️  目录不存在，暂时跳过: {log_dir}")
            continue
        handler = LogFileHandler(service_name, log_path)
        # recursive=False：只监听该目录，不递归子目录
        observer.schedule(handler, path=log_dir, recursive=False)
        log(f"👀 监控已注册: [{service_name}] → {log_path}")

    # 第三步：启动监控
    observer.start()
    log("✅ 所有监控已启动，等待日志变化事件...")

    try:
        while True:
            time.sleep(1)  # 主线程保持运行，watchdog 在后台线程工作
    except KeyboardInterrupt:
        observer.stop()
        log("🛑 监控已手动停止")

    observer.join()
