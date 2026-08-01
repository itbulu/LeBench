# LZY Bench Platform（Phase 4）

Web Dashboard + REST API + SQLite，消费 CLI 产出的标准 JSON。

本文同时说明：**如何把整套工具部署到 Linux 云服务器并完成评测 → 上报 → 看板查看**。

**GitHub 仓库**：[https://github.com/itbulu/LeBench](https://github.com/itbulu/LeBench)

融合怪对照与优化路线：[`docs/COMPARISON_ECS.md`](../docs/COMPARISON_ECS.md)

---

## 一、服务器使用规范（部署与评测）

### 1.1 环境要求

| 项 | 要求 |
|----|------|
| 系统 | Ubuntu 20.04 / 22.04 / 24.04（推荐）；兼容 Debian 11+ |
| 权限 | 评测需 **root**（`sudo`） |
| 磁盘 | 建议预留数 GB（fio / Docker 镜像） |
| 网络 | 安装依赖、Speedtest、拉镜像、`git clone` 需要外网 |

生产业务机请谨慎全量压测，建议用测试机或低峰执行。

### 1.2 把项目放到服务器

**推荐：一键安装**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh)
# 安装并全量评测
bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh) --run
# 精简评测（含 ipquality，不含 docker/wordpress）
bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh) --run-lite
```

**或：从 GitHub 克隆**

```bash
# 若无 git：sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/itbulu/LeBench.git /opt/lzy-bench
cd /opt/lzy-bench
```

更新到最新代码：

```bash
cd /opt/lzy-bench
git pull origin main
```

**备选：本机 scp 上传**

```bash
scp -r "./LZY Bench" root@你的服务器IP:/opt/lzy-bench
# 或上传解压后的 LeBench 目录
```

也可用 SFTP / 面板将整个目录上传到 `/opt/lzy-bench`。

### 1.3 安装 CLI 依赖

```bash
cd /opt/lzy-bench
chmod +x benchmark.sh install.sh
sudo ./install.sh
```

会安装 jq、fio、sysbench、traceroute 等，并尽量创建命令 `lzy-bench`。

### 1.4 运行评测

```bash
# 版本
sudo lzy-bench version
# 或
sudo ./benchmark.sh version

# 全量评测（含线路 / 流媒体 / Docker / WordPress，首次较久）
sudo ./benchmark.sh

# 只要基础项（更快）：写入本地配置后全量
cat > config/local.conf <<'EOF'
LZY_DEFAULT_MODULES="system cpu memory disk network route streaming"
EOF
sudo ./benchmark.sh

# 单独模块
sudo ./benchmark.sh system
sudo ./benchmark.sh cpu
sudo ./benchmark.sh disk
sudo ./benchmark.sh network
sudo ./benchmark.sh route
sudo ./benchmark.sh streaming
sudo ./benchmark.sh docker
sudo ./benchmark.sh wordpress
```

### 1.5 结果与报告位置

| 路径 | 内容 |
|------|------|
| `results/<run_id>/` | 各模块 JSON、`score.json`、`summary.json` |
| `reports/<run_id>/report.md` | Markdown 报告（可发 WordPress） |
| `reports/<run_id>/report.html` | HTML 报告（浏览器打开） |
| `reports/<run_id>/summary.txt` | 纯文本摘要（SSH/screen 友好） |
| `results/<run_id>/summary.txt` | 同上（结果目录副本） |
| `logs/<YYYYMMDD>/` | 分模块日志 |

查看 HTML：下载到本地打开，或临时托管：

```bash
cd reports/<run_id>
python3 -m http.server 8080
# 访问 http://服务器IP:8080/report.html（需放行 8080）
```

### 1.6 最短路径（先跑通）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh)
cd /opt/lzy-bench
sudo ./benchmark.sh system
sudo ./benchmark.sh ipquality
sudo ./benchmark.sh           # 或 --run-lite 精简全量
ls reports/
```

### 1.7 注意事项

