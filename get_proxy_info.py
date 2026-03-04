# -*- coding: utf-8 -*-
"""
获取指定线路的代理认证信息（用户名、密码）并保存，供 Go 代理或本地代理使用。
用法: python get_proxy_info.py [线路_sid]
默认线路: 新加坡 (sg-bgp)
"""
import json
import os
import sys
from test import get_server, save_proxy_auth_to_file

# 路径与常量
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")
PROXY_AUTH_FILE = os.path.join(SCRIPT_DIR, "proxy_auth.json")
PROXY_CURRENT_FILE = os.path.join(SCRIPT_DIR, "proxy_current.json")

DEFAULT_SID = "sg-bgp"
# 线路未返回认证信息时的备用账号
PROXY_TEST_USER = "3405280792@qq.com"
PROXY_TEST_PASS = "495077"


def get_p_user_p_pass(server_data: dict) -> tuple:
    """从 get_server 返回的 data 中解析 p_user、p_pass（支持顶层或 proxy 子对象）"""
    p_user = server_data.get("p_user") or server_data.get("proxy_user") or server_data.get("username")
    p_pass = server_data.get("p_pass") or server_data.get("proxy_pass") or server_data.get("password")
    if p_user and p_pass:
        return p_user, p_pass
    proxy = server_data.get("proxy")
    if isinstance(proxy, dict):
        p_user = proxy.get("p_user") or proxy.get("proxy_user") or proxy.get("username")
        p_pass = proxy.get("p_pass") or proxy.get("proxy_pass") or proxy.get("password")
    return (p_user or None, p_pass or None)


def main():
    """主流程：读取 token -> 获取线路详情 -> 解析认证信息 -> 保存到 JSON"""
    if os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
    else:
        token = ""

    if not token:
        print("未找到 token，请先运行 login.py")
        return

    sid = sys.argv[1].strip() if len(sys.argv) >= 2 else DEFAULT_SID
    print(f"正在获取线路 [{sid}] 的代理认证信息...")

    res = get_server(token, sid)
    if res.get("status") != 0:
        print(f"❌ 获取线路详情失败: {res.get('msg', '未知错误')}")
        return

    server_data = res.get("data", {})
    p_user, p_pass = get_p_user_p_pass(server_data)

    if not p_user or not p_pass:
        print("⚠️ 线路未返回认证信息，使用备用账号")
        p_user, p_pass = PROXY_TEST_USER, PROXY_TEST_PASS
        auth_data = {"p_user": p_user, "p_pass": p_pass}
    else:
        print("✅ 成功获取线路认证信息")
        auth_data = server_data

    save_proxy_auth_to_file(auth_data, PROXY_AUTH_FILE)

    simplified = {"username": p_user, "password": p_pass, "sid": sid}
    try:
        with open(PROXY_CURRENT_FILE, "w", encoding="utf-8") as f:
            json.dump(simplified, f, ensure_ascii=False, indent=2)
        print(f"✅ 代理简明信息已保存至 {PROXY_CURRENT_FILE}")
    except Exception as e:
        print(f"❌ 保存失败: {e}")


if __name__ == "__main__":
    main()