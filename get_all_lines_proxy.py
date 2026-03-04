# -*- coding: utf-8 -*-
"""
拉取所有线路的 PAC，提取 var proxy = "..." 写入 lines_proxy.json，供 Go 代理切换线路时使用。
用法: python get_all_lines_proxy.py
依赖: 先运行 login.py、linelist.py，且 token.txt 存在。
"""
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")
LINES_FILE = os.path.join(SCRIPT_DIR, "lines.json")
LINES_PROXY_FILE = os.path.join(SCRIPT_DIR, "lines_proxy.json")

# 从 PAC 内容中提取 var proxy = "..." 的完整字符串
RE_PROXY = re.compile(r'var\s+proxy\s*=\s*"([^"]*)"', re.I)


def extract_proxy_string(pac_content: str) -> str:
    """从 PAC 文本中提取 var proxy = "..." 的引号内内容，未找到返回空字符串。"""
    if not pac_content or not isinstance(pac_content, str):
        return ""
    m = RE_PROXY.search(pac_content)
    return m.group(1).strip() if m else ""


def main():
    token = ""
    if os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
    if not token:
        print("未找到 token，请先运行 login.py 并将 token 保存到 token.txt")
        return

    # 线路列表：优先从 lines.json 读，否则调 api/servers
    line_sns = []
    if os.path.isfile(LINES_FILE):
        try:
            with open(LINES_FILE, "r", encoding="utf-8") as f:
                lines = json.load(f)
            if isinstance(lines, list):
                for item in lines:
                    if isinstance(item, dict) and item.get("line_sn"):
                        line_sns.append(item["line_sn"])
        except Exception as e:
            print(f"读取 {LINES_FILE} 失败: {e}")
    if not line_sns:
        try:
            from linelist import get_servers
            res = get_servers(token)
            if res.get("status") == 0:
                for item in res.get("data") or []:
                    if isinstance(item, dict) and item.get("line_sn"):
                        line_sns.append(item["line_sn"])
        except ImportError:
            pass
    if not line_sns:
        print("无线路列表，请先运行 python linelist.py 生成 lines.json")
        return

    from test import get_pac

    result = {}
    total = len(line_sns)
    for i, sid in enumerate(line_sns, 1):
        print(f"[{i}/{total}] {sid} ...", end=" ", flush=True)
        res = get_pac(token, sid)
        if res.get("status") != 0:
            print(f"get_pac 失败: {res.get('msg', '')}")
            continue
        pac_content = res.get("data", "")
        proxy_str = extract_proxy_string(pac_content)
        if proxy_str:
            result[sid] = proxy_str
            print("OK")
        else:
            print("未解析到 var proxy")

    with open(LINES_PROXY_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {len(result)} 条线路的 proxy 到 {LINES_PROXY_FILE}")
    print("Go 项目切换线路时将从此文件读取该线路的上游代理。")


if __name__ == "__main__":
    main()
