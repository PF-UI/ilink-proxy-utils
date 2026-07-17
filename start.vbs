' ============================================================================
' iLink 代理 — Windows 一键启动（双击此文件即可，无命令行窗口）
' ============================================================================
' 双击 start.vbs 即可在后台启动代理，随系统静默运行
' 启动后: 代理 127.0.0.1:8888 | 控制面板 http://127.0.0.1:8889
' ============================================================================

Dim WshShell, scriptDir, cmd

Set WshShell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

cmd = "cd /d """ & scriptDir & """ && python main.py start --compiled"
WshShell.Run "cmd /c " & cmd, 0, False   ' 0 = 隐藏窗口, False = 不等待

Set WshShell = Nothing
