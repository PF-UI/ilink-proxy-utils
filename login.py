# -*- coding: utf-8 -*-
"""
iLink 邮箱登录，获取验证码，获取 token，保存到 token.txt。
用法: python login.py
"""
import hashlib
import os
import time
import requests
from typing import Dict, Any

# 路径与常量
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")
BASE = "https://cerest.i-linka.com"
SIGN_SUFFIX = "cef949d30232cf00bfabba46ac5c16e2"

requests.packages.urllib3.disable_warnings()
SESSION = requests.Session()
SESSION.mount("https://", requests.adapters.HTTPAdapter(max_retries=3))


def md5(s: str) -> str:
    """生成 MD5 哈希"""
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def make_headers(token: str = "") -> Dict[str, str]:
    """生成请求头（含 t、sign 签名）"""
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


def make_common_body() -> Dict[str, Any]:
    """生成登录接口公共请求体"""
    return {
        "appver": "2.2.9",
        "device_name": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "token": "",
        "curr_server_id": "",
        "runtime_id": "",
        "from": "pc",
        "userIp": "",
    }


def send_code(email: str) -> Dict[str, Any]:
    """发送邮箱验证码"""
    try:
        url = f"{BASE}/auth/sendCode"
        body = make_common_body()
        body["email"] = email
        r = SESSION.post(url, headers=make_headers(), data=body, timeout=15, verify=False)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}


def login_email(email: str, checkcode: str) -> Dict[str, Any]:
    """邮箱 + 验证码登录"""
    try:
        url = f"{BASE}/auth/login"
        body = make_common_body()
        body["email"] = email
        body["checkcode"] = checkcode
        r = SESSION.post(url, headers=make_headers(), data=body, timeout=15, verify=False)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}


def main():
    """主流程：输入邮箱 -> 发验证码 -> 输入验证码 -> 登录 -> 保存 token"""
    print("===== iLink 登录获取 Token =====")
    email = input("请输入登录邮箱: ").strip()
    if not email or "@" not in email:
        print("❌ 请输入有效的邮箱地址")
        return

    print("\n📤 正在发送验证码...")
    res = send_code(email)
    if res.get("status") != 0:
        print(f"❌ 发送验证码失败: {res.get('msg', '未知错误')}")
        return
    print("✅ 验证码已发送，请查收邮箱")

    checkcode = input("\n请输入邮箱验证码: ").strip()
    if not checkcode:
        print("❌ 未输入验证码")
        return

    print("🔑 正在登录...")
    res = login_email(email, checkcode)
    if res.get("status") != 0:
        print(f"❌ 登录失败: {res.get('msg', '未知错误')}")
        return

    token = res.get("data", {}).get("token")
    if not token:
        print("❌ 登录成功但未返回 token")
        return

    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(token)
        print(f"✅ 登录成功，Token 已保存至 {TOKEN_FILE}")
    except Exception as e:
        print(f"❌ 保存 Token 失败: {e}")


if __name__ == "__main__":
    main()