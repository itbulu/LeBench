# LZY Bench Platform（Phase 4）

Web Dashboard + REST API + SQLite，消费 CLI 产出的标准 JSON。

## 快速启动

```bash
cd platform
chmod +x run.sh
./run.sh
```

浏览器打开：http://127.0.0.1:8787/  
API 文档：http://127.0.0.1:8787/docs

Windows（PowerShell）：

```powershell
cd platform
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

## 导入 / 上报结果

本地直接写入 SQLite（无需启动 HTTP）：

```bash
python scripts/ingest_local.py ../results/<run_id> --label "HK-Lite" --provider "DemoCloud" --price 4.99
```

通过 API 上报：

```bash
# 先启动 ./run.sh
python scripts/upload.py ../results/<run_id> --api http://127.0.0.1:8787 \
  --label "HK-Lite" --provider "DemoCloud" --region "HK" --price 4.99
```

或从 CLI 仓库根目录：

```bash
sudo ./benchmark.sh upload                  # 上传最近一次
sudo ./benchmark.sh upload 20260801-120000  # 指定 run_id
```

## API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/runs` | 结果列表 |
| GET | `/api/runs/{run_id}` | 详情（含完整 payload） |
| POST | `/api/runs` | 上报/更新 |
| DELETE | `/api/runs/{run_id}` | 删除 |
| GET | `/api/ranking?metric=overall` | 排行榜 |
| GET | `/api/compare?runs=id1,id2` | 多机对比 |

可选鉴权：设置环境变量 `LZY_PLATFORM_TOKEN`，则 `POST`/`DELETE` 需 Header `Authorization: Bearer <token>`。

## 数据

默认 SQLite：`platform/data/lzy_bench.db`  
可用 `LZY_PLATFORM_DB` 覆盖路径。后续可替换为 PostgreSQL（保持 API 不变）。

## 演示数据

```bash
python scripts/seed_demo.py
./run.sh
```
