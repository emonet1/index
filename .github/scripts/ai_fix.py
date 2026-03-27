import glob
import json
import os
import re
from typing import Dict, List, Optional, Tuple

import requests


OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER")
ISSUE_TITLE = os.environ.get("ISSUE_TITLE", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
REPO_NAME = os.environ.get("GITHUB_REPOSITORY")
COMMENT_BODY = os.environ.get("COMMENT_BODY", "")

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4")
OPENAI_REVIEW_MODEL = os.environ.get("OPENAI_REVIEW_MODEL", OPENAI_MODEL)
OPENAI_API_URL = os.environ.get("OPENAI_API_URL", "https://api.openai.com/v1/responses")
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "").strip()
OPENAI_MAX_PROMPT_CHARS = int(os.environ.get("OPENAI_MAX_PROMPT_CHARS", "120000"))

CONTEXT_EXTENSIONS = ("py", "js", "go", "ts", "yml", "yaml", "html", "sh", "java", "cpp")
SKIP_PATH_PARTS = (".git", "node_modules", "venv", "__pycache__", "dist", "build")
MAX_CONTEXT_FILES = int(os.environ.get("MAX_CONTEXT_FILES", "15"))
MAX_CONTEXT_FILE_SIZE = int(os.environ.get("MAX_CONTEXT_FILE_SIZE", "8000"))

CODEX_SYSTEM_PROMPT = (
    "You are Codex, OpenAI's coding agent. "
    "Be precise, conservative, and repository-aware. "
    "When asked for JSON, return valid JSON only with no markdown fencing."
)


def robust_json_decode(text: Optional[str]) -> Optional[Dict[str, object]]:
    """Decode model output into a JSON object."""
    if not text:
        return None

    candidates = [text]

    cleaned = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    cleaned = re.sub(r"\n?```", "", cleaned).strip()
    if cleaned != text:
        candidates.append(cleaned)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            return data

    return None


def get_context() -> str:
    """Collect a bounded amount of repository context for the model prompt."""
    context_parts: List[str] = []
    files: List[str] = []

    for ext in CONTEXT_EXTENSIONS:
        files.extend(glob.glob(f"**/*.{ext}", recursive=True))

    for path in sorted(files):
        if any(part in path for part in SKIP_PATH_PARTS):
            continue
        try:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
        except Exception:
            continue

        if not content or len(content) >= MAX_CONTEXT_FILE_SIZE:
            continue

        context_parts.append(f"\n--- File: {path} ---\n{content}\n")
        if len(context_parts) >= MAX_CONTEXT_FILES:
            break

    return "".join(context_parts)


def _truncate_prompt(prompt: str) -> str:
    if len(prompt) > OPENAI_MAX_PROMPT_CHARS:
        print(f"Prompt truncated: {len(prompt)} -> {OPENAI_MAX_PROMPT_CHARS}")
        return prompt[:OPENAI_MAX_PROMPT_CHARS]
    return prompt


def _extract_openai_text(response_json: dict) -> Optional[str]:
    output_text = response_json.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    if isinstance(output_text, list):
        joined = "".join(part for part in output_text if isinstance(part, str))
        if joined.strip():
            return joined

    texts: List[str] = []
    for item in response_json.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content_part in item.get("content") or []:
            if not isinstance(content_part, dict):
                continue
            if content_part.get("type") == "output_text" and content_part.get("text"):
                texts.append(content_part["text"])
            elif content_part.get("type") == "refusal" and content_part.get("refusal"):
                texts.append(content_part["refusal"])

    if texts:
        return "".join(texts)

    error = response_json.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])

    return None


def call_codex(prompt: str, *, model: str, expect_json: bool = False) -> Optional[str]:
    if not OPENAI_API_KEY:
        print("Codex call skipped: OPENAI_API_KEY is not set.")
        return None

    prompt = _truncate_prompt(prompt)

    payload = {
        "model": model,
        "instructions": CODEX_SYSTEM_PROMPT,
        "input": prompt,
        "text": {"format": {"type": "text"}},
    }
    if OPENAI_REASONING_EFFORT:
        payload["reasoning"] = {"effort": OPENAI_REASONING_EFFORT}

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=90)
    except Exception as exc:
        print(f"Codex request failed: {exc}")
        return None

    if response.status_code >= 400:
        preview = (response.text or "")[:800].replace("\n", " ")
        print(f"Codex request failed: HTTP {response.status_code}: {preview}")
        return None

    try:
        response_json = response.json()
    except Exception as exc:
        preview = (response.text or "")[:500].replace("\n", " ")
        print(f"Codex response decode failed: {exc}; body={preview}")
        return None

    text = _extract_openai_text(response_json)
    if text:
        return text

    print(f"Codex response did not contain usable text: {str(response_json)[:500]}")
    return None


