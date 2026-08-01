# LZY Bench — LeZaiYun Benchmark Toolkit

**品牌**：LeZaiYun（乐在云）  
**版本**：1.3.2-p1  
**理念**：Once Test, Multiple Output — 一次测试，多种输出。  
**仓库**：[https://github.com/itbulu/LeBench](https://github.com/itbulu/LeBench)

Linux CLI 评测 + Platform（Dashboard / API / 排行榜 / 多机对比）。

对照融合怪优化说明：[`docs/COMPARISON_ECS.md`](docs/COMPARISON_ECS.md)

## 一键安装（推荐）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh)
bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh) --run-lite
```

## 快速开始（CLI）

```bash
git clone https://github.com/itbulu/LeBench.git
cd LeBench
sudo ./install.sh
sudo ./benchmark.sh
# SSH 不稳定时：screen/tmux 跑完后直接看文本摘要
cat results/*/summary.txt
cat reports/*/summary.txt
```

## 快速开始（Platform）

```bash
cd platform
./run.sh
# 浏览器打开 http://127.0.0.1:8787/
```

详见 [`platform/README.md`](platform/README.md) 与 [`docs/API.md`](docs/API.md)。

## 命令摘要

| 命令 | 说明 |
|------|------|
| `all` | 全量评测（含 IP 质量 / Docker / WP） |
| `ipquality` | IP 质量（代理/机房/DNSBL/邮件端口） |
| `route` / `streaming` | 线路（含带宽类型）/ 解锁 |
| `docker` / `wordpress` | 应用测试 |
| `score` / `report` / `upload` | 评分 / 报告 / 上报 |

## 阶段状态

| 阶段 | 状态 |
|------|------|
| Phase 1–4 | 完成 |
| ecs 对照 P0 | 一键安装 / IP 质量 / 带宽类型 / 解锁增强 |
| ecs 对照 P1 | 三网下载测速 / summary.txt / dd 快测 |

## License

待定。
