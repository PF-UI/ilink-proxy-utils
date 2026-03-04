# -*- coding: utf-8 -*-
"""
拉取指定线路的 PAC 与代理认证，写入当前目录，供 Go 代理(proxy_manager)使用。
与 get_proxy_info.py 类似，额外拉取 PAC 并保存为 proxy.pac。
用法:
  python get_pac.py [线路_sid]        # 指定 line_sn，如 sg-bgp、us-user1
  python get_pac.py 美国             # 按地区名自动选第一条可连接线路
  python get_pac.py                  # 默认新加坡 (sg-bgp)
依赖: pip install requests
"""
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")
PAC_PATH = os.path.join(SCRIPT_DIR, "proxy.pac")
PROXY_AUTH_FILE = os.path.join(SCRIPT_DIR, "proxy_auth.json")
PROXY_CURRENT_FILE = os.path.join(SCRIPT_DIR, "proxy_current.json")
LINES_FILE = os.path.join(SCRIPT_DIR, "lines.json")

# 线路未返回 p_user/p_pass 时使用
PROXY_TEST_USER = "3405280792@qq.com"
PROXY_TEST_PASS = "495077"

DEFAULT_SID = "sg-bgp"

try:
    from linelist import get_servers, parse_area_from_name
except ImportError:
    get_servers = None
    parse_area_from_name = None

from test import get_server, get_pac, save_pac_to_file, save_proxy_auth_to_file


def get_p_user_p_pass(server_data: dict) -> tuple:
    """从 get_server 返回的 data 中解析 p_user、p_pass"""
    p_user = server_data.get("p_user") or server_data.get("proxy_user") or server_data.get("username")
    p_pass = server_data.get("p_pass") or server_data.get("proxy_pass") or server_data.get("password")
    if p_user and p_pass:
        return p_user, p_pass
    proxy = server_data.get("proxy")
    if isinstance(proxy, dict):
        p_user = proxy.get("p_user") or proxy.get("proxy_user") or proxy.get("username")
        p_pass = proxy.get("p_pass") or proxy.get("proxy_pass") or proxy.get("password")
    return (p_user or None, p_pass or None)


def find_sid_by_area(token: str, area: str) -> str:
    """从 api/servers 中取第一个指定地区且可连接的 line_sn"""
    if not get_servers or not parse_area_from_name:
        return ""
    res = get_servers(token)
    if res.get("status") != 0:
        return ""
    for line in res.get("data") or []:
        if parse_area_from_name(line.get("name", "")) == area and line.get("connect"):
            return line.get("line_sn") or ""
    return ""


def main():
    token = ""
    if os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
    if not token:
        print("未找到 token，请先运行 login.py 并将 token 保存到 token.txt")
        return

    # 第一个参数：sid 或地区名（如 美国、香港）
    sid_or_area = (sys.argv[1].strip() if len(sys.argv) >= 2 else "").strip() or DEFAULT_SID
    sid = sid_or_area

    # 若为地区名，从线路列表解析 sid
    if get_servers and parse_area_from_name:
        maybe_sid = find_sid_by_area(token, sid_or_area)
        if maybe_sid:
            sid = maybe_sid
            print(f"地区 [{sid_or_area}] 使用线路: {sid}\n")
        elif sid_or_area and not any(c in sid_or_area for c in ".-"):
            # 看起来像地区名但没匹配到
            print(f"未找到地区 [{sid_or_area}] 的可连接线路，使用 sid 当作线路名尝试\n")

    print(f"线路: {sid}")
    print(f"输出: {PAC_PATH}, {PROXY_CURRENT_FILE}, {PROXY_AUTH_FILE}\n")

    # 1. 获取线路详情并保存认证
    print("1. 获取线路详情与认证...")
    res_server = get_server(token, sid)
    if res_server.get("status") != 0:
        print(f"   ❌ get_server 失败: {res_server.get('msg', '未知错误')}")
        return
    server_data = res_server.get("data", {})
    p_user, p_pass = get_p_user_p_pass(server_data)
    if not p_user or not p_pass:
        p_user, p_pass = PROXY_TEST_USER, PROXY_TEST_PASS
        print("   线路未返回 p_user/p_pass，使用备用账号")
        save_proxy_auth_to_file({"p_user": p_user, "p_pass": p_pass}, filename=PROXY_AUTH_FILE)
    else:
        save_proxy_auth_to_file(server_data, filename=PROXY_AUTH_FILE)

    with open(PROXY_CURRENT_FILE, "w", encoding="utf-8") as f:
        json.dump({"username": p_user, "password": p_pass, "sid": sid}, f, ensure_ascii=False, indent=2)
    print(f"   ✅ 已写入 {PROXY_CURRENT_FILE}\n")

    # 2. 获取 PAC 并保存
    print("2. 获取 PAC...")
    res_pac = get_pac(token, sid)
    if res_pac.get("status") != 0:
        print(f"   ❌ get_pac 失败: {res_pac.get('msg', '未知错误')}")
        return
    pac_content = res_pac.get("data", "")
    if not isinstance(pac_content, str) or not pac_content.strip():
        print("   ❌ PAC 内容为空")
        return
    save_pac_to_file(pac_content, filename=PAC_PATH)
    print(f"   ✅ 已写入 {PAC_PATH}\n")

    # 3. 可选：把该线路认证回写到 lines.json，便于面板一键切换
    if os.path.isfile(LINES_FILE):
        try:
            with open(LINES_FILE, "r", encoding="utf-8") as f:
                lines = json.load(f)
            if isinstance(lines, list):
                for item in lines:
                    if isinstance(item, dict) and item.get("line_sn") == sid:
                        item["username"] = p_user
                        item["password"] = p_pass
                        break
            with open(LINES_FILE, "w", encoding="utf-8") as f:
                json.dump(lines, f, ensure_ascii=False, indent=2)
            print("3. 已更新 lines.json 中该线路认证，面板可一键切换。")
        except Exception as e:
            print(f"3. 更新 lines.json 失败（不影响使用）: {e}")
    else:
        print("3. 无 lines.json，跳过回写。可先运行 python linelist.py。")

    print("\n请启动 proxy_manager 使用代理：cd proxy_manager && go run .\\main.go")


if __name__ == "__main__":
    main()
