# 演示用镜像：只跑 FastAPI，模型调用走外部 API
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8100

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py .

# 数据库放到挂载卷里，容器重建不丢
ENV DSH_DB_PATH=/data/data.db
RUN mkdir -p /data

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8100/api/status',timeout=4).status==200 else 1)"

CMD ["python", "run.py"]
