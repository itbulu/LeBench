#!/usr/bin/env bash
# install.sh - install LZY Bench dependencies on Ubuntu/Debian
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[ERROR] 请使用 root 运行: sudo ./install.sh" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "[INFO] 更新 apt 索引..."
apt-get update -y

echo "[INFO] 安装基础依赖..."
apt-get install -y \
  curl wget ca-certificates \
  jq \
  fio \
  sysbench \
  iproute2 \
  iputils-ping \
  traceroute \
  whois \
  dnsutils \
  lsb-release \
  procps \
  util-linux \
  coreutils \
  findutils \
  gawk \
  tar \
  gzip

apt-get install -y mtr-tiny 2>/dev/null || apt-get install -y mtr 2>/dev/null \
  || echo "[WARN] mtr 未安装（线路检测仍可用 traceroute）"

# speedtest: prefer Ookla official if available, else speedtest-cli via pip/apt
echo "[INFO] 安装 Speedtest..."
if apt-get install -y speedtest-cli 2>/dev/null; then
  echo "[OK] speedtest-cli 已安装"
else
  echo "[WARN] apt 无 speedtest-cli，尝试 Ookla 仓库..."
  if curl -s https://packagecloud.io/install/repositories/ookla/speedtest-cli/script.deb.sh | bash; then
    apt-get install -y speedtest || echo "[WARN] Ookla speedtest 安装失败，网络模块将跳过 speedtest"
  else
    echo "[WARN] Speedtest 未安装，可稍后手动安装"
  fi
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "${ROOT}/benchmark.sh"
chmod +x "${ROOT}/install.sh"
find "${ROOT}/modules" -name 'run.sh' -exec chmod +x {} \;
find "${ROOT}/core" -name '*.sh' -exec chmod +x {} \;

# Optional symlink
if [[ -d /usr/local/bin ]]; then
  ln -sfn "${ROOT}/benchmark.sh" /usr/local/bin/lzy-bench
  echo "[OK] 已创建命令: lzy-bench -> ${ROOT}/benchmark.sh"
fi

echo ""
echo "[OK] 依赖安装完成。运行示例:"
echo "  sudo lzy-bench version"
echo "  sudo lzy-bench system"
echo "  sudo lzy-bench"
