# Linux VPS 冒烟 / 验收

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip sysbench fio iputils-ping traceroute

cd /path/to/LeBench
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

lebench doctor | tee doctor.json
lebench run --profile vps --intensity quick --yes --output-dir ./reports
lebench run --profile vps --intensity standard --yes --output-dir ./reports

# 可选
cp lebench/data/ping_targets.example.yaml ./ping_targets.yaml
cp lebench/data/speedtest_targets.example.yaml ./speedtest_targets.yaml
# 编辑 speedtest_targets.yaml：enabled: true 并填写可信 URL

lebench run --profile dedicated --modules system,physical --yes
lebench run --profile gpu --modules system,gpu --yes
lebench run --profile lightweight --enable-app-perf --modules system,app_perf --yes
lebench run --profile bare_metal --modules system,physical,cloud_delivery --yes

pytest -q
```

关注：缺工具时模块为 `not_run`/`permission_denied` 且其它模块继续；无块设备写入；报告含条件与单位。
