import os
import json
import requests
import sys
import glob
import re

# ==========================================
# 1. 配置与环境变量
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER")
ISSUE_TITLE = os.environ.get("ISSUE_TITLE")
ISSUE_BODY = os.environ.get("ISSUE_BODY")
REPO_NAME = os.environ.get("GITHUB_REPOSITORY")
COMMENT_BODY = os.environ.get("COMMENT_BODY", "")

# 🐛 Bug 4 修复: 升级 Gemini 模型以提升 JSON 稳定性
GEMINI_MODEL = "gemini-2.0-flash"
QWEN_MODEL = "qwen-turbo"

# ==========================================
# 2. 增强型清洗与解析工具
# ==========================================
def robust_json_decode(text):
    """鲁棒性极强的 JSON 提取器，应对 AI 的各种乱码和 Markdown 标签"""
    if not text: return None
    try:
        # 尝试清理 Markdown 代码块
        text = re.sub(r'```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'\s*```', '', text)
        # 寻找第一个 { 和最后一个 }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])
        return json.loads(text)
    except Exception as e:
        print(f"JSON 解析失败: {e}")
        return None

def get_context():
    """获取项目上下文，限制扫描数量以防 Token 溢出"""
    context = ""
    files = []
    for ext in["py", "js", "go", "ts", "yml", "yaml", "html", "sh", "java", "cpp"]:
        files.extend(glob.glob(f"**/*.{ext}", recursive=True))
    
    count = 0
    for f in files:
        if any(x in f for x in [".git", "node_modules", "venv", "__pycache__", "dist", "build"]):
            continue
        if count >= 15: break # 限制上下文文件数
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                if 0 < len(content) < 8000:
                    context += f"\n--- File: {f} ---\n{content}\n"
                    count += 1
        except: pass
    return context

def call_qwen(prompt):
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": QWEN_MODEL,
        "messages":[{"role": "system", "content": "You are a senior coder. Provide full file fixes."},
                     {"role": "user", "content": prompt}]
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=60)
        return resp.json()["choices"][0]["message"]["content"]
    except: return None

def call_gemini(prompt, is_json=False):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    if is_json:
        payload["generationConfig"]["response_mime_type"] = "application/json"
    try:
        resp = requests.post(url, json=payload, timeout=90)
        resp.raise_for_status()
        result = resp.json()
        candidate = result['candidates'][0]
        finish_reason = candidate.get('finishReason')
        if finish_reason not in (None, 'STOP'):
            print(f"Gemini 异常结束原因: {finish_reason}")
            return None
        return candidate['content']['parts'][0]['text']
    except Exception as e:
        print(f"Gemini 调用失败: {e}")
        return None

def post_comment(text):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{ISSUE_NUMBER}/comments"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    requests.post(url, headers=headers, json={"body": text})

# 🐛 Bug 3 修复: 改进应用机制并返回错误原因
def apply_code(files_dict):
    """安全地将代码写入本地文件，返回 (是否成功, 提示信息)"""
    if not files_dict: 
        return False, "未能提取到有效的代码（可能 AI 返回的 JSON 格式有误）。"
    
    applied_count = 0
    filtered_count = 0
    
    for path, content in files_dict.items():
        # 安全检查：禁止通过 AI 修改工作流配置
        if ".github" in path:
            filtered_count += 1
            continue
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        applied_count += 1
        
    if applied_count > 0:
        return True, f"成功应用了 {applied_count} 个文件修改。"
    elif filtered_count > 0:
        return False, f"所有 {filtered_count} 个文件修改均位于 .github/ 目录，出于安全原因已被拦截。"
    else:
        return False, "没有任何文件被应用修改。"

# ==========================================
# 3. 主程序逻辑
# ==========================================
def main():
    # 检测人工一键修复指令 (/apply A | /apply B | /apply HYBRID)
    cmd = re.search(r'/apply\s+(A|B|HYBRID)', COMMENT_BODY, re.IGNORECASE)
    
    if cmd:
        choice = cmd.group(1).upper()
        print(f"收到人工强制指令: {choice}")
        ctx = get_context()
        prompt = f"Context:\n{ctx}\n\nIssue: {ISSUE_TITLE}\nApply fix using strategy {choice}. Output strictly JSON: {{\"path\": \"content\"}}"
        
        # 🐛 Bug 2 修复: 判断分支以对应正确模型
        if choice == "A":
            raw = call_qwen(prompt)
        else:
            raw = call_gemini(prompt, is_json=True)
            
        files = robust_json_decode(raw)
        
        # 应用结果与回调
        success, msg = apply_code(files)
        if success:
            post_comment(f"✅ **指令执行成功**：已应用方案 **{choice}**，正在为您准备 Pull Request。\n*日志: {msg}*")
            with open("FIX_DONE", "w") as f: f.write("SUCCESS")
            return
        else:
            post_comment(f"❌ 执行失败：{msg}")
            return

    # 自动生成的流程
    print("🚀 启动 AI 对抗生成流程...")
    ctx = get_context()
    base_prompt = f"Context:\n{ctx}\n\nIssue: {ISSUE_TITLE}\nBody: {ISSUE_BODY}\n\nTask: Provide the full code to fix this issue."

    plan_a = call_qwen(base_prompt) or "Qwen 方案生成失败"
    plan_b = call_gemini(base_prompt) or "Gemini 方案生成失败"

    arbitrate_prompt = f"""
As a CTO, compare these two solutions for Issue: {ISSUE_TITLE}

PLAN A (Qwen): {plan_a}
PLAN B (Gemini): {plan_b}

Decision Rules:
1. Winner: A, B, HYBRID, or NONE.
2. If one is clearly better, pick it.
3. Provide full file code in JSON.

Output STRICT JSON:
{{
  "winner": "A" | "B" | "HYBRID" | "NONE",
  "reason": "summary",
  "files": {{ "path/to/file": "full content" }},
  "report": "detailed markdown analysis"
}}
"""
    raw_verdict = call_gemini(arbitrate_prompt, is_json=True)
    verdict = robust_json_decode(raw_verdict)

    if verdict and verdict.get("winner") in["A", "B", "HYBRID"]:
        winner = verdict["winner"]
        success, msg = apply_code(verdict.get("files", {}))
        if success:
            msg_body = f"""
### 🤖 AI 自动修复结论 ({winner})
**决策依据**: {verdict.get('reason')}

**修复报告**:{verdict.get('report')}

---
*提示：如不满意，可回复 `/apply A` 或 `/apply B` 强制切换方案。*
"""
            post_comment(msg_body)
            with open("FIX_DONE", "w") as f: f.write("SUCCESS")
            return
        else:
            # 文件被安全机制阻拦或无法写入
            print(f"⚠️ 自动采纳的方案 {winner} 失败：{msg}。已降级至人工选择模式。")

    # 解析失败、中立或自动写入被拦截时的降级选项
    fallback_msg = f"""
### ⚖️ AI 仲裁未自动应用
系统无法自动部署最佳方案（或选定方案的安全拦截器生效）。请查看下方详细对比进行人工选择：

#### 🛠️ 一键修复选项
回复以下指令以强制应用对应方案：
- `/apply A` : 应用 Qwen 修复方案
- `/apply B` : 应用 Gemini 修复方案

---
#### 📝 方案详情对比

<details><summary>🔍 查看 方案 A (Qwen) 源代码</summary>

{plan_a}

</details>

<details><summary>🔍 查看 方案 B (Gemini) 源代码</summary>

{plan_b}

</details>"""
    post_comment(fallback_msg)

if __name__ == "__main__":
    main()
