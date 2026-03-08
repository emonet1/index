import os
import glob
import subprocess
import time
import json
from datetime import datetime

# Configuration
HOOKS_DIR = "/home/pb/pb_hooks"
ERROR_LOG_PATH = "/home/pb/error.log"
GIT_REPO_PATH = "/home/pb" # Assuming the pb directory is the git repo
ALIYUN_API_KEY = os.getenv("ALIYUN_API_KEY")
ALIYUN_SECRET_KEY = os.getenv("ALIYUN_SECRET_KEY")
QWEN_MODEL_ID = "qwen-plus" # Or other appropriate model

# Placeholder for Aliyun client (replace with actual Aliyun SDK client)
class AliyunClient:
    def __init__(self, api_key, secret_key):
        self.api_key = api_key
        self.secret_key = secret_key
        # Initialize actual Aliyun client here, e.g., from aliyunsdkcore.client import AcsClient

    def call_qwen_plus(self, prompt):
        # Simulate API call
        print(f"Calling Qwen-plus with prompt (truncated): {prompt[:200]}...")
        # In a real scenario, this would make an actual API call
        # For demonstration, let's return a dummy fix
        if "routerAdd" in prompt:
            return """routerAdd("GET", "/test-break", (c) => {
  try {
    // Simulate a test endpoint
    return c.json(200, { message: "Test successful (AI fixed)" });
  } catch (error) {
    console.error('Error in /test-break route (AI fixed):', error);
    return c.json(500, { error: "Internal server error (AI fixed)" });
  }
});"""
        elif "console.log('Hello World')" in prompt:
            return """try {
  console.log('Hello World (AI fixed)');
} catch (error) {
  console.error('Error in test_bug.js (AI fixed):', error);
}"""
        return "console.log('AI fixed this generic issue.');"

aliyun_client = AliyunClient(ALIYUN_API_KEY, ALIYUN_SECRET_KEY)

def get_latest_error():
    """从错误日志中提取最新的错误信息"""
    try:
        with open(ERROR_LOG_PATH, "r") as f:
            lines = f.readlines()
            # 查找最近的错误标记，例如 "ERROR:" 或 "panic:"
            for i in range(len(lines) - 1, -1, -1):
                if "ERROR:" in lines[i] or "panic:" in lines[i]:
                    # 提取最近的几行作为错误上下文
                    start_index = max(0, i - 10) # Get 10 lines before error
                    return "".join(lines[start_index:i+1])
        return "未找到具体的错误日志。"
    except Exception as e:
        return f"读取错误日志失败: {e}"

def commit_and_restart(file_path, original_content, fixed_content):
    """提交代码并重启 PocketBase 服务"""
    try:
        # 写入修复后的代码
        with open(file_path, "w") as f:
            f.write(fixed_content)

        # 切换到 Git 仓库目录
        os.chdir(GIT_REPO_PATH)

        # 添加文件到暂存区
        subprocess.run(["git", "add", file_path], check=True)

        # 提交更改
        commit_message = f"AUTO-FIX: Applied AI fix for {os.path.basename(file_path)} on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        print(f"✅ 成功提交代码: {commit_message}")

        # 重启 PocketBase 服务 (假设使用 supervisorctl)
        subprocess.run(["supervisorctl", "restart", "pocketbase"], check=True)
        print("✅ 成功重启 PocketBase 服务。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Git 操作或服务重启失败: {e}")
        # 尝试回滚文件内容
        try:
            with open(file_path, "w") as f:
                f.write(original_content)
            print(f"⚠️ 修复失败，已回滚 {file_path} 到原始内容。")
        except Exception as rollback_e:
            print(f"❌ 回滚文件失败: {rollback_e}")
        return False
    except Exception as e:
        print(f"❌ 提交或重启过程中发生未知错误: {e}")
        return False

def main():
    print(f"🚀 启动 AI 自动修复程序 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

    # 1. 查找目标文件
    target_file = None
    specific_test_file = os.path.join(HOOKS_DIR, "test.pb.js")
    
    # 优先检查 Issue 中明确提到的“破坏测试”文件
    if os.path.exists(specific_test_file):
        target_file = specific_test_file
        print(f"🔍 优先诊断文件 (根据Issue上下文明确指出): {target_file}")
    else:
        # 如果特定文件不存在，则查找所有 JS 文件并按修改时间排序，选择最新修改的
        files = glob.glob(f"{HOOKS_DIR}/*.js")
        if not files:
            print(f"❌ 错误: 在 {HOOKS_DIR} 未找到代码文件。")
            return
        
        # 按照文件修改时间倒序排序，最新修改的文件排在前面
        files.sort(key=os.path.getmtime, reverse=True)
        target_file = files[0]
        print(f"🔍 诊断文件 (最新修改): {target_file}")
    
    with open(target_file, "r") as f:
        old_code = f.read()

    # 2. 提取报错
    error_context = get_latest_error()
    print("📝 正在请求 AI 修复方案 (通义千问 qwen-plus)...")

    # 3. 构建 Prompt
    prompt = f"""
    你是 PocketBase 专家。修复以下代码中的语法或逻辑错误，确保它能正常运行，并使服务稳定。
    如果这是一个测试文件或已知有问题的代码，请将其修改为无害的、功能正常的代码，例如返回一个简单的JSON响应，或者移除其破坏性逻辑。
    【报错日志】：
    {error_context}
    
    【待修复代码文件】: {os.path.basename(target_file)}
    ```javascript
    {old_code}
    ```
    
    请只返回修复后的完整代码，不要包含任何解释或其他文本。
    """

    # 4. 调用 AI 模型获取修复方案
    try:
        ai_fix_code = aliyun_client.call_qwen_plus(prompt)
        if not ai_fix_code:
            print("❌ AI 未返回修复方案。")
            return
        print("✅ AI 成功生成修复方案。")
    except Exception as e:
        print(f"❌ 调用 AI 模型失败: {e}")
        return

    # 5. 应用修复并重启服务
    if ai_fix_code != old_code:
        print("💾 正在应用修复并提交代码...")
        if commit_and_restart(target_file, old_code, ai_fix_code):
            print("🎉 自动修复流程完成，服务已尝试恢复。")
        else:
            print("⚠️ 自动修复流程失败，请手动检查。")
    else:
        print("ℹ️ AI 认为代码无需修改或返回了相同代码。")

if __name__ == "__main__":
    main()
