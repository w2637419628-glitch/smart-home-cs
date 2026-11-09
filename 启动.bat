@echo off
chcp 65001 >nul
title 会进化的智能家居客服
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [x] 没找到 python。请先装 Python 3.10+ 并勾选 Add Python to PATH。
  echo     下载：https://www.python.org/downloads/
  pause
  exit /b 1
)

python start.py
if errorlevel 1 pause
