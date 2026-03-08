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

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODELS = [
    m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "gemini-2.0-flash,gemini-1.5-pro").split(",")
    if m.strip()
]
QWEN_MODEL = "qwen-turbo"

# ==========================================
# 2. 工具函数
# ==========================================
def robust_json_decode(text):
    """多层 JSON 提取，兼容 AI 的不同输出格式。"""
    if not text:
        return None
    # 第 1 层：直接尝试 JSON 解析
    try:
        return json.loads(text)
    except Exception:
        pass
    # 第 2 层：去掉 Markdown 代码块后再解析
    try:
        cleaned = re.sub(r'```[a-zA-Z]*\n?', '', text)
        cleaned = re.sub(r'\n?```', '', cleaned).strip()
        return json.loads(cleaned)
    except Exception:
        pass
    # 第 3 层：截取首个 { 到最后一个 } 的片段解析
    try:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
    except Exception as e:
        print(f"JSON 解析失败（第 3 层）: {e}")
    return None

def get_context():
    """获取项目上下文，限制扫描数量以防止 Token 过长。"""
    context = ""
    files = []
    for ext in ["py", "js", "go", "ts", "yml", "yaml", "html", "sh", "java", "cpp"]:
        files.extend(glob.glob(f"**/*.{ext}", recursive=True))

    count = 0
    for f in sorted(files):
        if any(x in f for x in [".git", "node_modules", "venv", "__pycache__", "dist", "build"]):
            continue
        if count >= 15:
            break
        try:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                if 0 < len(content) < 8000:
                    context += f"\n--- File: {f} ---\n{content}\n"
                    count += 1
        except Exception:
            pass
    return context

def call_qwen(prompt):
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {QWEN_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": QWEN_MODEL,
        "messages": [
            {"role": "system", "content": "You are a senior software engineer. Always respond with valid JSON only, no markdown, no explanation outside JSON."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=90)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Qwen 调用失败: {e}")
        return None

def _extract_gemini_text(resp_json):
    candidates = resp_json.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        text_parts = []
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                text_parts.append(part["text"])
        if text_parts:
            return "".join(text_parts)
    return None

def call_gemini(prompt, is_json=False):
    if not GEMINI_API_KEY:
        print("Gemini 调用失败: GEMINI_API_KEY 未设置")
        return None

    max_prompt_chars = int(os.environ.get("GEMINI_MAX_PROMPT_CHARS", "120000"))
    if len(prompt) > max_prompt_chars:
        print(f"Gemini 提示词过长，已截断: {len(prompt)} -> {max_prompt_chars}")
        prompt = prompt[:max_prompt_chars]

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    if is_json:
        # Gemini 接口要求这里使用驼峰字段名
        payload["generationConfig"]["responseMimeType"] = "application/json"

    models = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]
    api_versions = ["v1beta", "v1"]
    last_error = "未知错误"

    for model in models:
        for api_version in api_versions:
            url = f"https://generativelanguage.googleapis.com/{api_version}/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                resp = requests.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=90
                )
            except Exception as e:
                last_error = str(e)
                print(f"Gemini 调用失败 (model={model}, api={api_version}): {e}")
                continue

            if resp.status_code >= 400:
                body_preview = (resp.text or "")[:800].replace("\n", " ")
                last_error = f"HTTP {resp.status_code}: {body_preview}"
                print(f"Gemini 调用失败 (model={model}, api={api_version}) -> {last_error}")
                continue

            try:
                data = resp.json()
            except Exception as e:
                body_preview = (resp.text or "")[:500].replace("\n", " ")
                last_error = f"Gemini 返回非 JSON: {e}, body={body_preview}"
                print(f"Gemini 调用失败 (model={model}, api={api_version}): {last_error}")
                continue

            text = _extract_gemini_text(data)
            if text:
                return text

            prompt_feedback = data.get("promptFeedback") or {}
            block_reason = prompt_feedback.get("blockReason")
            if block_reason:
                last_error = f"被拦截: {block_reason}"
                print(f"Gemini 响应被拦截 (model={model}, api={api_version}): {block_reason}")
                continue

            last_error = f"响应中未包含文本: {str(data)[:500]}"
            print(f"Gemini 调用失败 (model={model}, api={api_version}): {last_error}")

    print(f"Gemini 全部尝试失败: {last_error}")
    return None
