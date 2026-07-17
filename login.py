# -*- coding: utf-8 -*-
"""
iLink 邮箱登录，获取验证码，获取 token，保存到 token.txt。
用法:
  交互模式:  python login.py
  自动模式:  python login.py --auto  (使用 .env 中的邮箱，自动发送验证码)
"""
import hashlib
import os
import sys
import time
import requests
from typing import Dict, Any

# Windows 控制台 UTF-8 支持
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# 本地配置模块
import config

requests.packages.urllib3.disable_warnings()
SESSION = requests.Session()
SESSION.mount("https://", requests.adapters.HTTPAdapter(max_retries=3))


def md5(s: str) -> str:
    """生成 MD5 哈希"""
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def make_headers(token: str = "") -> Dict[str, str]:
    """生成请求头（含 t、sign 签名）"""
    t = str(int(time.time() * 1000))
    sign = md5(t + config.SIGN_SUFFIX)
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
        url = f"{config.BASE}/auth/sendCode"
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
        url = f"{config.BASE}/auth/login"
        body = make_common_body()
        body["email"] = email
        body["checkcode"] = checkcode
        r = SESSION.post(url, headers=make_headers(), data=body, timeout=15, verify=False)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}


def verify_token(token: str) -> bool:
    """验证 token 是否仍然有效"""
    try:
        url = f"{config.BASE}/api/get_default_server"
        body = make_common_body()
        body["token"] = token
        r = SESSION.post(url, headers=make_headers(token=token), data=body, timeout=10, verify=False)
        r.raise_for_status()
        resp = r.json()
        return resp.get("status") == 0
    except Exception:
        return False


def do_login(email: str) -> str:
    """
    执行登录流程：发送验证码 → 输入验证码 → 登录 → 返回 token。
    返回空字符串表示登录失败。
    """
    print(f"\n📤 正在发送验证码到 {email} ...")
    res = send_code(email)
    print("   响应:", res)
    if res.get("status") != 0:
        print(f"❌ 发送验证码失败: {res.get('msg', '未知错误')}")
        return ""
    print("✅ 验证码已发送，请查收邮箱")

    checkcode = input("\n请输入邮箱验证码: ").strip()
    if not checkcode:
        print("❌ 未输入验证码")
        return ""

    print("🔑 正在登录...")
    res = login_email(email, checkcode)
    print("   响应:", res)
    if res.get("status") != 0:
        print(f"❌ 登录失败: {res.get('msg', '未知错误')}")
        return ""

    token = res.get("data", {}).get("token")
    if not token:
        print("❌ 登录成功但未返回 token")
        return ""

    config.save_token(token)
    print(f"✅ 登录成功，Token 已保存至 {config.TOKEN_FILE}")
    return token


def ensure_token(force: bool = False) -> str:
    """
    确保有有效的 token：
    1. 先检查已保存的 token 是否有效
    2. 如果无效或不存在，执行登录
    返回 token 或空字符串。
    """
    if not force:
        existing = config.get_token()
        if existing:
            print("🔍 检查已有 token 有效性...")
            if verify_token(existing):
                print("✅ Token 有效，无需重新登录")
                return existing
            else:
                print("⚠️ Token 已过期，需要重新登录")
    return do_login(email=config.get_credentials()[0])


def main():
    """主流程"""
    print("===== iLink 登录获取 Token =====")

    auto = "--auto" in sys.argv
    email, _ = config.get_credentials()

    if not email:
        email = input("请输入登录邮箱: ").strip()
        if not email or "@" not in email:
            print("❌ 请输入有效的邮箱地址")
            return

    print(f"📧 邮箱: {email}")

    if auto:
        token = ensure_token()
        if not token:
            print("❌ 获取 token 失败")
            sys.exit(1)
    else:
        token = do_login(email)
        if not token:
            print("❌ 登录失败")
            sys.exit(1)

    print("🎉 完成")


if __name__ == "__main__":
    main()
