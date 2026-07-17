# -*- coding: utf-8 -*-
"""
iLink 代理转本地 — 统一入口脚本
================================
用法:
    python main.py setup      # 完整初始化：检查/登录 → 获取线路 → 获取代理信息
    python main.py login      # 仅登录获取 token
    python main.py lines      # 获取线路列表
    python main.py proxy [sid] # 获取指定线路代理信息（默认 sg-bgp）
    python main.py start      # 启动 Go 代理服务器
    python main.py test       # 测试代理是否工作
    python main.py all        # 一键完成：setup + start + test
"""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

# Windows 控制台 UTF-8 支持
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import config


def step_separator(title: str):
    """打印分隔标题"""
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}\n")


def cmd_login() -> bool:
    """登录获取 token"""
    step_separator("步骤 1: 登录获取 Token")
    subprocess.run([sys.executable, "login.py", "--auto"], cwd=config.SCRIPT_DIR)
    token = config.get_token()
    if token:
        print("✅ Token 就绪")
        return True
    else:
        print("❌ Token 获取失败，尝试交互式登录...")
        subprocess.run([sys.executable, "login.py"], cwd=config.SCRIPT_DIR)
        token = config.get_token()
        return bool(token)


def cmd_lines() -> bool:
    """获取线路列表"""
    step_separator("步骤 2: 获取线路列表")
    result = subprocess.run(
        [sys.executable, "linelist.py", "--auto"],
        cwd=config.SCRIPT_DIR
    )
    return result.returncode == 0


def cmd_proxy(sid: str = None) -> bool:
    """获取代理信息"""
    sid = sid or config.DEFAULT_SID
    step_separator(f"步骤 3: 获取线路 [{sid}] 代理认证信息")
    result = subprocess.run(
        [sys.executable, "get_proxy_info.py", sid],
        cwd=config.SCRIPT_DIR
    )
    return result.returncode == 0


def cmd_setup():
    """完整初始化"""
    print("\n🚀 iLink 代理初始化\n")
    if not cmd_login():
        print("❌ 登录失败，终止")
        return False

    if not cmd_lines():
        print("⚠️ 线路列表获取失败，继续...")

    if not cmd_proxy(config.DEFAULT_SID):
        print("❌ 代理信息获取失败，终止")
        return False

    print("\n✅ 初始化完成！现在可以运行: python main.py start 启动代理")
    return True


