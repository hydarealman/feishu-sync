import os
import requests
from github import Github

# --- 环境变量读取 ---
FEISHU_APP_ID = os.environ.get('FEISHU_APP_ID')
FEISHU_APP_SECRET = os.environ.get('FEISHU_APP_SECRET')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
INPUT_ID = os.environ.get('DOC_ID')      # 可能是 space_id 或 node_token
FILENAME = os.environ.get('FILENAME')

if not all([FEISHU_APP_ID, FEISHU_APP_SECRET, GITHUB_TOKEN, INPUT_ID, FILENAME]):
    print("错误: 缺少必要的环境变量，请检查 Secrets 和输入参数。")
    exit(1)

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

def get_space_id_and_root_node(token, identifier):
    """
    尝试将 identifier 作为 space_id，获取空间信息和根节点 token。
    如果成功，返回 (space_id, root_node_token)。
    如果失败，则认为 identifier 本身就是 node_token，返回 (None, identifier)。
    """
    # 1. 先尝试作为 space_id 获取空间详情
    space_url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{identifier}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(space_url, headers=headers)
    if resp.status_code == 200:
        data = resp.json().get("data", {}).get("space", {})
        space_id = data.get("space_id")
        root_node_token = data.get("root_node_token")
        if space_id and root_node_token:
            print(f"✅ 识别为 space_id，根节点 token: {root_node_token}")
            return space_id, root_node_token
        else:
            print("⚠️ 空间信息中缺少必要字段，尝试作为 node_token 处理...")
    else:
        print(f"⚠️ 作为 space_id 获取失败 (HTTP {resp.status_code})，尝试作为 node_token 处理...")

    # 2. 作为 node_token 处理，需要先获取其所属 space_id
    node_url = f"https://open.feishu.cn/open-apis/wiki/v2/nodes/{identifier}"
    resp = requests.get(node_url, headers=headers)
    if resp.status_code == 200:
        data = resp.json().get("data", {}).get("node", {})
        space_id = data.get("space_id")
        if space_id:
            print(f"✅ 识别为 node_token，所属 space_id: {space_id}")
            return space_id, identifier
    # 如果两种都失败
    print(f"❌ 无法将 '{identifier}' 解析为有效的 space_id 或 node_token。")
    print(f"最后一次尝试作为 node_token 返回: {resp.text}")
    exit(1)

def get_wiki_node_content(token, space_id, node_token):
    url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}/nodes/{node_token}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"获取节点内容失败: {resp.text}")
        exit(1)

    data = resp.json().get("data", {}).get("node", {})
    content_blocks = data.get("children", [])

    def extract_text_from_blocks(blocks):
        lines = []
        for block in blocks:
            block_type = block.get("block_type")
            if block_type in range(1, 12):
                text_elements = block.get("text", {}).get("elements", [])
                line = "".join(e.get("text_run", {}).get("content", "") for e in text_elements if "text_run" in e)
                if line:
                    # 简单的 Markdown 转换
                    prefix = {
                        1: "# ", 2: "## ", 3: "### ", 4: "#### ", 5: "##### ", 6: "###### ",
                        7: "- ", 8: "1. ", 9: "> ", 10: "```\n", 11: ""
                    }.get(block_type, "")
                    if block_type == 10:
                        lines.append(prefix + line + "\n```")
                    else:
                        lines.append(prefix + line)
            children = block.get("children", [])
            if children:
                lines.extend(extract_text_from_blocks(children))
        return lines

    lines = extract_text_from_blocks(content_blocks)
    return "\n\n".join(lines)

def push_to_github(filename, content):
    g = Github(GITHUB_TOKEN)
    repo_name = os.environ.get('GITHUB_REPOSITORY')
    if not repo_name:
        print("错误: 无法获取仓库信息。")
        exit(1)
    repo = g.get_repo(repo_name)
    commit_msg = f"从飞书知识库同步 {INPUT_ID}"
    try:
        contents = repo.get_contents(filename)
        repo.update_file(contents.path, commit_msg, content, contents.sha)
        print(f"✅ 文件 {filename} 更新成功！")
    except Exception:
        repo.create_file(filename, commit_msg, content)
        print(f"✅ 文件 {filename} 创建成功！")
    finally:
        g.close()

# --- 主流程 ---
if __name__ == "__main__":
    token = get_tenant_access_token()
    print(f"🔍 正在解析输入标识符: {INPUT_ID}")
    space_id, node_token = get_space_id_and_root_node(token, INPUT_ID)
    print(f"📄 正在获取节点内容 (space_id={space_id}, node_token={node_token})...")
    doc_content = get_wiki_node_content(token, space_id, node_token)
    if not doc_content:
        print("⚠️ 警告：获取到的内容为空，将推送空文件。")
    push_to_github(FILENAME, doc_content)
    print("🎉 同步完成！")