def post_comment(text):
    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{ISSUE_NUMBER}/comments"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
    try:
        requests.post(url, headers=headers, json={"body": text})
    except Exception as e:
        print(f"评论发布失败: {e}")

def apply_code(files_dict):
    """
    安全地将 AI 返回代码写入本地文件。
    期望格式: {"真实相对路径": "完整文件内容", ...}
    返回: (是否成功, 说明信息)
    """
    if not files_dict:
        return False, "未在 AI 响应中找到有效代码载荷（为空或 JSON 无效）。"

    # 检测是否是错误的占位符格式 {"path": "...", "content": "..."}
    if "path" in files_dict and "content" in files_dict and len(files_dict) == 2:
        # AI 把模板字段名当成真实字段，尝试自动修复
        real_path = files_dict.get("path", "").strip()
        real_content = files_dict.get("content", "").strip()
        if real_path and real_content and "/" in real_path:
            print(f"检测到占位符格式，已自动修复: path={real_path}")
            files_dict = {real_path: real_content}
        else:
            return False, f"AI 返回了错误的占位符格式 {{\"path\": ..., \"content\": ...}}，无法识别真实文件路径。原始 path 值: '{real_path}'"

    applied_count = 0
    filtered_count = 0
    skipped_paths = []

    for path, content in files_dict.items():
        # 安全检查：禁止 AI 修改工作流配置
        if ".github" in path:
            filtered_count += 1
            skipped_paths.append(path)
            print(f"安全过滤: {path}")
            continue
        # 路径安全检查：阻止路径穿越
        if path.startswith("/") or ".." in path:
            filtered_count += 1
            skipped_paths.append(path)
            print(f"路径穿越拦截: {path}")
            continue
        try:
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"写入成功: {path}")
            applied_count += 1
        except Exception as e:
            print(f"写入失败 {path}: {e}")

    if applied_count > 0:
        return True, f"成功写入 {applied_count} 个文件。"
    elif filtered_count > 0:
        return False, f"{filtered_count} 个文件均被安全策略拦截（路径: {', '.join(skipped_paths)}）。"
    else:
        return False, "没有任何文件被写入。"

