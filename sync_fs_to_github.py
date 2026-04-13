
import os
import requests
from github import Github

# --- 从环境变量读取配置 ---
FEISHU_APP_ID = os.environ.get('FEISHU_APP_ID')
FEISHU_APP_SECRET = os.environ.get('FEISHU_APP_SECRET')
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
WIKI_TOKEN = os.environ.get('DOC_ID')      # 为了复用参数名，这里实际上存的是 wiki node token
FILENAME = os.environ.get('FILENAME')

if not all([FEISHU_APP_ID, FEISHU_APP_SECRET, GITHUB_TOKEN, WIKI_TOKEN, FILENAME]):
    print("错误: 缺少必要的环境变量，请检查 Secrets 和输入参数。")
    exit(1)

# --- 获取飞书 tenant_access_token ---
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

# --- 1. 通过 node_token 获取 space_id ---
def get_space_id_by_node(token, node_token):
    url = f"https://open.feishu.cn/open-apis/wiki/v2/nodes/{node_token}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json().get("data", {}).get("node", {})
        space_id = data.get("space_id")
        if not space_id:
            print("错误: 无法从节点信息中获取 space_id")
            exit(1)
        return space_id
    else:
        print(f"获取 space_id 失败: {resp.text}")
        exit(1)

# --- 2. 获取知识库节点内容（递归提取所有文本块） ---
def get_wiki_node_content(token, space_id, node_token):
    url = f"https://open.feishu.cn/open-apis/wiki/v2/spaces/{space_id}/nodes/{node_token}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"获取节点内容失败: {resp.text}")
        exit(1)

    data = resp.json().get("data", {}).get("node", {})
    # 知识库内容可能是 page 或 block 结构，这里简单处理：如果有 children 则遍历提取文本
    # 更完整的处理需要递归解析 block，但为了快速可用，我们调用飞书的“导出为纯文本”接口（如果存在）
    # 然而知识库没有 raw_content 接口，所以我们需要手动解析 block 结构
    
    # 尝试从节点中提取文本内容（假设节点类型为 block）
    content_blocks = data.get("children", [])
    if not content_blocks:
        # 可能没有 children，节点本身是一个页面，内容在 page 的 body 里？
        # 根据飞书 API，需要再调用获取块内容的接口，这里简化处理：如果有 obj_token，则尝试获取块内容
        obj_token = data.get("obj_token")
        if obj_token:
            # 如果是旧版文档块，用文档接口读取
            doc_url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{obj_token}/raw_content"
            doc_resp = requests.get(doc_url, headers=headers)
            if doc_resp.status_code == 200:
                return doc_resp.json().get("data", {}).get("content", "")
            else:
                print(f"尝试以文档方式读取失败: {doc_resp.text}")
        
        # 如果以上都失败，返回空内容
        return "（知识库内容为空或无法解析）"

    # 递归提取块中的文本
    def extract_text_from_blocks(blocks):
        lines = []
        for block in blocks:
            block_type = block.get("block_type")
            if block_type in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]:  # 文本类块
                text_elements = block.get("text", {}).get("elements", [])
                line = ""
                for elem in text_elements:
                    if "text_run" in elem:
                        line += elem["text_run"].get("content", "")
                if line:
                    # 根据类型添加 Markdown 标题标记
                    if block_type == 1:
                        lines.append("# " + line)
                    elif block_type == 2:
                        lines.append("## " + line)
                    elif block_type == 3:
                        lines.append("### " + line)
                    elif block_type == 4:
                        lines.append("#### " + line)
                    elif block_type == 5:
                        lines.append("##### " + line)
                    elif block_type == 6:
                        lines.append("###### " + line)
                    elif block_type == 7:  # 无序列表
                        lines.append("- " + line)
                    elif block_type == 8:  # 有序列表
                        lines.append("1. " + line)
                    elif block_type == 9:  # 引用
                        lines.append("> " + line)
                    elif block_type == 10: # 代码块
                        lines.append("```")
                        lines.append(line)
                        lines.append("```")
                    else:
                        lines.append(line)
            # 递归处理子块
            children = block.get("children", [])
            if children:
                lines.extend(extract_text_from_blocks(children))
        return lines

    lines = extract_text_from_blocks(content_blocks)
    return "\n\n".join(lines)

# --- 3. 推送到 GitHub 仓库 ---
def push_to_github(filename, content):
    g = Github(GITHUB_TOKEN)
    repo_name = os.environ.get('GITHUB_REPOSITORY')
    if not repo_name:
        print("错误: 无法获取仓库信息。")
        exit(1)
    repo = g.get_repo(repo_name)
    
    commit_msg = f"从飞书知识库同步节点 {WIKI_TOKEN}"
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
    print(f"🔍 正在通过节点 token 获取 space_id...")
    space_id = get_space_id_by_node(token, WIKI_TOKEN)
    print(f"✅ space_id: {space_id}")
    print(f"📄 正在获取知识库节点内容...")
    doc_content = get_wiki_node_content(token, space_id, WIKI_TOKEN)
    if not doc_content:
        print("⚠️ 警告：获取到的内容为空，将推送空文件。")
    push_to_github(FILENAME, doc_content)
    print("🎉 同步完成！")
