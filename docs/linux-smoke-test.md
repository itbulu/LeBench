# Linux VPS 冒烟 / 验收

仓库：https://github.com/itbulu/LeBench

## 安装后最小路径

```bash
export PATH="$HOME/.local/bin:$PATH"
lebench --version
lebench doctor | tee doctor.json

# 快速：验证 CLI + system/cpu/memory 调度
lebench run --profile vps --intensity quick --yes --output-dir ./reports

# 标准：含磁盘；网络无配置时为 not_run
lebench run --profile vps --intensity standard --yes --output-dir ./reports
```

## 配齐依赖再测（Debian/Ubuntu）

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sysbench fio iputils-ping traceroute

git clone https://github.com/itbulu/LeBench.git
cd LeBench
bash install.sh --local --yes
export PATH="$HOME/.local/bin:$PATH"
```

## 网络 / Ping

```bash
cp lebench/data/ping_targets.example.yaml ./ping_targets.yaml
cp lebench/data/speedtest_targets.example.yaml ./speedtest_targets.yaml
# 编辑 speedtest_targets.yaml：enabled: true + 可信 URL

lebench run --profile vps --intensity standard --yes --config-dir . --output-dir ./reports
```

## 五类 Profile 抽查

```bash
lebench run --profile dedicated --modules system,physical --yes --output-dir ./reports
lebench run --profile gpu --modules system,gpu --yes --output-dir ./reports
lebench run --profile lightweight --enable-app-perf --modules system,app_perf --yes --output-dir ./reports
lebench run --profile bare_metal --modules system,physical,cloud_delivery --yes --output-dir ./reports
```

## 开发自检

```bash
pytest -q
```

## 验收关注点

1. 缺工具 / 无 root 时模块为 `not_run` 或 `permission_denied`，其它模块继续  
2. 无块设备写入（`/dev/sd*`、`/dev/nvme*`）  
3. 报告含工具版本、条件、单位、跳过原因  
4. TXT + internal JSON 均在 `./reports/`
