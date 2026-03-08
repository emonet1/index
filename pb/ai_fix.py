import os
import glob
import subprocess
import time

# Placeholder for the directory where PocketBase hooks are located
HOOKS_DIR = "pb/pb_hooks"

def clean_ai_code(raw_code):
    """
    Placeholder function to simulate cleaning AI-generated code.
    In a real scenario, this would parse and clean the AI's output.
    """
    # For this exercise, let's assume it just returns the code as is, or strips whitespace.
    return raw_code.strip()

def run_git_sync():
    """
    Placeholder function to simulate Git synchronization.
    """
    print("🚀 Running Git synchronization...")
    try:
        # Example: git add ., git commit, git push
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "AUTO-FIX: AI applied fix to PocketBase hook"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Git synchronization complete.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git synchronization failed: {e}")

def fix_pocketbase_issue():
    print("Starting AI fix process for PocketBase issue...")
    
    files = glob.glob(f"{HOOKS_DIR}/*.js")
    if not files:
        print(f"No JavaScript files found in {HOOKS_DIR}. Exiting.")
        return

    # --- FIX START ---
    # 改进文件选择逻辑：选择最近修改的文件，而不是 glob 结果的第一个
    # 这增加了 AI 修复实际导致问题的文件的概率
    target_file = max(files, key=os.path.getmtime)
    # --- FIX END ---

    print(f"🔍 诊断文件: {target_file}")

    old_code = ""
    try:
        with open(target_file, "r") as f:
            old_code = f.read()
    except FileNotFoundError:
        print(f"Error: Target file {target_file} not found.")
        return
    except Exception as e:
        print(f"Error reading {target_file}: {e}")
        return

    # Simulate AI generating a fix. In a real system, this would involve an LLM call.
    # For this example, let's assume the AI always suggests a minor change or no change.
    # Let's make it suggest a change for demonstration purposes.
    # In a real scenario, 'raw_code' would come from the AI's response.
    raw_code = old_code + "\n// AI added this line for testing.\n" # Simulate AI output

    fixed_code = clean_ai_code(raw_code)
    
    # 5. 写入修复后的代码
    # 只有当 AI 实际返回了不同的代码时才写入，避免不必要的 git commit
    if fixed_code.strip() != old_code.strip():
        with open(target_file, "w") as f:
            f.write(fixed_code)
        print("✅ AI 修复方案已写入文件")
        
        # 6. 同步到 GitHub
        run_git_sync()
    else:
        print("ℹ️ AI 认为代码无需修改或返回了相同代码，跳过写入和 Git 同步。")
    
    # 7. 重启 PocketBase 使代码生效
    print("🔄 正在通过 Supervisor 重启 PocketBase...")
    # Placeholder for actual PocketBase restart command
    # subprocess.run(["supervisorctl", "restart", "pocketbase"])

if __name__ == "__main__":
    # Create a dummy hooks directory and files for testing the script logic
    os.makedirs(HOOKS_DIR, exist_ok=True)
    
    # Create dummy files with different modification times
    with open(os.path.join(HOOKS_DIR, "test_bug.js"), "w") as f:
        f.write("console.log('buggy code');")
    time.sleep(0.1) # Ensure different mtime
    with open(os.path.join(HOOKS_DIR, "crash.js"), "w") as f:
        f.write("function crash() { return getData(); }")
    time.sleep(0.1)
    with open(os.path.join(HOOKS_DIR, "fatal_error.js"), "w") as f:
        f.write("throw new Error('Fatal error');")
    time.sleep(0.1)
    with open(os.path.join(HOOKS_DIR, "test.pb.js"), "w") as f:
        f.write("routerAdd(\"GET\", \"/test\", (c) => c.json(200, { message: \"OK\" }));")

    print("\n--- Running fix_pocketbase_issue ---")
    fix_pocketbase_issue()
    print("--- fix_pocketbase_issue finished ---\n")

    # Clean up dummy files/directory (uncomment to enable cleanup)
    # for f in glob.glob(f"{HOOKS_DIR}/*.js"):
    #     os.remove(f)
    # os.rmdir(HOOKS_DIR)
