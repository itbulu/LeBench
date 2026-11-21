# LeBench

Linux 五类服务器统一评测工具（独立 Python CLI）。

仓库：[https://github.com/itbulu/LeBench](https://github.com/itbulu/LeBench)  
当前版本 **0.2.0**（S0–S4 已实现；S5 网站 JSON Schema 导出仍预留）。

---

## 快速开始（推荐）

在 **非生产 Linux VPS** 上：

```bash
# 1) 下载安装脚本并审阅
curl -fsSL -o install.sh https://raw.githubusercontent.com/itbulu/LeBench/main/install.sh
less install.sh

# 2) 一键安装（系统依赖 + Python 环境）
bash install.sh --yes --repo https://github.com/itbulu/LeBench.git

# 3) 加入 PATH 后检查环境
export PATH="$HOME/.local/bin:$PATH"
lebench --version
lebench doctor
```

或先克隆再装：

```bash
git clone https://github.com/itbulu/LeBench.git
cd LeBench
bash install.sh --local --yes
export PATH="$HOME/.local/bin:$PATH"
```

更多安装参数见 [docs/install.md](docs/install.md)。  
卸载：`bash install.sh --uninstall`（不卸载系统包）。

---

## 如何跑评测

### 1. 先看环境

```bash
lebench doctor      # 依赖/权限/磁盘空间（只检查，不安装）
lebench profiles    # 五种产品类型与默认模块
lebench modules     # 各模块是否可用
```

### 2. 按强度测试

| 强度 | 做什么 | 命令 |
|------|--------|------|
| `quick` | system + 短 CPU/内存 | `lebench run --profile vps --intensity quick --yes --output-dir ./reports` |
| `standard` | + 磁盘 DD/FIO + 网络/Ping | `lebench run --profile vps --intensity standard --yes --output-dir ./reports` |
| `deep` | + 路由/IP/兼容性/稳定性 | `lebench run --profile vps --intensity deep --confirm-deep --output-dir ./reports` |

说明：

- `--yes`：跳过 **standard** 的预算确认；**不能**代替 deep 的 `--confirm-deep`
- 报告输出在 `./reports/`：`*.txt`（可读）+ `*.internal.json`（内部快照，非网站导入格式）

### 3. 五种 Profile

```bash
# VPS（默认公共性能）
lebench run --profile vps --intensity standard --yes --output-dir ./reports

# 独立服务器（含物理硬件只读探测）
lebench run --profile dedicated --intensity standard --yes --output-dir ./reports

# GPU 机（无卡会 not_applicable）
lebench run --profile gpu --intensity standard --yes --output-dir ./reports

# 轻量应用云（应用压测需显式开启）
lebench run --profile lightweight --enable-app-perf --intensity standard --yes --output-dir ./reports

# 裸金属（含 cloud_delivery 占位，不调云 API）
lebench run --profile bare_metal --intensity standard --yes --output-dir ./reports
```

Profile 名称注意：是 `bare_metal`，不是 `baremetal`。

### 4. 只跑部分模块 / 跳过模块

```bash
lebench run --profile vps --modules system,cpu,memory,disk_fio --yes --output-dir ./reports
lebench run --profile vps --intensity standard --skip network,ping --yes --output-dir ./reports
lebench run --profile vps --intensity quick --dry-run --output-dir ./reports   # 只预览，不执行
```

### 5. 网络 / Ping 要先配节点

未配置时 `network` 为 `not_run`（不会虚构三网成绩）。

```bash
cd LeBench   # 源码目录
cp lebench/data/ping_targets.example.yaml ./ping_targets.yaml
cp lebench/data/speedtest_targets.example.yaml ./speedtest_targets.yaml
# 编辑 speedtest_targets.yaml：把节点 enabled 改为 true，并填写可信测速 URL

lebench run --profile vps --intensity standard --yes --config-dir . --output-dir ./reports
```

### 6. 可选开关

```bash
# 本机已安装 Geekbench 时才测（不下载、不内嵌）
lebench run --profile vps --modules cpu --enable-geekbench --yes --output-dir ./reports

# 流媒体/AI 可达性探测（HTTP 200 ≠ 完整解锁）
lebench run --profile vps --modules compatibility --enable-compatibility --yes --output-dir ./reports

# 本地回环轻量 HTTP 压测
lebench run --profile lightweight --modules app_perf --enable-app-perf --yes --output-dir ./reports

# 报告中保留敏感信息（默认脱敏）
lebench run --profile vps --intensity quick --yes --allow-sensitive --output-dir ./reports
```

---

## 验收建议（Linux 实机）

按顺序执行，把 `reports/` 里 TXT 留下即可验收：

```bash
lebench doctor | tee doctor.json
lebench run --profile vps --intensity quick --yes --output-dir ./reports
lebench run --profile vps --intensity standard --yes --output-dir ./reports

# 缺工具时应为 not_run / permission_denied，其它模块继续
# 确认没有对 /dev/sd*、/dev/nvme* 写测
```

完整清单：[docs/linux-smoke-test.md](docs/linux-smoke-test.md)

开发者单元测试：

```bash
python3 -m pip install -e ".[dev]"
pytest -q
```

---

## 手动安装（不走一键脚本）

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sysbench fio iputils-ping traceroute

git clone https://github.com/itbulu/LeBench.git
cd LeBench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
lebench --version
```

RHEL 系可用 `bash scripts/install_deps.sh --yes`。

---

## 安全要点

- 默认脱敏；`--allow-sensitive` 才保留公网 IP 等
- 磁盘测试只写临时普通文件，禁止块设备
- 安装脚本可能使用 sudo 装系统包；装完默认只跑 `doctor`，不自动压测
- 输出格式 `lebench-internal-v0` **不是**乐在云网站导入协议

## 文档索引

| 文档 | 内容 |
|------|------|
| [docs/install.md](docs/install.md) | 安装参数、卸载 |
| [docs/linux-smoke-test.md](docs/linux-smoke-test.md) | Linux 冒烟步骤 |
| [docs/module-coverage.md](docs/module-coverage.md) | 模块覆盖状态 |
| [docs/开发完成说明_0.2.0.md](docs/开发完成说明_0.2.0.md) | 版本说明 |

## License

MIT
