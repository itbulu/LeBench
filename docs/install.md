# LeBench 安装说明

仓库：https://github.com/itbulu/LeBench

## 方式一：一键安装（可先审再跑）

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/itbulu/LeBench/main/install.sh
less install.sh
bash install.sh --yes
```

常用参数：

| 参数 | 含义 |
|------|------|
| `--yes` | 非交互安装系统依赖 |
| `--local` | 用当前源码树安装（clone 后在仓库内执行） |
| `--no-deps` | 不装 apt/dnf 包 |
| `--deps-only` | 只装系统依赖 |
| `--ref v0.2.0` | 指定 tag/分支 |
| `--repo URL` | 自定义 Git 地址（默认已指向 itbulu/LeBench） |
| `--uninstall` | 卸载用户级 venv 与 wrapper |

默认安装位置：

- 程序/venv：`~/.local/share/lebench`
- 命令包装：`~/.local/bin/lebench`

## 方式二：从已克隆仓库安装

```bash
git clone https://github.com/itbulu/LeBench.git
cd LeBench
bash install.sh --local --yes
export PATH="$HOME/.local/bin:$PATH"
lebench doctor
```

## 方式三：完全手动（最易审计）

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sysbench fio iputils-ping traceroute

git clone https://github.com/itbulu/LeBench.git
cd LeBench
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
lebench doctor
```

## 卸载

```bash
bash install.sh --uninstall
# 系统包（sysbench/fio 等）不会自动删除
```

## 安全说明

- 一键脚本可能请求 `sudo` 安装系统包；请先阅读 `install.sh` / `scripts/*`。
- 安装结束默认只跑 `doctor`，**不会**自动执行磁盘/网络压测。
- `curl | bash` 不是唯一方式；生产环境建议下载审阅后再执行。