def post_comment(text: str) -> None:
    if not (REPO_NAME and ISSUE_NUMBER and GITHUB_TOKEN):
        print("Skip posting GitHub comment: required env vars are missing.")
        return

    url = f"https://api.github.com/repos/{REPO_NAME}/issues/{ISSUE_NUMBER}/comments"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }

    try:
        response = requests.post(url, headers=headers, json={"body": text}, timeout=30)
        if response.status_code >= 400:
            print(f"GitHub comment failed: HTTP {response.status_code} {response.text[:300]}")
    except Exception as exc:
        print(f"Failed to post GitHub comment: {exc}")


def apply_code(files_dict: Optional[Dict[str, str]]) -> Tuple[bool, str]:
    """
    Safely write Codex-generated code to the local workspace.

    Expected format:
    {
      "relative/path/to/file.py": "full file content",
      ...
    }
    """
    if not files_dict:
        return False, "No valid file payload found in Codex response."

    if "path" in files_dict and "content" in files_dict and len(files_dict) == 2:
        real_path = str(files_dict.get("path", "")).strip()
        real_content = str(files_dict.get("content", ""))
        if real_path and real_content and "/" in real_path:
            print(f"Recovered placeholder response format into real file mapping: {real_path}")
            files_dict = {real_path: real_content}
        else:
            return False, 'Model returned placeholder keys {"path": "...", "content": "..."} only.'

    applied_count = 0
    skipped_paths = []
    failed_paths = []

    for path, content in files_dict.items():
        if not isinstance(path, str) or not isinstance(content, str):
            failed_paths.append(str(path))
            continue

        if ".github" in path:
            skipped_paths.append(path)
            print(f"Security filter skipped workflow path: {path}")
            continue

        normalized = path.replace("\\", "/")
        if path.startswith("/") or ".." in normalized:
            skipped_paths.append(path)
            print(f"Security filter blocked path traversal: {path}")
            continue

        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)
            print(f"Wrote file: {path}")
            applied_count += 1
        except Exception as exc:
            failed_paths.append(path)
            print(f"Failed to write {path}: {exc}")

    if applied_count > 0:
        extras = []
        if skipped_paths:
            extras.append(f"skipped={', '.join(skipped_paths)}")
        if failed_paths:
            extras.append(f"failed={', '.join(failed_paths)}")
        suffix = f" ({'; '.join(extras)})" if extras else ""
        return True, f"Applied {applied_count} file(s){suffix}."

    if skipped_paths:
        return False, f"All candidate files were blocked by safety policy: {', '.join(skipped_paths)}"

    if failed_paths:
        return False, f"Failed to write files: {', '.join(failed_paths)}"

    return False, "No files were written."


def build_apply_prompt(choice: str, context: str) -> str:
    style = "conservative minimal-risk" if choice == "A" else "alternative but still practical"
    return f"""You are Codex fixing a bug reported in a GitHub Issue.

Issue Title: {ISSUE_TITLE}
Issue Body: {ISSUE_BODY}

Project Context:
{context}

Task:
- Produce fix strategy "{choice}" in a {style} style.
- Return ONLY a valid JSON object.
- Keys must be REAL relative file paths.
- Values must be COMPLETE replacement file contents.

Example:
{{
  "src/app.py": "print('hello')\\n",
  "README.md": "# Project\\n"
}}

Do NOT use placeholder keys like "path" or "content".
Do NOT include markdown fences or explanatory text."""


def build_plan_prompt(context: str, variant: str) -> str:
    if variant == "A":
        strategy = (
            "Produce a conservative fix plan that minimizes file churn and prefers the "
            "smallest safe change."
        )
    else:
        strategy = (
            "Produce an alternative fix plan that may be a bit broader, but should improve "
            "clarity or robustness if justified."
        )

    return f"""You are Codex, OpenAI's coding agent, reviewing a GitHub issue.

Issue Title: {ISSUE_TITLE}
Issue Body: {ISSUE_BODY}

Project Context:
{context}

Task:
{strategy}

Output:
- A concise explanation of the approach.
- Then the proposed fixed code or patch content in plain text.
- Make it easy for another reviewer to compare against another plan."""


