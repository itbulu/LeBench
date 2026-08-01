# LZY Bench — LeZaiYun Benchmark Toolkit

**品牌**：LeZaiYun（乐在云）  
**版本**：1.3.0-platform（Phase 4）  
**理念**：Once Test, Multiple Output — 一次测试，多种输出。

Linux CLI 评测 + Platform（Dashboard / API / 排行榜 / 多机对比）。

## 快速开始（CLI）

```bash
sudo ./install.sh
sudo ./benchmark.sh
```

## 快速开始（Platform）

```bash
cd platform
./run.sh
# 浏览器打开 http://127.0.0.1:8787/
# 演示数据：python scripts/seed_demo.py
```

上报最近一次评测：

```bash
./benchmark.sh upload
# 或带元数据
LZY_UPLOAD_LABEL="HK-Lite" LZY_UPLOAD_PROVIDER="DemoCloud" LZY_PRICE=4.99 ./benchmark.sh upload
```

详见 [`platform/README.md`](platform/README.md) 与 [`docs/API.md`](docs/API.md)。

## 命令摘要

| 命令 | 说明 |
|------|------|
| `all` | 全量评测（含 Docker/WP） |
| `docker` / `wordpress` | 应用测试 |
| `route` / `streaming` | 线路 / 解锁 |
| `score` / `report` | 评分 / 报告 |
| `upload` | 上报到 Platform API |

## 阶段状态

| 阶段 | 状态 |
|------|------|
| Phase 1 MVP | 完成 |
| Phase 2 标准版 | 完成 |
| Phase 3 专业版 | 完成 |
| Phase 4 平台化 | 完成（SQLite + FastAPI + Dashboard） |

## License

待定。
