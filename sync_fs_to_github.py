# scripts/fetch_feishu_doc.py
import os
import requests
import re
from typing import Optional

def get_tenant_access_token(app_id: str, app_secret: str) -> Optional[str]:
    """使用 App ID 和 App Secret 获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            print(f"获取 tenant_access_token 失败: {data}")
            return None
        return data.get("tenant_access_token")
    except Exception as e:
        print(f"请求 tenant_access_token 时出错: {e}")
        return None

def get_document_id_from_wiki_url(wiki_url: str, app_id: str, app_secret: str) -> Optional[str]:
    """从知识库URL中提取 node_token 并换取真正的 document_id"""
    # 1. 先获取 access token
    token = get_tenant_access_token(app_id, app_secret)
    if not token:
        return None

    # 2. 提取 node_token
    match = re.search(r'/wiki/([a-zA-Z0-9]+)', wiki_url)
    if not match:
        print(f"错误：无法从URL中提取node_token: {wiki_url}")
        return None
    node_token = match.group(1)
    print(f"提取到的 node_token: {node_token}")

    # 3. 调用 API 获取节点信息
    api_url = "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"token": node_token}
    
    try:
        response = requests.get(api_url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            print(f"飞书API返回错误: {data}")
            return None
        
        node_info = data.get("data", {}).get("node", {})
        obj_type = node_info.get("obj_type")
        obj_token = node_info.get("obj_token")
        
        if obj_type != "docx":
            print(f"警告：该节点不是文档类型，而是 {obj_type}。")
            return None
            
        print(f"成功获取 document_id: {obj_token}")
        return obj_token
    except Exception as e:
        print(f"API请求失败: {e}")
        return None

def fetch_and_save_document(document_id: str, token: str, output_path: str):
    """示例：根据 document_id 获取文档内容并保存为 Markdown 文件"""
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/raw_content"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            print(f"获取文档内容失败: {data}")
            return
        
        content = data.get("data", {}).get("content", "")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"文档已保存至: {output_path}")
    except Exception as e:
        print(f"保存文档时出错: {e}")

if __name__ == "__main__":
    # 从 GitHub Secrets 环境变量中读取敏感信息
    APP_ID = os.environ.get("FEISHU_APP_ID")
    APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
    WIKI_URL = os.environ.get("FEISHU_WIKI_URL", "https://scnfpjgsylvl.feishu.cn/wiki/CAItwR71aiWTtPkq4hscgk53n9g")
    OUTPUT_FILE = os.environ.get("OUTPUT_FILE", "doc.md")
    
    if not APP_ID or not APP_SECRET:
        print("错误：请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        exit(1)
    
    # 1. 获取 token (为了复用，我们先获取一次)
    token = get_tenant_access_token(APP_ID, APP_SECRET)
    if not token:
        exit(1)
    
    # 2. 转换 wiki URL 到真实的 document_id
    doc_id = get_document_id_from_wiki_url(WIKI_URL, APP_ID, APP_SECRET)
    if not doc_id:
        exit(1)
    
    # 3. 拉取文档内容并保存
    fetch_and_save_document(doc_id, token, OUTPUT_FILE)
