#!/usr/bin/env bash
# ============================================================================
# iLink 代理 — Linux / macOS 一键启动
# ============================================================================
# chmod +x start.sh && ./start.sh
# 启动后: 代理 127.0.0.1:8888 | 控制面板 http://127.0.0.1:8889
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo "   iLink 代理启动中..."
echo "========================================"
echo ""

# 尝试预编译二进制，失败则 go run
GO_DIR="$SCRIPT_DIR/proxy_manager"
if [ -f "$GO_DIR/proxy_manager" ]; then
    echo "[信息] 使用预编译二进制: proxy_manager"
    "$GO_DIR/proxy_manager"
else
    echo "[信息] 编译并启动..."
    python3 main.py start
fi
