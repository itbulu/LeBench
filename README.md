# LeBench

Linux 五类服务器统一评测工具（独立 Python CLI）。

当前版本 **0.2.0**：S0–S4 已实现；**S5 网站 JSON Schema 导出仍预留**。

## 一键安装（Linux VPS）

> 建议先下载审阅再执行（不要把 `curl | bash` 当唯一方式）。  
> 下面把 `YOUR_GITHUB_USER` 换成你的 GitHub 用户名/组织名。

```bash
# 1) 下载并审阅
curl -fsSL -o install.sh https://raw.githubusercontent.com/YOUR_GITHUB_USER/LeBench/main/install.sh
less install.sh

# 2) 安装（含系统依赖：python3/sysbench/fio/ping 等）
#    若默认仓库地址尚未改，请显式指定：
bash install.sh --yes --repo https://github.com/YOUR_GITHUB_USER/LeBench.git

# 3) 确保命令在 PATH
export PATH="$HOME/.local/bin:$PATH"
lebench doctor
lebench run --profile vps --intensity quick --yes --output-dir ./reports
```

从已克隆仓库安装（不依赖远程 URL）：

```bash
git clone https://github.com/YOUR_GITHUB_USER/LeBench.git
cd LeBench
bash install.sh --local --yes
```

完整参数与手动安装见 [docs/install.md](docs/install.md)。

卸载用户安装：`bash install.sh --uninstall`（不卸载系统包）。

## 手动安装

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sysbench fio iputils-ping traceroute

cd LeBench
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
lebench --version
```

RHEL 系请用 `dnf`/`yum`；或直接：`bash scripts/install_deps.sh --yes`。

## 常用命令

```bash
lebench doctor
lebench profiles
lebench modules

lebench run --profile vps --intensity quick --yes --output-dir ./reports
lebench run --profile vps --intensity standard --yes --output-dir ./reports

# deep 必须显式确认
lebench run --profile vps --intensity deep --confirm-deep --output-dir ./reports
```

五种 Profile：`vps`、`dedicated`、`gpu`、`lightweight`、`bare_metal`。

## 节点配置

```bash
cp lebench/data/ping_targets.example.yaml ./ping_targets.yaml
cp lebench/data/speedtest_targets.example.yaml ./speedtest_targets.yaml
# 编辑后启用节点
lebench run --profile vps --intensity standard --yes --config-dir . --output-dir ./reports
```

未配置有效测速节点时，`network` 为 `not_run`。

## 安全要点

- 默认脱敏；`--allow-sensitive` 才保留公网 IP 等
- 磁盘测试只写临时普通文件，禁止块设备
- `--yes` 可跳过标准预算确认，**不能**代替 `--confirm-deep`
- 安装脚本可能使用 sudo 装系统包；装完默认只跑 `doctor`
- 输出为 `lebench-internal-v0`，**不是**乐在云导入协议

## 开发与测试

```bash
pytest -q
```

模块覆盖见 [docs/module-coverage.md](docs/module-coverage.md)。  
Linux 冒烟见 [docs/linux-smoke-test.md](docs/linux-smoke-test.md)。

## License

MIT
