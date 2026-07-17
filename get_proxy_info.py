# -*- coding: utf-8 -*-
"""
获取指定线路的代理认证信息（用户名、密码）并保存，供 Go 代理或本地代理使用。
用法:
  python get_proxy_info.py [线路_sid]
  默认线路: 新加坡 (sg-bgp)
"""
import json
import os
import sys
from test import get_server, save_proxy_auth_to_file

# Windows 控制台 UTF-8 支持
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import config


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
    # 1. 获取 token
    token = config.get_token()
    if not token:
        print("❌ 未找到 token，请先运行 login.py 登录")
        print("   或使用: python linelist.py --auto 自动登录获取线路")
        return

    # 2. 线路 SID
    sid = sys.argv[1].strip() if len(sys.argv) >= 2 else config.DEFAULT_SID
    print(f"正在获取线路 [{sid}] 的代理认证信息...")

    # 3. 请求线路详情
    res = get_server(token, sid)
    if res.get("status") != 0:
        print(f"❌ 获取线路详情失败: {res.get('msg', '未知错误')}")
        print("   可能 token 已过期，请重新运行: python login.py")
        return

    server_data = res.get("data", {})
    print(f"   返回数据: {json.dumps(server_data, ensure_ascii=False, indent=2)}")
    p_user, p_pass = get_p_user_p_pass(server_data)

    # 4. 如果没有返回代理认证信息，使用 .env 中的账号密码作为备用
    if not p_user or not p_pass:
        print("⚠️ 线路未返回认证信息，使用 .env 中的账号密码作为备用")
        p_user, p_pass = config.get_credentials()
        if not p_user or not p_pass:
            print("❌ .env 中也没有凭据信息")
            return
        print(f"   备用账号: {p_user}")
    else:
        print("✅ 成功获取线路认证信息")

    # 5. 保存完整认证信息
    server_data["p_user"] = p_user
    server_data["p_pass"] = p_pass
    save_proxy_auth_to_file(server_data, config.PROXY_AUTH_FILE)

    # 6. 保存简化信息供 Go 代理使用（包含上游代理地址和端口）
    upstream_host = server_data.get("ip", "api.i-linka.com")
    upstream_port = str(server_data.get("port", "8080"))
    simplified = {
        "username": p_user,
        "password": p_pass,
        "sid": sid,
        "upstream_host": upstream_host,
        "upstream_port": upstream_port,
    }
    try:
        with open(config.PROXY_CURRENT_FILE, "w", encoding="utf-8") as f:
            json.dump(simplified, f, ensure_ascii=False, indent=2)
        print(f"✅ 代理简明信息已保存至 {config.PROXY_CURRENT_FILE}")
        print(f"   username: {p_user}")
        print(f"   password: {p_pass}")
        print(f"   sid: {sid}")
        print(f"   上游代理: {upstream_host}:{upstream_port}")
    except Exception as e:
        print(f"❌ 保存失败: {e}")


if __name__ == "__main__":
    main()
