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

# 模型配置
GEMINI_MODEL = "gemini-2.0-flash" # 使用 Pro 模型进行逻辑仲裁更强
QWEN_MODEL = "qwen-turbo"       # 或 qwen-max

# ——————————————————————————————————————————————————————————————————————
# 工具函数
# ——————————————————————————————————————————————————————————————————————

def get_project_files():
    """获取当前目录下主要的 Python/JS/MD 文件内容，提供上下文"""
    context = ""
    # 简单遍历，限制大小以防 Token 溢出
    files = glob.glob("**/*.py", recursive=True) + glob.glob("**/*.js", recursive=True)
    for f in files[:5]: # 限制读取文件数量
        if "node_modules" in f or "venv" in f: continue
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                if len(content) < 2000: # 只读取较小的文件
                    context += f"\n--- File: {f} ---\n{content}\n"
        except:
            pass
    return context

def call_qwen(prompt, system_prompt="You are a helpful coding assistant."):
    """调用通义千问 API (OpenAI 兼容格式 或 DashScope 原生)"""
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
        return "Error generating solution."

def call_gemini(prompt, system_instruction=None):
    """调用 Google Gemini API"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    # Gemini 1.5 支持 system_instruction
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    
    if system_instruction:
        payload["system_instruction"] = {"parts": [{"text": system_instruction}]}

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        return result['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        if resp.text: print(f"Details: {resp.text}")
        return "Error generating solution."

# ——————————————————————————————————————————————————————————————————————
# 主逻辑
# ——————————————————————————————————————————————————————————————————————

def main():
    print(f"🚀 开始处理 Issue #{ISSUE_NUMBER}: {ISSUE_TITLE}")
    
    # 1. 获取代码上下文
    code_context = get_project_files()
    
    # 2. 构建基础提示词
    base_prompt = f"""
    Context (Project Files Snippets):
    {code_context}
    
    The Issue:
    Title: {ISSUE_TITLE}
    Description: {ISSUE_BODY}
    
    Task:
    Provide a fix for this issue. 
    1. Analyze the problem.
    2. Provide the corrected full code for the specific file(s).
    3. Explain your changes briefly.
    """

    # ————————————————————————————————————————————————
    # 3. 双 AI 生成方案
    # ————————————————————————————————————————————————
    print("🤖 正在请求 Qwen 生成方案 (Plan A)...")
    plan_a = call_qwen(base_prompt, system_prompt="You are an expert Python developer. Provide a robust fix.")
    
    print("🤖 正在请求 Gemini 生成方案 (Plan B)...")
    plan_b = call_gemini(base_prompt, system_instruction="You are a senior code reviewer and developer. Provide a clean, secure fix.")

    # ————————————————————————————————————————————————
    # 4. Gemini 仲裁 (Leader Role)
    # ————————————————————————————————————————————————
    print("⚖️ 进入仲裁阶段 (Gemini Leader)...")
    
    arbitration_prompt = f"""
    You are the Chief Technology Officer (CTO) and final arbitrator.
    
    We have an Issue: "{ISSUE_TITLE}"
    
    Two AI developers have proposed solutions:
    
    === SOLUTION A (by Qwen) ===
    {plan_a}
    
    === SOLUTION B (by Gemini) ===
    {plan_b}
    
    --- YOUR TASK ---
    1. Compare Solution A and Solution B critically.
    2. Analyze Logic, Security, Performance, and Code Style.
    3. Decide the WINNER (A or B). If both are bad or dangerous, reject both.
    4. Provide a DETAILED reasoning for the Pull Request description.
    
    --- OUTPUT FORMAT (Strict JSON) ---
    You MUST output valid JSON only. Do not wrap in markdown code blocks. Structure:
    {{
        "analysis_a": "Detailed critique of A (pros/cons)",
        "analysis_b": "Detailed critique of B (pros/cons)",
        "comparison": "Why is one better than the other?",
        "risk_level": "LOW", "MEDIUM", or "HIGH",
        "human_review_required": boolean (true if HIGH risk or core logic change),
        "winner": "A" or "B" or "NONE",
        "rejection_reason": "If winner is NONE, explain why",
        "final_solution_code": {{
             "filename.ext": "FULL CORRECTED CODE CONTENT HERE"
        }},
        "pr_report_markdown": "A well-formatted markdown text summarizing the decision, suitable for PR body."
    }}
    """
    
    verdict_raw = call_gemini(arbitration_prompt, system_instruction="You are a JSON-speaking strict code arbitrator.")
    
    # 清理 Gemini 可能返回的 Markdown 标记 ```json ... ```
    verdict_clean = verdict_raw.replace("```json", "").replace("```", "").strip()
    
    try:
        verdict = json.loads(verdict_clean)
    except json.JSONDecodeError:
        print("❌ JSON 解析失败，仲裁者返回了非结构化数据。")
        print(verdict_raw)
        sys.exit(1)

    # ————————————————————————————————————————————————
    # 5. 执行仲裁结果
    # ————————————————————————————————————————————————
    
    # 检查是否需要人工审查
    if verdict.get("human_review_required") or verdict.get("risk_level") == "HIGH" or verdict.get("winner") == "NONE":
        reason = verdict.get("rejection_reason") or verdict.get("comparison")
        print(f"🛑 触发人工审查拦截: {reason}")
        with open("human_review_needed.txt", "w", encoding="utf-8") as f:
            f.write(reason)
        sys.exit(0) # 退出脚本，后续 Workflow 步骤会处理

    # 写入代码文件
    print(f"🏆 获胜者: 方案 {verdict['winner']}")
    changes = verdict.get("final_solution_code", {})
    
    if not changes:
        print("⚠️ 获胜但未提供代码，转人工。")
        with open("human_review_needed.txt", "w") as f: f.write("AI selected a winner but failed to output code structure.")
        sys.exit(0)

    for filename, content in changes.items():
        # 简单的安全检查：防止写入 .github 目录
        if ".github" in filename:
            print(f"⚠️ 跳过写入敏感文件: {filename}")
            continue
            
        # 确保目录存在
        os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else ".", exist_ok=True)
        
        print(f"✏️ 正在写入文件: {filename}")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)

    # ————————————————————————————————————————————————
    # 6. 生成详细报告 (用于 PR Body)
    # ————————————————————————————————————————————————
    report_content = f"""
# 🤖 AI 仲裁修复报告

> **Issue**: #{ISSUE_NUMBER} {ISSUE_TITLE}

## ⚖️ 仲裁结果
- 🟦 **方案 A (Qwen)**: {verdict['analysis_a']}
- 🟩 **方案 B (Gemini)**: {verdict['analysis_b']}

### 🏆 最终裁决：方案 {verdict['winner']} 胜出

**推理过程**:
{verdict['comparison']}

## 🛡️ 风险评估
- **风险等级**: {verdict['risk_level']}
- **人工复核**: {'需要' if verdict['human_review_required'] else '无需'}

---
*Generated by Dual-AI Arbitration Workflow (Qwen + Gemini)*
    """
    
    # 如果 JSON 中 AI 自己生成了更好的 Markdown，则优先使用
    if verdict.get("pr_report_markdown"):
         report_content = verdict["pr_report_markdown"] + "\n\n---\n*Automated by Dual-AI System*"

    with open("AI_REVIEW_REPORT.md", "w", encoding="utf-8") as f:
        f.write(report_content)
    
    print("✅ 修复脚本执行完成。")

if __name__ == "__main__":
    main()
