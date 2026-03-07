import os
import json
import requests
import sys
import glob

# ——————————————————————————————————————————————————————————————————————
# 配置与常量
# ——————————————————————————————————————————————————————————————————————
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER")
ISSUE_TITLE = os.environ.get("ISSUE_TITLE")
ISSUE_BODY = os.environ.get("ISSUE_BODY")
REPO_NAME = os.environ.get("GITHUB_REPOSITORY")

# 修正后的模型标识符
GEMINI_MODEL = "gemini-1.5-flash"  # 建议使用 flash，响应快且稳
QWEN_MODEL = "qwen-turbo"

# ——————————————————————————————————————————————————————————————————————
# 工具函数
# ——————————————————————————————————————————————————————————————————————

def get_project_files():
    """获取上下文代码"""
    context = ""
    # 扩大搜索范围，排除干扰项
    files = glob.glob("**/*.py", recursive=True) + glob.glob("**/*.js", recursive=True) + glob.glob("**/*.go", recursive=True)
    count = 0
    for f in files:
        if any(x in f for x in ["node_modules", "venv", ".git", "__pycache__"]): continue
        if count > 10: break # 限制文件数
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                if len(content) < 5000:
                    context += f"\n--- File: {f} ---\n{content}\n"
                    count += 1
        except:
            pass
    return context

def call_qwen(prompt, system_prompt="You are a helpful coding assistant."):
    """调用通义千问 API"""
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=60)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ Qwen API Error: {e}")
        return "Error: Qwen failed to generate solution."

def call_gemini(prompt, system_instruction=None, is_json=False):
    """
    调用 Google Gemini API
    is_json: 如果为 True，强制模型返回 JSON 格式
    """
    # 确保 URL 格式正确，使用 v1beta
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1, # 降低随机性
        }
    }
    
    if is_json:
        # 强制输出 JSON 格式，这是解决解析错误的最高级手段
        payload["generationConfig"]["response_mime_type"] = "application/json"
    
    if system_instruction:
        payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code != 200:
            print(f"❌ Gemini API Error: {resp.status_code}")
            print(f"Details: {resp.text}")
            return None
        
        result = resp.json()
        return result['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f"❌ Gemini Exception: {e}")
        return None

# ——————————————————————————————————————————————————————————————————————
# 主逻辑
# ——————————————————————————————————————————————————————————————————————

def main():
    if not GEMINI_API_KEY or not QWEN_API_KEY:
        print("❌ 错误: 缺少 API Key 配置")
        sys.exit(1)

    print(f"🚀 开始处理 Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}")
    
    code_context = get_project_files()
    
    base_prompt = f"""
Context (Project Files Snippets):
{code_context}

The Issue:
Title: {ISSUE_TITLE}
Description: {ISSUE_BODY}

Task:
Provide a technical fix for this issue. 
1. Analyze the root cause.
2. Provide the corrected full code for the specific file(s).
3. Explain your changes.
"""

    # 1. 生成两个方案
    print("🤖 正在请求 Qwen 生成方案 (Plan A)...")
    plan_a = call_qwen(base_prompt, "You are an expert developer. Provide a specific and robust fix.")
    
    print("🤖 正在请求 Gemini 生成方案 (Plan B)...")
    plan_b = call_gemini(base_prompt, "You are a senior developer. Provide a clean, secure fix.")
    
    if not plan_a and not plan_b:
        print("❌ 两个模型均未生成有效方案。")
        sys.exit(1)

    # 2. 仲裁阶段
    print("⚖️ 进入仲裁阶段 (Gemini Leader)...")
    
    arbitration_prompt = f"""
Compare the following two solutions for Issue: "{ISSUE_TITLE}"

=== SOLUTION A (Qwen) ===
{plan_a}

=== SOLUTION B (Gemini) ===
{plan_b}

--- TASK ---
1. Evaluate Logic, Security, and Completeness.
2. Pick the winner ('A' or 'B').
3. Output the result in STRICT JSON format.

--- REQUIRED JSON STRUCTURE ---
{{
    "winner": "A" or "B" or "NONE",
    "analysis_a": "critique",
    "analysis_b": "critique",
    "comparison": "reasoning",
    "risk_level": "LOW/MEDIUM/HIGH",
    "human_review_required": false,
    "final_solution_code": {{
         "relative/path/to/file.ext": "FULL CODE CONTENT"
    }},
    "pr_report_markdown": "Detailed Markdown summary"
}}
"""
    
    # 使用 is_json=True 强制输出纯 JSON
    verdict_raw = call_gemini(arbitration_prompt, "You are a CTO and code arbitrator. Output ONLY JSON.", is_json=True)
    
    if not verdict_raw:
        print("❌ 仲裁者未能返回结果。")
        sys.exit(1)

    try:
        verdict = json.loads(verdict_raw)
    except json.JSONDecodeError:
        # 最后的兜底：尝试手动清洗 Markdown
        print("⚠️ JSON 直接解析失败，尝试清洗补救...")
        verdict_clean = verdict_raw.replace("```json", "").replace("```", "").strip()
        try:
            verdict = json.loads(verdict_clean)
        except:
            print("❌ 仲裁数据解析彻底失败。")
            print(verdict_raw)
            sys.exit(1)

    # 3. 处理仲裁结果
    if verdict.get("winner") == "NONE" or verdict.get("human_review_required") == True:
        reason = verdict.get("comparison", "AI 判定需要人工介入")
        print(f"🛑 拦截：需要人工审查。原因: {reason}")
        with open("human_review_needed.txt", "w", encoding="utf-8") as f:
            f.write(reason)
        sys.exit(0)

    # 4. 应用代码更改
    winner = verdict.get("winner")
    print(f"🏆 获胜方案: {winner}")
    
    files_to_fix = verdict.get("final_solution_code", {})
    if not files_to_fix:
        print("⚠️ 方案获胜但未检测到待修改的代码文件。")
        sys.exit(0)

    for filepath, content in files_to_fix.items():
        if ".github" in filepath or "/" not in filepath and filepath.endswith(".md"):
            continue # 简单安全过滤
            
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
        print(f"✏️ 正在写入文件: {filepath}")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    # 5. 生成报告
    with open("AI_REVIEW_REPORT.md", "w", encoding="utf-8") as f:
        f.write(verdict.get("pr_report_markdown", "# AI 自动修复报告\n无法生成详细描述"))
    
    print("✅ 修复脚本执行完成。")

if __name__ == "__main__":
    main()
