import os
import requests
from github import Github

# --- 从环境变量读取配置 ---
FEISHU_APP_ID = os.environ.get('FEISHU_APP_ID')
FEISHU_APP_SECRET = os.environ.get('FEISHU_APP_SECRET')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
DOC_ID = os.environ.get('DOC_ID')
FILENAME = os.environ.get('FILENAME')

if not all([FEISHU_APP_ID, FEISHU_APP_SECRET, GITHUB_TOKEN, DOC_ID, FILENAME]):
    print("错误: 缺少必要的环境变量，请检查 Secrets 和输入参数。")
    exit(1)

# --- 1. 获取飞书 access token ---
def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    payload = {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}
    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code == 200:
        return resp.json().get("tenant_access_token")
    else:
        print(f"获取飞书 Token 失败: {resp.text}")
        exit(1)

# --- 2. 获取飞书文档纯文本内容 ---
def get_doc_raw_content(token, doc_id):
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/raw_content"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json().get("data", {}).get("content")
    else:
        print(f"获取文档内容失败: {resp.text}")
        exit(1)

# --- 3. 推送到 GitHub 仓库 ---
def push_to_github(filename, content):
    g = Github(GITHUB_TOKEN)
    repo_name = os.environ.get('GITHUB_REPOSITORY')
    if not repo_name:
        print("错误: 无法获取仓库信息。")
        exit(1)
    repo = g.get_repo(repo_name)
    
    commit_msg = f"从飞书同步文档 {DOC_ID}"
    try:
        # 如果文件已存在，则更新
        contents = repo.get_contents(filename)
        repo.update_file(contents.path, commit_msg, content, contents.sha)
        print(f"✅ 文件 {filename} 更新成功！")
    except Exception:
        # 如果文件不存在，则创建
        repo.create_file(filename, commit_msg, content)
        print(f"✅ 文件 {filename} 创建成功！")
    finally:
        g.close()

# --- 主流程 ---
if __name__ == "__main__":
    token = get_tenant_access_token()
    doc_content = get_doc_raw_content(token, DOC_ID)
    push_to_github(FILENAME, doc_content)
    print("🎉 同步完成！")
