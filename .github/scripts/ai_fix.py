import os
import json
import requests
import sys
import glob
import re

# ——————————————————————————————————————————————————————————————————————
# 1. 配置与常量
# ——————————————————————————————————————————————————————————————————————
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER")
ISSUE_TITLE = os.environ.get("ISSUE_TITLE")
ISSUE_BODY = os.environ.get("ISSUE_BODY")
REPO_NAME = os.environ.get("GITHUB_REPOSITORY")
COMMENT_BODY = os.environ.get("COMMENT_BODY", "")

GEMINI_MODEL = "gemini-1.5-flash"
QWEN_MODEL = "qwen-turbo"

# ——————————————————————————————————————————————————————————————————————
# 2. 工具函数
# ——————————————————————————————————————————————————————————————————————

def get_project_context():
    """获取项目代码上下文"""
    context = ""
    files = []
    # 查找常见代码文件
    for ext in ["py", "js", "go", "ts", "php", "java", "yml", "yaml"]:
        files.extend(glob.glob(f"**/*.{ext}", recursive=True))
    
    count = 0
    for f in files:
        # 过滤干扰项
        if any(x in f for x in ["node_modules", ".git", "venv", "__pycache__", "dist"]):
            continue 
        if count >= 15: 
            break # 达到上下文上限
            
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                if 0 < len(content) < 10000:
                    context += f"\n--- File: {f} ---\n{content}\n"
                    count += 1
        except: pass
    return context

def call_qwen(prompt):
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": "You are a senior developer. Return only code fixes."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ Qwen API Error: {e}")
        return None

def call_gemini(prompt, is_json=False):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1}
    }
    if is_json:
        payload["generationConfig"]["response_mime_type"] = "application/json"
    
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code != 200:
            print(f"❌ Gemini Error: {resp.status_code} - {resp.text}")
            return None
        return resp.json()['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f"❌ Gemini Exception: {e}")
        return None

def post_comment(text):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{ISSUE_NUMBER}/comments"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, headers=headers, json={"body": text})

def apply_code_changes(files_dict):
    """安全应用代码更改"""
    if not files_dict: return False
    
    success = False
    for path, content in files_dict.items():
        # 🛡️ 安全过滤：禁止通过 AI 修改工作流、环境变量或敏感目录
        if any(x in path.lower() for x in [".github/", ".env", "secrets", "config/"]):
            print(f"⚠️ 拒绝修改敏感文件: {path}")
            continue
            
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            print(f"✅ 写入成功: {path}")
            success = True
    return success

# ——————————————————————————————————————————————————————————————————————
# 3. 核心逻辑
# ——————————————————————————————————————————————————————————————————————

def main():
    # 检测人工指令 (/apply A, /apply B, /apply HYBRID)
    cmd_match = re.search(r'/apply\s+(A|B|HYBRID)', COMMENT_BODY.upper())
    
    if cmd_match:
        choice = cmd_match.group(1)
        print(f"🎯 接收到指令: {choice}。正在提取代码并应用...")
        code_context = get_project_context()
        
        # 强化 JSON 格式要求，避免单引号问题
        force_prompt = f"""
Based on this context:
{code_context}

The issue is: {ISSUE_TITLE}

Task: Use the "{choice}" strategy to fix the issue.
Return a STRICT JSON object where keys are file paths and values are the FULL file content.
Example: {{"path/to/file.py": "content..."}}
"""
        verdict_raw = call_gemini(force_prompt, is_json=True)
        try:
            files = json.loads(verdict_raw)
            if apply_code_changes(files):
                post_comment(f"✅ **已手动应用方案 {choice}**。\n已创建修复代码并准备提交。")
                with open("FIX_DONE", "w") as f: f.write("SUCCESS")
            sys.exit(0)
        except Exception as e:
            print(f"❌ 解析失败: {e}")
            sys.exit(1)

    # 标准分析流程
    print("🚀 启动 AI 自动分析流程...")
    code_context = get_project_context()
    base_prompt = f"Context:\n{code_context}\n\nIssue: {ISSUE_TITLE}\n{ISSUE_BODY}\n\nProvide a full code fix."
    
    plan_a = call_qwen(base_prompt)
    plan_b = call_gemini(base_prompt)

    if not plan_a and not plan_b:
        post_comment("❌ AI 服务暂时不可用，请稍后再试。")
        sys.exit(1)

    arbitration_prompt = f"""
Compare these solutions for: {ISSUE_TITLE}

PLAN A: {plan_a}
PLAN B: {plan_b}

Decision Rules:
1. Pick "A" or "B" or "HYBRID". 
2. If both are dangerous/bad, pick "NONE".
3. Provide the result in JSON.

{{
  "winner": "A" | "B" | "HYBRID" | "NONE",
  "reason": "explanation",
  "files": {{ "path/to/file": "full content" }},
  "report": "markdown summary"
}}
"""
    verdict_raw = call_gemini(arbitration_prompt, is_json=True)
    try:
        verdict = json.loads(verdict_raw)
    except:
        post_comment("⚠️ AI 决策结果解析失败，请人工介入。")
        sys.exit(1)

    winner = verdict.get("winner")
    if winner in ["A", "B", "HYBRID"]:
        if apply_code_changes(verdict.get("files", {})):
            report = f"### 🤖 AI 自动修复报告 (方案: {winner})\n\n**决策依据**: {verdict.get('reason')}\n\n{verdict.get('report')}"
            post_comment(report)
            with open("FIX_DONE", "w") as f: f.write("SUCCESS")
    else:
        # 提供人工指令选项
        msg = f"""
### ⚖️ AI 无法自动决策
Leader 认为当前方案需要人工复核。

**理由**: {verdict.get('reason', '不确定的变更风险')}

**请审查下方代码并回复指令**:
- `/apply A` : 采用 Qwen 方案
- `/apply B` : 采用 Gemini 方案
- `/apply HYBRID` : 采用 AI 综合方案

<details><summary>方案 A 预览 (Qwen)</summary>\n\n```\n{plan_a}\n```\n</details>
<details><summary>方案 B 预览 (Gemini)</summary>\n\n```\n{plan_b}\n```\n</details>
"""
        post_comment(msg)

if __name__ == "__main__":
    main()
