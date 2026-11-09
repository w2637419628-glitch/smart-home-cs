@echo off
chcp 65001 >nul
title 停止服务
cd /d "%~dp0"

set PORT=8100
if not "%1"=="" set PORT=%1

echo 正在查找占用 %PORT% 端口的进程...
powershell -NoProfile -Command ^
  "$c = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; if (-not $c) { Write-Host '没有进程在监听 %PORT%' } else { $c | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Write-Host ('停止 PID ' + $_); Stop-Process -Id $_ -Force } ; Write-Host '已停止' }"

timeout /t 2 >nul