def check_port(port: int) -> bool:
    """检查端口是否被占用，返回 True 表示可用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    return result != 0  # 非 0 表示连接失败，端口空闲


def find_proxy_processes() -> list:
    """查找正在运行的 proxy_manager 进程（返回 PID 列表）"""
    pids = []
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq proxy_manager.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.replace('"', "").split(",")
                    if len(parts) >= 2:
                        try:
                            pids.append(int(parts[1]))
                        except ValueError:
                            pass
        else:
            result = subprocess.run(
                ["pgrep", "-f", "proxy_manager"],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    pids.append(int(line.strip()))
    except Exception:
        pass
    return pids


def kill_proxy_processes():
    """强制终止所有 proxy_manager 进程"""
    pids = find_proxy_processes()
    if not pids:
        return

    print(f"⚠️ 发现 {len(pids)} 个旧代理进程 (PID: {', '.join(map(str, pids))})，正在清理...")
    try:
        if sys.platform == "win32":
            for pid in pids:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            for pid in pids:
                os.kill(pid, signal.SIGKILL)
        print("✅ 旧进程已清理")
        time.sleep(1)  # 等待端口释放
    except Exception as e:
        print(f"❌ 清理失败: {e}")


def cmd_start():
    """启动 Go 代理"""
    step_separator("启动 Go 代理服务器")

    go_dir = os.path.join(config.SCRIPT_DIR, "proxy_manager")
    compiled = "--compiled" in sys.argv
    exe_path = os.path.join(go_dir, "proxy_manager.exe")
    use_compiled = compiled and os.path.isfile(exe_path)

    # 使用预编译 exe 时无需 Go；否则检查 Go 环境
    if not use_compiled:
        try:
            subprocess.run(["go", "version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            if compiled:
                print(f"❌ 未找到预编译文件 {exe_path}，且本机无 Go 环境")
                print("   请放置 proxy_manager.exe，或安装 Go: https://go.dev/dl/")
            else:
                print("❌ 未找到 Go 环境，请先安装 Go: https://go.dev/dl/")
            return

    # 检查 proxy_current.json
    if not os.path.isfile(config.PROXY_CURRENT_FILE):
        print(f"⚠️ 未找到 {config.PROXY_CURRENT_FILE}，尝试初始化...")
        if not cmd_setup():
            return

    # 端口冲突检测与自动清理
    ports_occupied = []
    for port in [8888, 8889]:
        if not check_port(port):
            ports_occupied.append(port)
    if ports_occupied:
        print(f"⚠️ 端口 {', '.join(map(str, ports_occupied))} 已被占用，尝试自动清理...")
        kill_proxy_processes()
        # 再次检查
        still_occupied = [p for p in ports_occupied if not check_port(p)]
        if still_occupied:
            print(f"❌ 端口 {', '.join(map(str, still_occupied))} 仍被占用（可能被其他程序占用）")
            print("   请手动查看: netstat -ano | findstr :8888")
            return
        print("✅ 端口已释放\n")

    # 预览当前配置
    try:
        with open(config.PROXY_CURRENT_FILE, "r", encoding="utf-8") as f:
            auth = json.load(f)
        print(f"   当前线路: {auth.get('sid', '?')}")
        print(f"   用户名:   {auth.get('username', '?')}")
        print(f"   密码:     {'*' * len(auth.get('password', ''))}")
    except Exception:
        pass

    print(f"\n   本地代理:  127.0.0.1:8888")
    print(f"   控制面板:  http://127.0.0.1:8889")
    print(f"\n   按 Ctrl+C 停止\n")

    # 启动 Go 代理（阻塞运行，窗口保持打开以显示日志）
    if use_compiled:
        print(f"   使用预编译: {exe_path}")
        subprocess.run([exe_path], cwd=go_dir)
    elif compiled:
        print(f"⚠️ 未找到预编译文件 {exe_path}，回退到 go run")
        subprocess.run(["go", "run", "."], cwd=go_dir)
    else:
        subprocess.run(["go", "run", "."], cwd=go_dir)


def cmd_test():
    """测试代理是否工作"""
    step_separator("测试代理连接")

    proxy_url = "http://127.0.0.1:8888"

    # 1. 健康检查
    print("1. 检查代理服务状态...")
    try:
        req = urllib.request.Request("http://127.0.0.1:8888/api/health")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        print(f"   ✅ 代理状态: {data.get('status')}, 线路: {data.get('sid')}")
    except Exception as e:
        print(f"   ❌ 代理未运行: {e}")
        print("   请先启动: python main.py start")
        return

    # 2. 通过代理访问测试网站
    print("\n2. 通过代理访问外部网站...")
    test_urls = [
        ("https://www.google.com", "Google"),
        ("https://www.github.com", "GitHub"),
    ]

    for url, name in test_urls:
        try:
            proxy_handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url,
            })
            opener = urllib.request.build_opener(proxy_handler)
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            })
            resp = opener.open(req, timeout=15)
            print(f"   ✅ {name}: HTTP {resp.status}")
            resp.close()
        except Exception as e:
            print(f"   ❌ {name}: {e}")

    print("\n✅ 测试完成")


def cmd_stop():
    """停止所有代理进程"""
    step_separator("停止代理服务器")
    pids = find_proxy_processes()
    if not pids:
        print("✅ 没有运行中的代理进程")
        return
    kill_proxy_processes()
    print("✅ 代理已停止")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("可用命令: setup, login, lines, proxy, start, test, all")
        return

    cmd = sys.argv[1].lower()
    sid = sys.argv[2] if len(sys.argv) >= 3 else None

    if cmd == "setup":
        cmd_setup()
    elif cmd == "login":
        cmd_login()
    elif cmd == "lines":
        cmd_lines()
    elif cmd == "proxy":
        cmd_proxy(sid)
    elif cmd == "start":
        cmd_start()
    elif cmd == "test":
        cmd_test()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "all":
        print("\n🚀 一键启动 iLink 代理转本地\n")
        if cmd_setup():
            print("\n⏳ 3 秒后启动代理服务器...")
            time.sleep(1)
            cmd_start()
    else:
        print(f"未知命令: {cmd}")
        print("可用命令: setup, login, lines, proxy, start, test, all")


if __name__ == "__main__":
    main()