# ==========================================
# 3. 主流程逻辑
# ==========================================
def main():
    # 检测人工一键修复指令 (/apply A | /apply B | /apply HYBRID)
    cmd = re.search(r'/apply\s+(A|B|HYBRID)', COMMENT_BODY, re.IGNORECASE)

    if cmd:
        choice = cmd.group(1).upper()
        print(f"收到人工强制指令: /apply {choice}")
        ctx = get_context()

        # 修复点：明确 JSON 输出格式，避免 AI 返回占位符
        prompt = f"""You are fixing a bug reported in a GitHub Issue.

Issue Title: {ISSUE_TITLE}

Project Context:
{ctx}

Task: Apply fix strategy "{choice}". 
Output ONLY a valid JSON object where:
- Keys are REAL relative file paths (e.g. "pb/pb_hooks/fatal_error.js")  
- Values are the COMPLETE new file contents as strings

Example of correct output format:
{{
  "pb/pb_hooks/fatal_error.js": "// complete fixed file content here\\nconst x = 1;",
  "pb/some_other_file.js": "// another file content"
}}

Do NOT use placeholder keys like "path" or "content". Use actual file paths."""

        # 修复点：/apply A 调用 Qwen，/apply B 调用 Gemini
        if choice == "A":
            raw = call_qwen(prompt)
            model_used = "Qwen"
        else:
            raw = call_gemini(prompt, is_json=True)
            model_used = "Gemini"

        print(f"[{model_used}] 原始返回:\n{raw[:500] if raw else 'None'}")

        files = robust_json_decode(raw)
        print(f"解析后 files_dict: {list(files.keys()) if files else 'None'}")

        success, msg = apply_code(files)
        if success:
            post_comment(f"✅ **指令执行成功**：已应用方案 **{choice}**（{model_used}），正在为您准备 Pull Request。\n\n> {msg}")
            with open("FIX_DONE", "w") as f:
                f.write("SUCCESS")
        else:
            raw_preview = str(raw)[:300] if raw else "无响应"
            post_comment(f"执行失败：{msg}\n\n> 模型: {model_used}\n> 原始返回片段: `{raw_preview}`")
        return

    # ==========================================
    # 自动流程：双 AI 方案生成 + Gemini 仲裁
    # ==========================================
    print("启动 AI 对抗生成流程...")
    ctx = get_context()

    base_prompt = f"""You are a senior engineer fixing a GitHub Issue.

Issue Title: {ISSUE_TITLE}
Issue Body: {ISSUE_BODY}

Project Context:
{ctx}

Task: Provide a complete fix for this issue.
Output a clear explanation of your approach and the fixed code."""

    plan_a = call_qwen(base_prompt) or "Qwen 方案生成失败"
    plan_b = call_gemini(base_prompt) or "Gemini 方案生成失败"

    arbitrate_prompt = f"""You are a CTO reviewing two code fixes for a GitHub Issue.

Issue: {ISSUE_TITLE}

PLAN A (Qwen):
{plan_a}

PLAN B (Gemini):
{plan_b}

Evaluate both plans and output ONLY valid JSON (no markdown, no explanation outside JSON):
{{
  "winner": "A or B or HYBRID or NONE",
  "reason": "brief reason for your choice",
  "files": {{
    "actual/relative/path/to/file.js": "complete file content as string"
  }},
  "report": "detailed markdown comparison"
}}

IMPORTANT for "files":
- Keys MUST be real relative file paths, NOT placeholder words like "path" or "content"
- Values MUST be complete file contents
- If winner is NONE, use empty object: {{}}"""

    raw_verdict = call_gemini(arbitrate_prompt, is_json=True)
    print(f"[Gemini 仲裁] 原始返回:\n{raw_verdict[:500] if raw_verdict else 'None'}")
    verdict = robust_json_decode(raw_verdict)

    if verdict and verdict.get("winner") in ["A", "B", "HYBRID"]:
        winner = verdict["winner"]
        success, msg = apply_code(verdict.get("files", {}))
        if success:
            post_comment(f"""### 🤖 AI 自动修复结论（{winner}）
**决策依据**: {verdict.get('reason')}

**修复报告**:
{verdict.get('report')}

---
*提示：如不满意，可回复 `/apply A` 或 `/apply B` 强制切换方案。*""")
            with open("FIX_DONE", "w") as f:
                f.write("SUCCESS")
            return
        else:
            print(f"自动应用方案 {winner} 写入失败: {msg}。已降级为人工选择模式。")

    # 降级：展示双方案供人工选择
    fallback_msg = f"""### ⚠️ AI 仲裁未自动应用
系统无法自动部署最佳方案（或选定方案被安全策略拦截）。请查看下方详细对比并进行人工选择。
#### 🛠 一键修复选项
回复以下指令以强制应用对应方案：
- `/apply A` : 应用 Qwen 修复方案
- `/apply B` : 应用 Gemini 修复方案

---
#### 🔵 方案详情对比

<details><summary>📳 查看方案 A（Qwen）源码</summary>

{plan_a}

</details>

<details><summary>📳 查看方案 B（Gemini）源码</summary>

{plan_b}

</details>"""
    post_comment(fallback_msg)


if __name__ == "__main__":
    main()

