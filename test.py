# -*- coding: utf-8 -*-
"""
iLink 完整流程：发验证码 -> 邮箱+验证码登录 -> 获取 api/pac
依赖: pip install requests
"""
import hashlib
import json
import os
import time
import requests
import re
from typing import Optional, Dict, Any

# 代理认证信息保存路径（与 test.py 同目录）
PROXY_AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_auth.json")

# 增加超时重试配置
requests.packages.urllib3.disable_warnings()  # 禁用 SSL 警告
SESSION = requests.Session()  # 使用会话保持，提升性能
SESSION.mount('https://', requests.adapters.HTTPAdapter(max_retries=3))  # 重试 3 次

BASE = "https://cerest.i-linka.com"  # 或 https://node.aalink.xyz
SIGN_SUFFIX = "cef949d30232cf00bfabba46ac5c16e2"

def md5(s: str) -> str:
    """生成字符串的 MD5 哈希值"""
    return hashlib.md5(s.encode('utf-8')).hexdigest()

def make_headers(token: str = "") -> Dict[str, str]:
    """生成请求头"""
    t = str(int(time.time() * 1000))
    sign = md5(t + SIGN_SUFFIX)
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip",
        "t": t,
        "sign": sign,
        "token": token,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

def make_common_body(token: str = "", curr_server_id: str = "", runtime_id: str = "", user_ip: str = "") -> Dict[str, Any]:
    """生成公共请求体"""
    return {
        "appver": "2.2.9",
        "device_name": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "token": token,
        "curr_server_id": curr_server_id,
        "runtime_id": runtime_id or "",
        "from": "pc",
        "userIp": user_ip or "",
    }

def send_code(email: str) -> Dict[str, Any]:
    """发送验证码"""
    try:
        url = f"{BASE}/auth/sendCode"
        body = make_common_body()
        body["email"] = email
        r = SESSION.post(
            url, 
            headers=make_headers(), 
            data=body, 
            timeout=15,
            verify=False  # 忽略 SSL 证书验证（根据实际情况调整）
        )
        r.raise_for_status()  # 抛出 HTTP 错误
        print("send_code:r.json():", r.json())
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}

def login_email(email: str, checkcode: str) -> Dict[str, Any]:
    """邮箱验证码登录"""
    try:
        url = f"{BASE}/auth/login"
        body = make_common_body()
        body["email"] = email
        body["checkcode"] = checkcode
        r = SESSION.post(
            url, 
            headers=make_headers(), 
            data=body, 
            timeout=15,
            verify=False
        )
        r.raise_for_status()
        print("login_email:r.json():", r.json())
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}

def get_default_server(token: str, user_ip: str = "") -> Dict[str, Any]:
    """获取默认线路（与扩展登录后首次拿线路一致）"""
    try:
        url = f"{BASE}/api/get_default_server"
        body = make_common_body(token=token, user_ip=user_ip)
        body["geoip_info"] = "{}"
        r = SESSION.post(
            url,
            headers=make_headers(token=token),
            data=body,
            timeout=15,
            verify=False
        )
        r.raise_for_status()
        print("get_default_server:r.json():", r.json())
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}


def get_server(token: str, sid: str) -> Dict[str, Any]:
    """获取指定线路详情（与扩展 sync_current_server_info 一致，可能含 p_user/p_pass）"""
    try:
        url = f"{BASE}/api/get_server"
        body = make_common_body(token=token, curr_server_id=sid)
        body["sid"] = sid
        r = SESSION.post(
            url,
            headers=make_headers(token=token),
            data=body,
            timeout=15,
            verify=False
        )
        r.raise_for_status()
        print(" get_server:r.json():", r.json())
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}

def get_pac(token: str, sid: str, geoip: str = "true", top_server: str = "") -> Dict[str, Any]:
    """获取 PAC 配置"""
    try:
        url = f"{BASE}/api/pac"
        body = make_common_body(token=token, curr_server_id=sid)
        body["sid"] = sid
        body["gpd"] = "1"
        body["geoip"] = geoip
        body["top_server"] = top_server
        r = SESSION.post(
            url, 
            headers=make_headers(token=token), 
            data=body, 
            timeout=15,
            verify=False
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}

