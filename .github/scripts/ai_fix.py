#!/usr/bin/env python3
"""
双AI仲裁修复脚本 v3.0 (融合版)
- 架构: Qwen-Max (方案A) + Gemini-Flash (方案B) -> Gemini-Leader (仲裁)
- 功能: 自动解析Issue -> 风险评估 -> 双AI并行修复 -> 语法验证 -> 原位覆盖写入
"""
import os
import re
import requests
import json
import sys
import time

# ==================== 配置区 ====================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_KEY   = os.getenv("GEMINI_API_KEY")
QWEN_KEY     = os.getenv("QWEN_API_KEY")
ISSUE_NUMBER = os.getenv("ISSUE_NUMBER")
ISSUE_BODY   = os.getenv("ISSUE_BODY", "")
ISSUE_TITLE  = os.getenv("ISSUE_TITLE", "")

# Gemini API 配置
GEMINI_BASE  = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-2.0-flash"     # 执行者
GEMINI_JUDGE = "gemini-1.5-pro"       # 仲裁者 (使用更聪明的模型)

# 通义千问 API 配置
QWEN_BASE    = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
QWEN_MODEL   = "qwen-max"

# 服务目录映射 (保持原有的目录感知能力)
SERVICE_DIRS = {
    "pocketbase": "pb/pb_hooks",
    "websocket": "websocket-server",
    "ai-proxy": "ai-proxy"
}

# 敏感/重负荷关键词 (触发人工审查)
CRITICAL_KEYWORDS = [
    "database", "migration", "schema", "drop table", "alter table",
    "auth", "password", "secret", "token", "login",
    "payment", "billing",
    "rm -rf", "sudo",
    "architecture change"
]
# ================================================

def log(message, level="INFO"):
    icons = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "OK": "✅", "AI": "🤖", "JUDGE": "⚖️"}
    icon = icons.get(level, "")
    print(f"[{level}] {icon} {message}", flush=True)

# ================= 1. 核心解析逻辑 (保留自旧版) =================

def parse_issue_content(issue_body, issue_title):
    """从 Issue 中提取服务名、错误日志和代码文件"""
    log("开始解析 Issue 内容...")
    
    # 1. 提取服务名称
    service_name = "unknown"
    service_match = re.search(r'\[AUTO-FIX\]\s+(\w+)', issue_title)
    if service_match:
        service_name = service_match.group(1).lower()
    
    # 2. 提取错误日志
    error_log = ""
    error_patterns = [
        r'### 📋 错误日志[^\n]*\n```[^\n]*\n(.*?)\n```',
        r'错误日志.*?\n```[^\n]*\n(.*?)\n```',
    ]
    for pattern in error_patterns:
        match = re.search(pattern, issue_body, re.DOTALL)
        if match:
            error_log = match.group(1).strip()
            break
            
    # 3. 提取代码文件
    code_files = {}
    file_pattern = r'#### `([^`]+)`\s*\n```(\w+)\s*\n(.*?)\n```'
    matches = list(re.finditer(file_pattern, issue_body, re.DOTALL))
    
    for match in matches:
        file_path = match.group(1).strip()
        language = match.group(2).strip()
        code = match.group(3).strip()
        
        if len(code) > 10 and "截断" not in code:
            code_files[file_path] = {"language": language, "code": code}
            log(f"提取文件: {file_path} ({language})")

    return service_name, error_log, code_files

def assess_risk(title, body):
    """风险评估"""
    text = (title + " " + body).lower()
    hits = [kw for kw in CRITICAL_KEYWORDS if kw in text]
    if hits:
        return "CRITICAL", f"检测到敏感关键词: {hits}"
    if "restart loop" in text or "崩溃" in text:
        return "HEAVY", "检测到循环崩溃"
    return "NORMAL", "常规错误"

# ================= 2. AI 调用封装 =================