| 项 | 说明 |
|----|------|
| root | 压力测试 / 硬件信息 / 装依赖通常需要 |
| Docker/WP | 首次拉镜像慢；默认测完清理容器（`LZY_APP_CLEANUP=1`） |
| 保留 WP 栈 | `sudo LZY_APP_CLEANUP=0 ./benchmark.sh wordpress`（端口默认 18080） |
| 安全组 | 开 Platform 时放行 **8787**；仅本机可绑 `127.0.0.1` |
| 单模块失败 | 不会中断后续评测 |

---

## 二、Platform 快速启动

在已部署的仓库内：

```bash
cd /opt/lzy-bench/platform
chmod +x run.sh
./run.sh
```

- Dashboard：http://服务器IP:8787/  
- OpenAPI：http://服务器IP:8787/docs  

请确认云厂商安全组 / 防火墙放行 `8787`。

### Windows 本机开发启动（PowerShell）

```powershell
cd platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

---

## 三、导入 / 上报结果

### 3.1 本地写入 SQLite（无需 HTTP）

```bash
cd /opt/lzy-bench/platform
python scripts/ingest_local.py ../results/<run_id> \
  --label "HK-Lite" --provider "DemoCloud" --price 4.99
```

### 3.2 通过 API 上报

```bash
# 先启动 ./run.sh
python scripts/upload.py ../results/<run_id> --api http://127.0.0.1:8787 \
  --label "HK-Lite" --provider "DemoCloud" --region "HK" --price 4.99
```

### 3.3 从 CLI 仓库根目录上报

```bash
cd /opt/lzy-bench
./benchmark.sh upload                  # 最近一次
./benchmark.sh upload 20260801-120000  # 指定 run_id

# 带元数据
LZY_UPLOAD_LABEL="我的机器" \
LZY_UPLOAD_PROVIDER="厂商名" \
LZY_UPLOAD_REGION="HK" \
LZY_PRICE=4.99 \
./benchmark.sh upload
```

上报地址默认：`config/default.conf` 中的 `LZY_PLATFORM_API`（默认 `http://127.0.0.1:8787`）。  
远端看板示例：`LZY_PLATFORM_API=http://看板服务器IP:8787 ./benchmark.sh upload`。

---

## 四、API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/runs` | 结果列表 |
| GET | `/api/runs/{run_id}` | 详情（含完整 payload） |
| POST | `/api/runs` | 上报/更新 |
| DELETE | `/api/runs/{run_id}` | 删除 |
| GET | `/api/ranking?metric=overall` | 排行榜 |
| GET | `/api/compare?runs=id1,id2` | 多机对比 |

可选鉴权：设置环境变量 `LZY_PLATFORM_TOKEN`，则 `POST` / `DELETE` 需 Header：

```text
Authorization: Bearer <token>
```

更完整说明见仓库 [`docs/API.md`](../docs/API.md)。

---

## 五、数据与演示

默认 SQLite：`platform/data/lzy_bench.db`  
可用 `LZY_PLATFORM_DB` 覆盖路径。后续可替换为 PostgreSQL（保持 API 不变）。

```bash
cd /opt/lzy-bench/platform
python scripts/seed_demo.py
./run.sh
```

Dashboard 中可查看演示排行榜与多机对比。

---

## 六、推荐工作流（服务器）

1. `bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh)`  
2. `sudo ./benchmark.sh`（或精简模块 / `--run-lite`）  
3. `cd platform && ./run.sh` 启动看板（可选）  
4. `./benchmark.sh upload` 把结果写入看板  
5. 浏览器打开 `http://服务器IP:8787/` 查看排行 / 对比  

**理念**：Once Test, Multiple Output — 一次测试，多种输出。

- 仓库：[https://github.com/itbulu/LeBench](https://github.com/itbulu/LeBench)  
- 对照融合怪：[docs/COMPARISON_ECS.md](../docs/COMPARISON_ECS.md)