def build_arbiter_prompt(plan_a: str, plan_b: str) -> str:
    return f"""You are Codex reviewing two candidate fixes for a GitHub issue.

Issue Title: {ISSUE_TITLE}
Issue Body: {ISSUE_BODY}

PLAN A:
{plan_a}

PLAN B:
{plan_b}

Return ONLY valid JSON with this shape:
{{
  "winner": "A or B or HYBRID or NONE",
  "reason": "brief reason for the decision",
  "files": {{
    "actual/relative/path/to/file.py": "complete replacement file content"
  }},
  "report": "markdown comparison for the GitHub comment"
}}

Rules:
- Keys in "files" must be real relative file paths.
- Values in "files" must be complete replacement contents.
- If no safe auto-apply is possible, set winner to "NONE" and files to {{}}.
- Do not include markdown code fences or any text outside the JSON object."""


def run_manual_apply(choice: str, context: str) -> None:
    prompt = build_apply_prompt(choice, context)
    raw = call_codex(prompt, model=OPENAI_MODEL, expect_json=True)

    preview = raw[:500] if raw else "None"
    print(f"[Codex {choice}] raw response:\n{preview}")

    files = robust_json_decode(raw)
    print(f"Decoded file payload: {list(files.keys()) if files else 'None'}")

    success, message = apply_code(files)  # type: ignore[arg-type]
    if success:
        post_comment(
            f"## Codex fix applied\n"
            f"Applied strategy **{choice}** using **{OPENAI_MODEL}**.\n\n"
            f"> {message}"
        )
        with open("FIX_DONE", "w", encoding="utf-8") as handle:
            handle.write("SUCCESS")
        return

    raw_preview = str(raw)[:300] if raw else "No response"
    post_comment(
        f"## Codex apply failed\n"
        f"{message}\n\n"
        f"> Model: {OPENAI_MODEL}\n"
        f"> Response preview: `{raw_preview}`"
    )


def run_auto_flow(context: str) -> None:
    print("Starting Codex comparison flow...")

    plan_a = call_codex(build_plan_prompt(context, "A"), model=OPENAI_MODEL) or "Codex plan A generation failed."
    plan_b = call_codex(build_plan_prompt(context, "B"), model=OPENAI_MODEL) or "Codex plan B generation failed."

    raw_verdict = call_codex(build_arbiter_prompt(plan_a, plan_b), model=OPENAI_REVIEW_MODEL, expect_json=True)
    preview = raw_verdict[:500] if raw_verdict else "None"
    print(f"[Codex arbiter] raw response:\n{preview}")

    verdict = robust_json_decode(raw_verdict)
    if verdict and verdict.get("winner") in {"A", "B", "HYBRID"}:
        winner = str(verdict["winner"])
        files = verdict.get("files", {})
        success, message = apply_code(files if isinstance(files, dict) else None)
        if success:
            post_comment(
                "### Codex auto-fix result\n"
                f"**Winner**: {winner}\n"
                f"**Reason**: {verdict.get('reason', 'No reason provided')}\n\n"
                f"**Report**:\n{verdict.get('report', 'No report provided')}\n\n"
                "---\n"
                "Reply with `/apply A` or `/apply B` if you want to force one Codex plan."
            )
            with open("FIX_DONE", "w", encoding="utf-8") as handle:
                handle.write("SUCCESS")
            return

        print(f"Automatic application failed for winner {winner}: {message}")

    fallback_message = f"""### Codex review requires manual choice
The system could not safely auto-apply a winner, or the selected files were blocked by safety rules.

Reply with one of the following commands to force a plan:
- `/apply A` : apply Codex plan A
- `/apply B` : apply Codex plan B

---
#### Plan comparison

<details><summary>View Plan A</summary>

{plan_a}

</details>

<details><summary>View Plan B</summary>

{plan_b}

</details>"""
    post_comment(fallback_message)


def main() -> None:
    command = re.search(r"/apply\s+(A|B|HYBRID)", COMMENT_BODY, re.IGNORECASE)
    context = get_context()

    if command:
        choice = command.group(1).upper()
        if choice == "HYBRID":
            post_comment("`/apply HYBRID` is not supported in Codex mode. Use `/apply A` or `/apply B`.")
            return
        print(f"Received manual apply command: /apply {choice}")
        run_manual_apply(choice, context)
        return

    run_auto_flow(context)


if __name__ == "__main__":
    main()