def call_qwen(prompt):
    """调用通义千问"""
    if not QWEN_KEY:
        log("QWEN_KEY 未设置", "WARN")
        return None
    try:
        headers = {"Authorization": f"Bearer {QWEN_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": QWEN_MODEL,
            "input": {"messages": [{"role": "user", "content": prompt}]},
            "parameters": {"result_format": "message"}
        }
        resp = requests.post(QWEN_BASE, headers=headers, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["output"]["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"Qwen 调用失败: {e}", "ERROR")
        return None

def call_gemini(prompt, model=GEMINI_MODEL):
    """调用 Gemini"""
    if not GEMINI_KEY:
        log("GEMINI_KEY 未设置", "ERROR")
        return None
    try:
        url = f"{GEMINI_BASE}/{model}:generateContent?key={GEMINI_KEY}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log(f"Gemini 调用失败: {e}", "ERROR")
        return None

def clean_code(text, lang):
    """清理 AI 返回的代码"""
    # 提取 Markdown 代码块
    pattern = r'```(?:' + lang + r'|python|js|javascript)?\s*\n(.*?)\n```'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 如果没有代码块，尝试直接清洗
    text = re.sub(r'^```.*?\n', '', text)
    text = re.sub(r'\n```$', '', text)
    return text.strip()

def validate_code(code, language):
    """语法验证"""
    if 'python' in language or language == 'py':
        try:
            compile(code, '<string>', 'exec')
            return True, "语法正确"
        except SyntaxError as e:
            return False, f"Python SyntaxError: {e}"
    # JS 简单检查
    if 'script' in language or language == 'js':
        if code.count('{') != code.count('}'):
            return False, "JS 括号不匹配"
    return True, "验证通过"

# ================= 3. 仲裁核心逻辑 =================

def arbitrate_fix(file_path, original_code, error_log, language):
    """对单个文件执行双AI修复与仲裁"""
    log(f"正在修复: {file_path}...", "AI")
    
    prompt_base = f"""
    【任务】修复代码错误
    【文件】{file_path}
    【语言】{language}
    【错误日志】
    {error_log[:1500]}
    
    【原始代码】
    {original_code}
    
    请输出修复后的完整代码。只输出代码，不要解释。
    """

    # 1. 双AI 并行生成
    log("请求 Qwen...", "AI")
    sol_qwen = call_qwen(prompt_base)
    
    log("请求 Gemini...", "AI")
    sol_gemini = call_gemini(prompt_base)
    
    if not sol_qwen and not sol_gemini:
        return None, "所有 AI 均失败"

    # 2. Gemini Leader 仲裁
    log("Gemini Leader 正在仲裁...", "JUDGE")
    judge_prompt = f"""
    你是首席架构师。针对文件 {file_path} 的错误，两个 AI 提供了方案。
    
    【原始错误】{error_log[:500]}
    
    【方案 A (Qwen)】
    {sol_qwen if sol_qwen else "未响应"}
    
    【方案 B (Gemini)】
    {sol_gemini if sol_gemini else "未响应"}
    
    请：
    1. 评估哪个方案更安全、更有效。
    2. 如果两个都有问题，请基于两者重写最优代码。
    3. 输出最终代码和简短理由。
    
    输出格式要求：
    Reason: [一句话理由]
    Code:
    ```
    [最终代码]
    ```
    """
    
    verdict = call_gemini(judge_prompt, model=GEMINI_JUDGE)
    if not verdict:
        verdict = sol_gemini or sol_qwen # 降级处理
    
    # 提取最终代码
    final_code = clean_code(verdict, language)
    
    # 验证
    is_valid, msg = validate_code(final_code, language)
    if not is_valid:
        log(f"仲裁代码验证失败: {msg}", "ERROR")
        # 尝试回退到方案B或A
        if sol_gemini and validate_code(clean_code(sol_gemini, language), language)[0]:
            return clean_code(sol_gemini, language), "仲裁失败，回退到 Gemini 方案"
        return None, f"修复失败: {msg}"
        
    return final_code, verdict

# ================= 主程序 =================

def main():
    log("=" * 50)
    log("🤖 双AI仲裁修复系统 v3.0 启动")
    log("=" * 50)

    if not ISSUE_BODY:
        log("没有 Issue 内容，退出", "ERROR")
        sys.exit(1)

    # 1. 风险评估
    risk, reason = assess_risk(ISSUE_TITLE, ISSUE_BODY)
    log(f"风险等级: {risk} | {reason}")
    
    if risk in ["CRITICAL", "HEAVY"]:
        with open("human_review_needed.txt", "w", encoding="utf-8") as f:
            f.write(f"Level: {risk}\nReason: {reason}")
        log("触发人工审查，停止自动修复", "WARN")
        sys.exit(0)

    # 2. 解析 Issue
    service_name, error_log, code_files = parse_issue_content(ISSUE_BODY, ISSUE_TITLE)
    if not code_files:
        log("未找到代码文件，无法修复", "ERROR")
        sys.exit(1)

    # 3. 遍历修复
    fixed_files = {}
    report_content = f"# 🤖 AI 修复报告\nIssue: #{ISSUE_NUMBER}\n\n"
    
    for path, info in code_files.items():
        code, justification = arbitrate_fix(path, info['code'], error_log, info['language'])
        
        if code:
            fixed_files[path] = code
            report_content += f"## 文件: `{path}`\n\n**仲裁结果**: \n{justification[:500]}...\n\n---\n"
        else:
            report_content += f"## 文件: `{path}`\n\n❌ 修复失败\n\n---\n"

    # 4. 写入文件 (原位覆盖)
    service_dir = SERVICE_DIRS.get(service_name, service_name)
    write_count = 0
    
    for path, code in fixed_files.items():
        # 组合完整路径：如果是已知服务，加上前缀；否则假设是相对路径
        # 注意：这里需要根据实际仓库结构微调，这里假设 issue 里的 path 是相对路径
        if service_name != "unknown" and not path.startswith(service_dir):
            full_path = os.path.join(service_dir, path)
        else:
            full_path = path
            
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(code)
            log(f"已写入: {full_path}", "OK")
            write_count += 1
        except Exception as e:
            log(f"写入失败 {full_path}: {e}", "ERROR")

    # 5. 保存报告供 PR 使用
    with open("AI_REVIEW_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_content)
        
    if write_count > 0:
        log(f"成功修复 {write_count} 个文件", "OK")
    else:
        log("未能写入任何修复", "ERROR")
        sys.exit(1)

if __name__ == "__main__":
    main()
