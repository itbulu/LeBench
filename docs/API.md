# LZY Bench Platform API（Phase 4）

Base URL 默认：`http://127.0.0.1:8787`

## 鉴权（可选）

若服务端设置 `LZY_PLATFORM_TOKEN`：

```
Authorization: Bearer <token>
```

作用于：`POST /api/runs`、`DELETE /api/runs/{run_id}`。

## POST /api/runs

上报或更新一次评测。

```json
{
  "run_id": "20260801-120000",
  "label": "HK-Lite",
  "provider": "DemoCloud",
  "region": "HK",
  "price": 4.99,
  "payload": {
    "files": {
      "meta": {},
      "score": { "overall": 9.2, "scores": { "cpu": 9.0 } },
      "system": {},
      "route": {},
      "summary": {}
    }
  }
}
```

`payload.files.*` 对应 CLI `results/<run_id>/*.json`。

## GET /api/ranking

查询参数：

- `metric`: `overall` | `cpu_score` | `memory_score` | `disk_score` | `network_score` | `route_score` | `application_score`
- `limit`: 1–100

## GET /api/compare

查询参数：

- `runs`: 逗号分隔的 `run_id`，2–8 个

返回各机分项与相对第一台的 `deltas_vs_first`。

## 交互文档

启动服务后访问 `/docs`（Swagger UI）。
