import os
import json
from github import Github
from openai import OpenAI

def main():
    # ۱. دریافت متغیرهای محیطی از GitHub Actions
    gh_token = os.environ.get("GITHUB_TOKEN")
    openai_key = os.environ.get("OPENAI_API_KEY")
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    repo_name = os.environ.get("GITHUB_REPOSITORY")

    if not all([gh_token, openai_key, event_path, repo_name]):
        print("❌ Error: Missing required environment variables.")
        return

    # ۲. خواندن اطلاعات Pull Request
    with open(event_path, 'r') as f:
        event_data = json.load(f)
    
    pr_number = event_data['pull_request']['number']

    # ۳. اتصال به گیت‌هاب و دریافت تغییرات فایل‌ها
    gh = Github(gh_token)
    repo = gh.get_repo(repo_name)
    pr = repo.get_pull(pr_number)

    files = pr.get_files()
    code_changes = ""
    for file in files:
        if file.patch:
            code_changes += f"### File: {file.filename}\n```diff\n{file.patch}\n```\n\n"

    if not code_changes:
        print("ℹ️ No actionable code changes found to review.")
        return

    # ۴. سوپر مغز: دستورالعمل سیستمی پیشرفته
    SUPER_BRAIN_SYSTEM_PROMPT = """
You are an elite Principal Software Engineer, Security Auditor, and Cloud Architect.
Your job is to review Pull Requests with the highest standards of the industry.

When reviewing the code, you MUST follow these analytical steps internally before providing the final review:
1. Context Analysis: Understand what the code is trying to achieve.
2. Architecture & Design: Check for SOLID principles, DRY, and design patterns.
3. Performance: Analyze Big O time and space complexity. Flag memory leaks or N+1 queries.
4. Security (OWASP Top 10): Look for SQL injection, XSS, insecure direct object references, or hardcoded secrets.
5. Best Practices: Check naming conventions, error handling, and testability.

OUTPUT FORMAT (Must be in Markdown):
### 🧠 Thought Process
[Briefly explain your step-by-step reasoning and what you noticed in the code]

### 🚨 Security & Vulnerabilities
[List any security risks. If none, write "Passed ✅"]

### ⚡ Performance & Optimization
[Highlight inefficiencies or suggest better algorithms. If none, write "Passed ✅"]

### 🛠️ Architecture & Code Quality
[Feedback on SOLID, DRY, and maintainability]

### 💡 Suggested Fixes (Code Snippets)
[Provide refactored code blocks if applicable]
"""

    user_prompt = f"Please review the following code changes carefully:\n\n{code_changes}"

    # ۵. ارتباط با OpenAI برای تحلیل هوشمند
    print("🧠 Super Brain is analyzing the code...")
    client = OpenAI(api_key=openai_key)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SUPER_BRAIN_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2, # دمای پایین برای تحلیل دقیق، منطقی و بدون توهم
            max_tokens=2500
        )
        
        review_comment = response.choices[0].message.content
        
        # ۶. ثبت گزارش نهایی در گیت‌هاب
        pr.create_issue_comment(f"## 🤖 Agent Super Brain Analysis\n\n{review_comment}")
        print("✅ Review successfully posted to GitHub!")

    except Exception as e:
        print(f"❌ Error during LLM API call: {e}")

if __name__ == "__main__":
    main()
