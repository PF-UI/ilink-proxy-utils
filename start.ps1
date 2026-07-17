# ============================================================================
# iLink 代理 — Windows PowerShell 一键启动
# ============================================================================
# 右键 start.ps1 -> 使用 PowerShell 运行
# 或: powershell -ExecutionPolicy Bypass -File start.ps1
# 启动后: 代理 127.0.0.1:8888 | 控制面板 http://127.0.0.1:8889
# ============================================================================

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "   iLink 代理启动中..."                   -ForegroundColor Cyan
Write-Host "========================================"  -ForegroundColor Cyan
Write-Host ""

python main.py start --compiled

if ($LASTEXITCODE -ne 0) {
    Write-Host "`n代理启动失败，按任意键退出..." -ForegroundColor Red
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}