def save_pac_to_file(pac_content: str, filename: str = "proxy.pac") -> bool:
    """将 PAC 内容保存到文件"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            f.write(pac_content)
        print(f"PAC 文件已保存到: {filename}")
        return True
    except Exception as e:
        print(f"保存 PAC 文件失败: {e}")
        return False

def save_proxy_auth_to_file(server_data: Dict[str, Any], filename: str = None) -> bool:
    """若 server_data 中有 p_user、p_pass（或 proxy 子对象内），则保存到 JSON 供 dl.py 使用"""
    filename = filename or PROXY_AUTH_FILE
    # 先看顶层，再看 proxy 子对象（后端可能放在 data.proxy 里）
    p_user = server_data.get("p_user") or server_data.get("proxy_user") or server_data.get("username")
    p_pass = server_data.get("p_pass") or server_data.get("proxy_pass") or server_data.get("password")
    if not p_user or not p_pass:
        proxy = server_data.get("proxy")
        if isinstance(proxy, dict):
            p_user = proxy.get("p_user") or proxy.get("proxy_user") or proxy.get("username")
            p_pass = proxy.get("p_pass") or proxy.get("proxy_pass") or proxy.get("password")
    if not p_user or not p_pass:
        return False
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump({"p_user": p_user, "p_pass": p_pass}, f, ensure_ascii=False, indent=2)
        print(f"✅ 代理认证已保存到: {filename}")
        return True
    except Exception as e:
        print(f"保存代理认证失败: {e}")
        return False

def main():
    """主流程"""
    email = input("请输入登录邮箱: ").strip()
    if not email or "@" not in email:
        print("❌ 请输入有效的邮箱地址")
        return

    # 1. 发送验证码
    print("\n📤 正在发送验证码...")
    res_send = send_code(email)
    if res_send.get("status") != 0:
        print(f"❌ 发验证码失败: {res_send.get('msg', '未知错误')}")
        return
    print("✅ 验证码已发送，请查收邮箱")

    # 2. 输入验证码并登录
    checkcode = input("\n请输入邮箱验证码: ").strip()
    if not checkcode:
        print("❌ 未输入验证码")
        return

    print("🔑 正在登录...")
    res_login = login_email(email, checkcode)
    if res_login.get("status") != 0:
        print(f"❌ 登录失败: {res_login.get('msg', '未知错误')}")
        return
    
    data = res_login.get("data", {})
    token = data.get("token")
    print("token:", token)
    if not token:
        print("❌ 登录成功但未返回 token")
        return
    print("✅ 登录成功，token 已获取")

    # 3. 获取默认线路
    print("\n🌐 正在获取默认线路...")
    res_server = get_default_server(token)
    if res_server.get("status") != 0:
        print(f"❌ 获取线路失败: {res_server.get('msg', '未知错误')}")
        return
    
    server_data = res_server.get("data", {})
    sid = server_data.get("line_sn")
    if not sid:
        print("❌ 未获取到线路 ID (line_sn)")
        return
    print(f"✅ 线路 ID: {sid}")

    # 与扩展一致：先尝试从 get_default_server 保存代理认证
    if save_proxy_auth_to_file(server_data):
        print("   (已从 get_default_server 保存代理认证)")
    else:
        # 扩展还会用 api/get_server(sid) 同步线路，该接口可能返回 p_user/p_pass
        print("   正在用 api/get_server 拉取线路详情（可能与扩展 sync 一致）...")
        res_get_server = get_server(token, sid)
        if res_get_server.get("status") == 0:
            server_detail = res_get_server.get("data", {})
            if save_proxy_auth_to_file(server_detail):
                print("   (已从 get_server 保存代理认证)")
            else:
                # 调试：打印 get_server 返回的 data 的键，便于确认是否有其它字段名
                print("   get_server data 键:", list(server_detail.keys()))
                if isinstance(server_detail.get("proxy"), dict):
                    print("   get_server data.proxy 键:", list(server_detail["proxy"].keys()))
                print("   (未发现 p_user/p_pass，dl.py 使用代理时可能 404 Unauthorized)")
        else:
            print("   (get_server 失败)", res_get_server.get("msg", ""))

    # 4. 获取 PAC 配置
    print("\n📄 正在获取 PAC 配置...")
    res_pac = get_pac(token, sid)
    if res_pac.get("status") != 0:
        print(f"❌ 获取 PAC 失败: {res_pac.get('msg', '未知错误')}")
        return
    
    pac_content = res_pac.get("data", "")
    if not isinstance(pac_content, str) or len(pac_content) == 0:
        print("❌ PAC 内容为空")
        return
    
    print(f"✅ PAC 获取成功，内容长度: {len(pac_content)}")
    print("\n📃 PAC 内容预览 (前 800 字符):")
    print("-" * 60)
    print(pac_content[:800])
    print("-" * 60)

    # 提取代理地址
    proxy_match = re.search(r"PROXY\s+([^\s;]+)", pac_content)
    if proxy_match:
        proxy_addr = proxy_match.group(1)
        print(f"\n📍 提取的代理地址: {proxy_addr}")

    # 保存 PAC 到文件
    save_pac_to_file(pac_content)

if __name__ == "__main__":
    print("===== iLink PAC 获取工具 =====")
    main()
    print("\n🎉 流程执行完成")