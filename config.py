# -*- coding: utf-8 -*-
"""
统一配置模块：从 .env 文件加载凭据，供所有脚本使用。
"""
import os
import sys

# Windows 控制台 UTF-8 支持
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(SCRIPT_DIR, ".env")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.txt")
LINES_FILE = os.path.join(SCRIPT_DIR, "lines.json")
PROXY_AUTH_FILE = os.path.join(SCRIPT_DIR, "proxy_auth.json")
PROXY_CURRENT_FILE = os.path.join(SCRIPT_DIR, "proxy_current.json")
PAC_FILE = os.path.join(SCRIPT_DIR, "proxy.pac")

# API 常量
BASE = "https://cerest.i-linka.com"
SIGN_SUFFIX = "cef949d30232cf00bfabba46ac5c16e2"

# 默认线路
DEFAULT_SID = "sg-bgp"


def load_env():
    """从 .env 文件加载配置，返回字典"""
    cfg = {}
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    cfg[key.strip()] = value.strip().strip('"').strip("'")
    return cfg


def get_credentials():
    """获取登录凭据（邮箱、密码），优先从 .env 读取"""
    env = load_env()
    email = env.get("user_name", "")
    password = env.get("user_password", "")
    return email, password


def get_token():
    """获取保存的 token"""
    if os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""


def save_token(token: str):
    """保存 token 到文件"""
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(token)
