import os
import time
import subprocess
import json
import requests
import datetime

# Configuration
LOG_FILE = "/home/pb/error.log"
LAST_READ_POSITION_FILE = "/tmp/master_monitor_last_pos.txt"
SERVICE_STATUS_FILE = "/tmp/service_status.json"
GITHUB_ISSUE_API = "https://api.github.com/repos/your_github_user/your_github_repo/issues"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN") # Ensure this is set in your environment

# Placeholder for universal_fix.py path
UNIVERSAL_FIX_SCRIPT = "/path/to/universal_fix.py" # TODO: Update with actual path

def get_last_read_position():
    if os.path.exists(LAST_READ_POSITION_FILE):
        with open(LAST_READ_POSITION_FILE, "r") as f:
            return int(f.read().strip())
    return 0

def set_last_read_position(position):
    with open(LAST_READ_POSITION_FILE, "w") as f:
        f.write(str(position))

def get_new_log_content(log_file, last_pos):
    try:
        with open(log_file, "r") as f:
            f.seek(last_pos)
            new_content = f.read()
            new_pos = f.tell()
            return new_content, new_pos
    except FileNotFoundError:
        print(f"Log file not found: {log_file}")
        return "", last_pos
    except Exception as e:
        print(f"Error reading log file: {e}")
        return "", last_pos

def get_service_status(service_name):
    if os.path.exists(SERVICE_STATUS_FILE):
        with open(SERVICE_STATUS_FILE, "r") as f:
            status_data = json.load(f)
            return status_data.get(service_name, {})
    return {}

def update_service_status(service_name, status_info):
    status_data = {}
    if os.path.exists(SERVICE_STATUS_FILE):
        with open(SERVICE_STATUS_FILE, "r") as f:
            try:
                status_data = json.load(f)
            except json.JSONDecodeError:
                pass # Handle empty or invalid JSON
    
    status_data[service_name] = status_info
    with open(SERVICE_STATUS_FILE, "w") as f:
        json.dump(status_data, f, indent=4)

def contains_real_error(service_name, new_content):
    # If PocketBase just started, ignore initial logs that might contain "error" but are normal startup
    if service_name == "pocketbase" and "PocketBase v" in new_content and "started" in new_content:
        return False
        
    # Define PocketBase 的特定测试错误消息，这些消息不应触发自动修复
    # 这些模式是根据 Issue 中提供的日志内容总结而来
    pocketbase_test_error_messages = [
        "ERROR: Test after universal_fix update",
        "ERROR: Test after AI script fix",
        "ERROR: Final test after fix",
        "ERR" # 捕获日志中可能出现的截断测试错误，例如 "ERR"
    ]

    # 检查新内容中是否存在任何通用错误关键字
    general_error_keywords = ["error", "Error", "ERROR", "panic", "PANIC", "fatal", "FATAL", "exception", "Traceback"]
    
    # 逐行检查日志内容
    for line in new_content.splitlines():
        # 如果当前行包含任何通用错误关键字
        if any(kw in line for kw in general_error_keywords):
            # 进一步检查此错误是否为已知的测试错误
            is_known_test_error = False
            if service_name == "pocketbase":
                for test_msg in pocketbase_test_error_messages:
                    if test_msg in line:
                        is_known_test_error = True
                        break
            
            # 如果发现了一个通用错误，并且它不是一个已知的测试错误，那么这就是一个需要报告的“真实”错误
            if not is_known_test_error:
                return True
    
    # 如果遍历所有行后，没有发现任何非测试性的真实错误，则返回 False
    return False

def check_critical_state(service_name):
    """检测是否发生严重连续崩溃"""
    status = get_service_status(service_name)
    crash_count = status.get("crash_count", 0)
    last_crash_time = status.get("last_crash_time")

    if crash_count >= 3 and last_crash_time and (time.time() - last_crash_time < 300): # 5分钟内崩溃3次
        return True
    return False

def create_github_issue(title, body):
    if not GITHUB_TOKEN:
        print("GitHub token not found. Cannot create issue.")
        return

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "title": title,
        "body": body,
        "labels": ["bug", "auto-fix"]
    }

    try:
        response = requests.post(GITHUB_ISSUE_API, headers=headers, json=data)
        response.raise_for_status() # Raise an exception for HTTP errors
        print(f"GitHub Issue created: {response.json()['html_url']}")
    except requests.exceptions.RequestException as e:
        print(f"Error creating GitHub Issue: {e}")

def run_universal_fix(service_name, error_logs):
    print(f"Running universal_fix.py for {service_name}...")
    try:
        # Pass service_name and error_logs as arguments or environment variables
        # For simplicity, let's assume universal_fix.py can read from a temp file or stdin
        # Or, universal_fix.py might be designed to collect context itself.
        # Here, we'll just call it and let it handle its own context collection.
        subprocess.run(["python3", UNIVERSAL_FIX_SCRIPT, service_name], check=True, capture_output=True, text=True)
        print("universal_fix.py completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"universal_fix.py failed: {e}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
    except FileNotFoundError:
        print(f"Error: {UNIVERSAL_FIX_SCRIPT} not found.")

def main():
    service_name = "pocketbase" # This script is specifically for pocketbase based on the issue
    
    last_pos = get_last_read_position()
    new_content, new_pos = get_new_log_content(LOG_FILE, last_pos)

    if new_content:
        if contains_real_error(service_name, new_content):
            print(f"Real error detected for {service_name}. Triggering universal fix and GitHub Issue.")
            
            # Prepare issue title and body
            timestamp = datetime.datetime.now().strftime("%m/%d %H:%M")
            issue_title = f"[AUTO-FIX] {service_name} - {timestamp} 服务异常"
            issue_body = f"Detected a service anomaly for {service_name} at {timestamp}.\n\n"
            issue_body += "### Error Logs:\n```\n" + new_content + "\n```\n\n"
            issue_body += "Attempting to resolve using `universal_fix.py`."

            create_github_issue(issue_title, issue_body)
            run_universal_fix(service_name, new_content)
            
            # Reset crash count if a fix was attempted for a real error
            update_service_status(service_name, {"crash_count": 0, "last_crash_time": None})

        set_last_read_position(new_pos)

    # Example: Check for critical state (e.g., if PocketBase itself reports frequent crashes)
    # This part would typically be integrated with actual service monitoring (e.g., systemd status)
    # For this exercise, we'll assume the log analysis is the primary trigger.
    # if check_critical_state(service_name):
    #     print(f"Critical state detected for {service_name}. Further action might be needed.")

if __name__ == "__main__":
    # This script is intended to be run periodically, e.g., via cron
    main()
