#!/usr/bin/env bash
# ============================================================================
# iLink 代理 — 停止脚本 (Linux / macOS)
# ============================================================================
# chmod +x stop.sh && ./stop.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "   iLink 代理停止中..."
echo "========================================"
echo ""

# 杀掉 proxy_manager 进程
pids=$(pgrep -f proxy_manager 2>/dev/null || true)
if [ -n "$pids" ]; then
    echo "发现进程: $pids"
    kill $pids 2>/dev/null || true
    sleep 1
    # 强制杀掉残留
    pids=$(pgrep -f proxy_manager 2>/dev/null || true)
    if [ -n "$pids" ]; then
        kill -9 $pids 2>/dev/null || true
    fi
    echo "代理已停止"
else
    echo "没有运行中的代理"
fi
