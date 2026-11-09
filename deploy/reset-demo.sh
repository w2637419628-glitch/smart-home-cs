#!/usr/bin/env bash
# 把演示环境恢复到出厂状态：清空所有教学样本 / 工单 / 总纲，只留 20 条种子话术
# 用法：在服务器上执行  bash deploy/reset-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB="${DSH_DB_PATH:-$ROOT/data.db}"

echo "==> 目标数据库：$DB"
read -r -p "会清空所有教学数据，确定吗？(y/N) " ok
[[ "$ok" =~ ^[Yy]$ ]] || { echo "已取消"; exit 0; }

if docker ps --format '{{.Names}}' | grep -q '^smart-home-cs$'; then
  echo "==> 检测到容器运行，先停止"
  docker stop smart-home-cs >/dev/null
  rm -f "$DB"
  docker start smart-home-cs >/dev/null
else
  echo "==> 裸机模式"
  sudo systemctl stop smart-home-cs || true
  rm -f "$DB"
  sudo systemctl start smart-home-cs || true
fi

echo "==> 完成。首次访问会自动重建 20 条种子话术。"
