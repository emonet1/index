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
    
    # 2. 提取错误日志
    error_log = ""
    error_match = re.search(
        r'### 📋 错误日志\s*```[^\n]*\n(.*?)```',
        issue_body,
        re.DOTALL
    )
    if error_match:
        error_log = error_match.group(1).strip()
        log(f"提取到错误日志: {len(error_log)} 字符")
    else:
        log("警告: 未找到错误日志", "WARN")
    
    # 3. 提取代码文件
    code_files = {}
    file_pattern = r'#### `([^`]+)`\s*```(\w+)\s*(.*?)```'
    
    for match in re.finditer(file_pattern, issue_body, re.DOTALL):
        file_path = match.group(1)
        language = match.group(2)
        code = match.group(3).strip()
        
        code_files[file_path] = {
            "language": language,
            "code": code
        }
        log(f"提取到文件: {file_path} ({len(code)} 字符)")
    
    if not code_files:
        log("警告: 未找到代码文件", "WARN")
    
    return service_name, error_log, code_files


def call_ai_api(prompt, max_retries=3):
    """调用通义千问 API"""
    
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
            if hasattr(e.response, 'text'):
                log(f"响应内容: {e.response.text}", "ERROR")
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
```
{error_log}
```

## 文件路径
{file_path}

## 原始代码
```{language}
{original_code}
```

## 要求
1. 仔细分析错误日志，定位问题根源
2. 修复所有语法错误和逻辑错误
3. 保持原有代码结构和注释
4. 确保修复后的代码可以正常运行
5. **只返回修复后的完整代码，不要包含任何解释、注释或markdown标记**

## 输出
直接输出修复后的代码："""

    # 调用 AI
    fixed_code = call_ai_api(prompt)
    
    if not fixed_code:
        log(f"❌ AI 修复失败: {file_path}", "ERROR")
        return None
    
    # 清理 AI 返回内容
    fixed_code = clean_ai_response(fixed_code)
    
    log(f"✅ 修复完成: {file_path} ({len(fixed_code)} 字符)")
    return fixed_code


def write_fixed_files(service_name, code_files_fixed):
    """将修复后的代码写入文件"""
    
    log("开始写入修复后的文件...")
    
    # 确定服务目录
    service_dir = SERVICE_DIRS.get(service_name, service_name)
    
    for file_path, fixed_code in code_files_fixed.items():
        # 构建完整路径
        full_path = os.path.join(service_dir, file_path)
        
        # 创建目录
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # 写入文件
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(fixed_code)
            log(f"✅ 已写入: {full_path}")
        except Exception as e:
            log(f"❌ 写入失败 {full_path}: {e}", "ERROR")


def main():
    """主函数"""
    
    log("=" * 60)
    log("🤖 AI 自动修复流程开始")
    log("=" * 60)
    
    # 检查必要的环境变量
    if not AI_API_KEY:
        log("❌ 缺少 AI_API_KEY 环境变量", "ERROR")
        sys.exit(1)
    
    if not ISSUE_NUMBER:
        log("❌ 缺少 ISSUE_NUMBER 环境变量", "ERROR")
        sys.exit(1)
    
    # 解析 Issue 内容
    service_name, error_log, code_files = parse_issue_content(ISSUE_BODY, ISSUE_TITLE)
    
    if not error_log:
        log("❌ 未找到错误日志，无法修复", "ERROR")
        sys.exit(1)
    
    if not code_files:
        log("❌ 未找到代码文件，无法修复", "ERROR")
        sys.exit(1)
    
    log(f"📊 统计: 服务={service_name}, 错误日志={len(error_log)}字符, 文件数={len(code_files)}")
    
    # 逐个修复代码文件
    code_files_fixed = {}
    
    for file_path, file_info in code_files.items():
        original_code = file_info["code"]
        language = file_info["language"]
        
        fixed_code = fix_code_file(file_path, original_code, error_log, language)
        
        if fixed_code:
            code_files_fixed[file_path] = fixed_code
        else:
            log(f"⚠️  跳过文件（修复失败）: {file_path}", "WARN")
    
    if not code_files_fixed:
        log("❌ 所有文件修复失败", "ERROR")
        sys.exit(1)
    
    # 写入修复后的文件
    write_fixed_files(service_name, code_files_fixed)
    
    log("=" * 60)
    log(f"✅ AI 修复流程完成！共修复 {len(code_files_fixed)} 个文件")
    log("=" * 60)


if __name__ == "__main__":
    main()
