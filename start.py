# -*- coding: utf-8 -*-
"""一键本地启动：检查环境 → 起服务 → 自动打开浏览器。

用法：
    双击 启动.bat            （Windows 最省事）
    或 python start.py
    换端口：set PORT=8101 && python start.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
os.chdir(BASE)

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8100"))
URL = f"http://{HOST}:{PORT}"

MAIN = "\n".join([
    "",
    "  会进化的智能家居客服 · Agent Loop + 自进化",
    "  ------------------------------------------------",
])

REQUIRED = ["fastapi", "uvicorn", "pydantic", "dotenv", "openai"]


def check_deps() -> list[str]:
    import importlib.util
    return [m for m in REQUIRED if importlib.util.find_spec(m) is None]


def port_busy(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def open_browser_later(seconds: float = 2.5) -> None:
    def _run():
        time.sleep(seconds)
        try:
            webbrowser.open(URL + "/docs")
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


def main() -> int:
    print(MAIN)

    # 1) 依赖
    missing = check_deps()
    if missing:
        print(f"  [×] 缺少依赖：{', '.join(missing)}")
        print("      这台机器上装一次即可：")
        print("        pip install -r requirements.txt")
        print("      网络慢就用国内镜像：")
        print("        pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple")
        return 1

    # 2) 配置
    if not (BASE / ".env").exists():
        print("  [!] 没有 .env —— 将以【离线桩 mock】模式运行")
        print("      想接真实大模型：copy .env.example .env 后填入 LLM_API_KEY")
    else:
        provider = "未知"
        for line in (BASE / ".env").read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("LLM_PROVIDER="):
                provider = line.split("=", 1)[1].strip()
        print(f"  [√] 读取 .env，模型提供方 = {provider}")

    # 3) 端口
    if port_busy(HOST, PORT):
        print(f"\n  [!] 端口 {PORT} 已被占用 —— 大概率已经启动过了。")
        print(f"      直接打开：{URL}")
        print("      想另起一个：set PORT=8101 && python start.py")
        webbrowser.open(URL + "/docs")
        try:
            input("\n  按回车关闭本窗口…")
        except EOFError:
            pass
        return 0

    # 4) 起服务
    print(f"\n  [启动] {URL}")
    print("  首次启动会自动建库并灌入 20 条种子话术")
    print("  关闭服务：在这个窗口按 Ctrl+C，或直接关掉窗口\n")

    open_browser_later()

    import uvicorn  # 放到最后一刻导入，前面的错误提示才有意义
    try:
        uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False, log_level="info")
    except KeyboardInterrupt:
        print("\n  已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
