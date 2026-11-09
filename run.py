"""启动入口。

本地：python run.py            → http://127.0.0.1:8100
服务器：HOST=0.0.0.0 PORT=80 python run.py
"""
import os

import uvicorn

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8100"))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)
