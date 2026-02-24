#!/usr/bin/env python3
"""
AI 自动修复脚本
在 GitHub Actions 中运行，调用通义千问 API 进行代码修复
"""
import os
import re
import requests
import json
import sys

# ==================== 配置区 ====================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")
ISSUE_NUMBER = os.getenv("ISSUE_NUMBER")
ISSUE_BODY = os.getenv("ISSUE_BODY", "")
ISSUE_TITLE = os.getenv("ISSUE_TITLE", "")

AI_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
AI_MODEL = "qwen-plus"

# 服务目录映射
SERVICE_DIRS = {
    "pocketbase": "pb/pb_hooks",
    "websocket": "websocket-server",
    "ai-proxy": "ai-proxy"
}
# ================================================


def log(message, level="INFO"):
    """打印日志"""
    print(f"[{level}] {message}", flush=True)


def parse_issue_content(issue_body, issue_title):
    """从 Issue 中提取服务名、错误日志和代码文件"""
    
    log("开始解析 Issue 内容...")
    
    # 1. 提取服务名称
    service_name = "unknown"
    service_match = re.search(r'\[AUTO-FIX\]\s+(\w+)', issue_title)
    if service_match:
        service_name = service_match.group(1).lower()
        log(f"识别到服务: {service_name}")
    else:
        log("警告: 未能识别服务名称", "WARN")
    
    # 2. 提取错误日志 - 修复正则表达式
    error_log = ""
    # ✅ 修复：支持标题后的可选文本（如"已脱敏"），支持标题和代码块之间的换行
    error_patterns = [
        r'### 📋 错误日志[^\n]*\n```[^\n]*\n(.*?)```',  # 新格式：标题后有文本+换行
        r'### 📋 错误日志\s*```[^\n]*\n(.*?)```',      # 旧格式：标题后直接代码块
        r'错误日志.*?```[^\n]*\n(.*?)```',              # 备用：更宽松的匹配
    ]
    
    for pattern in error_patterns:
        error_match = re.search(pattern, issue_body, re.DOTALL)
        if error_match:
            error_log = error_match.group(1).strip()
            log(f"✅ 提取到错误日志: {len(error_log)} 字符")
            break
    
    if not error_log:
        log("警告: 未找到错误日志", "WARN")
        # 调试：打印 Issue body 的前500字符
        log(f"Issue body 预览: {issue_body[:500]}", "DEBUG")
    
    # 3. 提取代码文件 - 修复正则表达式
    code_files = {}
    # ✅ 修复：更宽松的匹配，支持多行和空格
    file_pattern = r'#### `([^`]+)`\s*```(\w+)\s*\n(.*?)\n```'
    
    for match in re.finditer(file_pattern, issue_body, re.DOTALL):
        file_path = match.group(1).strip()
        language = match.group(2).strip()
        code = match.group(3).strip()
        
        # 过滤掉截断的代码
        if "代码截断" not in code and len(code) > 10:
            code_files[file_path] = {
                "language": language,
                "code": code
            }
            log(f"✅ 提取到文件: {file_path} ({len(code)} 字符)")
        else:
            log(f"⚠️  跳过文件（代码不完整）: {file_path}", "WARN")
    
    if not code_files:
        log("警告: 未找到代码文件", "WARN")
        # 调试：查找所有代码块
        all_code_blocks = re.findall(r'```(\w+)\s*\n(.*?)\n```', issue_body, re.DOTALL)
        log(f"找到 {len(all_code_blocks)} 个代码块", "DEBUG")
    
    return service_name, error_log, code_files


def call_ai_api(prompt, max_retries=3):
    """调用通义千问 API"""
    
    if not AI_API_KEY:
        log("❌ AI_API_KEY 未设置", "ERROR")
        return None
    
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的代码修复工程师。请仔细分析错误日志，定位问题根源，并提供修复后的完整代码。只返回修复后的代码，不要包含任何解释或markdown标记。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 4000
    }
    
    for attempt in range(max_retries):
        try:
            log(f"调用 AI API (尝试 {attempt + 1}/{max_retries})...")
            
            response = requests.post(
                AI_API_URL,
                headers=headers,
                json=data,
                timeout=60
            )
            
            response.raise_for_status()
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0]['message']['content']
                log(f"✅ AI 返回 {len(content)} 字符")
                return content
            else:
                log(f"API 返回格式异常: {result}", "ERROR")
                
        except requests.exceptions.Timeout:
            log(f"请求超时 (尝试 {attempt + 1}/{max_retries})", "WARN")
        except requests.exceptions.RequestException as e:
            log(f"请求失败: {e}", "ERROR")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    log(f"响应内容: {e.response.text[:200]}", "ERROR")
                except:
                    pass
        except Exception as e:
            log(f"未知错误: {e}", "ERROR")
        
        if attempt < max_retries - 1:
            import time
            time.sleep(2 ** attempt)  # 指数退避
    
    return None


def clean_ai_response(text):
    """清理 AI 返回的代码（去除可能的 markdown 标记）"""
    
    # 去除开头的代码块标记
    text = re.sub(r'^```\w*\n', '', text)
    # 去除结尾的代码块标记
    text = re.sub(r'\n```$', '', text)
    # 去除可能的语言标识
    text = re.sub(r'^(javascript|python|js|py)\n', '', text, flags=re.IGNORECASE)
    
    return text.strip()


def fix_code_file(file_path, original_code, error_log, language):
    """使用 AI 修复单个代码文件"""
    
    log(f"开始修复文件: {file_path}")
    
    # 构建 prompt
    prompt = f"""## 任务
修复以下代码中的错误。

## 错误日志
