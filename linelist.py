# -*- coding: utf-8 -*-
"""
获取 iLink 线路列表，按地区分组展示。
用法:
  1) 命令行传入 token: python linelist.py <token>
  2) 自动从 token.txt 读取: python linelist.py
  3) 自动登录获取: python linelist.py --auto
"""
import hashlib
import json
import os
import sys
import time
import requests
from typing import Dict, Any, List, Tuple

# Windows 控制台 UTF-8 支持
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

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


def make_common_body(token: str = "") -> Dict[str, Any]:
    """生成 api/servers 请求体"""
    return {
        "appver": "2.2.9",
        "device_name": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "token": token,
        "curr_server_id": "",
        "runtime_id": "",
        "from": "pc",
        "userIp": "",
    }


def get_servers(token: str) -> Dict[str, Any]:
    """请求 api/servers 获取线路列表"""
    try:
        url = f"{config.BASE}/api/servers"
        body = make_common_body(token=token)
        r = SESSION.post(
            url,
            headers=make_headers(token=token),
            data=body,
            timeout=15,
            verify=False,
        )
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {"status": -1, "msg": f"请求异常: {str(e)}"}


def parse_area_from_name(name: str) -> str:
    """从线路名称解析地区，如 'xxx(新加坡)' -> '新加坡'"""
    if not name or "(" not in name or ")" not in name:
        return ""
    start = name.index("(") + 1
    end = name.index(")")
    return name[start:end].strip()


def group_by_area(lines: List[Dict]) -> List[Tuple[str, List[Dict]]]:
    """按地区分组，返回 [(地区, [线路列表]), ...]，常见地区优先"""
    areas: Dict[str, List[Dict]] = {}
    for line in lines:
        area = parse_area_from_name(line.get("name", "")) or "未分类"
        if area not in areas:
            areas[area] = []
        areas[area].append(line)

    order = ["香港", "新加坡", "日本", "美国", "台湾", "韩国", "其他"]
    result = []
    for a in order:
        if a in areas:
            result.append((a, areas.pop(a)))
    for a in sorted(areas.keys()):
        result.append((a, areas[a]))
    return result


def save_lines(lines: list, filepath: str = None) -> bool:
    """保存线路列表到文件"""
    filepath = filepath or config.LINES_FILE
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(lines, f, ensure_ascii=False, indent=2)
        print(f"✅ 线路列表已保存至 {filepath}")
        return True
    except Exception as e:
        print(f"⚠️ 保存线路列表失败: {e}")
        return False


def print_lines(lines: list):
    """按地区分组打印线路信息"""
    grouped = group_by_area(lines)
    print(f"\n共 {len(lines)} 条线路，按地区分组:\n")
    print("-" * 72)
    for area, area_lines in grouped:
        print(f"【{area}】")
        for line in area_lines:
            name = line.get("name", "")
            sid = line.get("line_sn", "")
            connect = "可连接" if line.get("connect") else "已满员"
            vip = line.get("vip_level", 0)
            vip_tag = f" VIP{vip}" if vip else ""
            desc = (line.get("line_desc") or "").strip()
            if desc:
                print(f"  line_sn: {sid}  名称: {name}{vip_tag}  [{connect}]  {desc}")
            else:
                print(f"  line_sn: {sid}  名称: {name}{vip_tag}  [{connect}]")
        print()
    print("-" * 72)


def main():
    """主流程：读取 token -> 获取线路列表 -> 按地区打印"""
    token = ""
    if len(sys.argv) >= 2 and not sys.argv[1].startswith("--"):
        token = sys.argv[1].strip()

    if not token:
        token = config.get_token()

    # 自动登录模式
    if not token and "--auto" in sys.argv:
        print("⚠️ 未找到 token，尝试自动登录...")
        from login import ensure_token
        token = ensure_token()

    if not token:
        print("❌ 未找到 token，请先运行 login.py 登录获取 token")
        print("   或使用: python linelist.py --auto 自动登录")
        return

    print("正在获取线路列表...")
    res = get_servers(token)
    if res.get("status") != 0:
        print(f"❌ 获取线路列表失败: {res.get('msg', '未知错误')}")
        print("   可能 token 已过期，请重新运行: python login.py")
        return

    lines = res.get("data") or []
    if not lines:
        print("⚠️ 线路列表为空")
        return

    save_lines(lines)
    print_lines(lines)
    print("使用某条线路时: python get_proxy_info.py <line_sn>")


if __name__ == "__main__":
    main()
