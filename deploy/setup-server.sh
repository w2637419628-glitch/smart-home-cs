#!/usr/bin/env bash
# 一键把体验站跑起来（Ubuntu / Debian）
#
# 用法：
#   1) 传代码到服务器：/opt/smart-home-cs
#   2) cd /opt/smart-home-cs
#   3) bash deploy/setup-server.sh
#
# 环境变量（可选）：
#   APP_PORT=8080     对外端口
#   SKIP_DOCKER=1     跳过 Docker 安装
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PORT="${APP_PORT:-8080}"

say() { printf "\n\033[1;36m==> %s\033[0m\n" "$*"; }
die() { printf "\n\033[1;31m[×] %s\033[0m\n" "$*"; exit 1; }

say "项目目录：$ROOT"

# ---------- 1. 配置文件 ----------
if [ ! -f .env ]; then
  cp .env.example .env
  die "已生成 .env，请先填入 LLM_API_KEY，然后重新运行本脚本：
      nano $ROOT/.env"
fi

if ! grep -q '^LLM_API_KEY=..*' .env; then
  die " .env 里的 LLM_API_KEY 还是空的，先填上：
      nano $ROOT/.env"
fi

# 体验站默认开启额度限制（防止公开链接被刷爆）
grep -q '^DEMO_MODE='          .env || echo 'DEMO_MODE=true'          >> .env
grep -q '^DEMO_PER_IP_DAILY='  .env || echo 'DEMO_PER_IP_DAILY=30'    >> .env
grep -q '^DEMO_GLOBAL_DAILY='  .env || echo 'DEMO_GLOBAL_DAILY=800'   >> .env
chmod 600 .env
say "配置就绪：$(grep '^DEMO_MODE=' .env)"

# ---------- 2. Docker ----------
if [ "${SKIP_DOCKER:-0}" != "1" ]; then
  if ! command -v docker >/dev/null 2>&1; then
    say "安装 Docker（约 1 分钟）"
    curl -fsSL https://get.docker.com | sh
  else
    say "Docker 已安装：$(docker --version)"
  fi
fi

# ---------- 3. 端口检查 ----------
if command -v ss >/dev/null 2>&1 && ss -ltn | grep -q ":$PORT "; then
  die "本机 $PORT 端口已被占用，换个端口：APP_PORT=8081 bash deploy/setup-server.sh"
fi

# ---------- 4. 启动 ----------
say "构建并启动（首次约 1-2 分钟）"
cd "$ROOT/deploy"
APP_PORT="$PORT" docker compose up -d --build

# ---------- 5. 自检 ----------
say "等待服务就绪"
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if curl -fsS "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1; then
  IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '服务器公网IP')"
  say "本机自测通过 ✅"
  cat <<EOF

  对外地址：http://$IP:$PORT

  ⚠️ 如果外面打不开，99% 是云厂商「安全组 / 防火墙」没放行 $PORT：
     阿里云：控制台 → 轻量服务器 → 防火墙 → 添加规则 → TCP $PORT
     腾讯云：控制台 → 防火墙 → 添加规则 → TCP $PORT

  常用命令：
    cd $ROOT/deploy
    docker compose logs -f --tail=100     # 看日志
    docker compose restart                # 重启
    docker compose down && docker compose up -d --build   # 改完代码重建
    bash $ROOT/deploy/reset-demo.sh       # 清空演示数据

EOF
else
  echo
  say "自测失败，最近日志："
  docker compose logs --tail=60 || true
  die "检查上面的报错，常见原因：LLM_API_KEY 未填 / 端口冲突 / 构建失败"
fi
