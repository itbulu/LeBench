# LZY Bench 评分规则（Phase 2–3）

## 原则

- 禁止人工评分
- 流程：原始指标 → 相对基准线性标准化（0–10）→ 按权重加权 → 综合分
- 某维度无数据时记为 N/A，**丢弃该权重并对其余维度归一**

## 默认权重（合计 100）

| 项目 | 权重 | 来源 |
|------|------|------|
| CPU | 20% | sysbench single/multi eps |
| Memory | 10% | sysbench memory MiB/s |
| Disk | 20% | fio 顺序带宽 + 随机 IOPS |
| Network | 20% | Speedtest 上下行 + Ping |
| Route | 10% | 线路启发式分数 |
| Application | 10% | Docker 启动耗时 + WordPress 部署/TTFB |
| Price | 10% | 环境变量 `LZY_PRICE`（月费 USD）；未设则 N/A |

## 应用维度（Phase 3）

越低越好，相对基准反比打分：

| 指标 | 配置项 | 默认参考 (ms) |
|------|--------|----------------|
| Nginx 启动（含拉取） | `LZY_SCORE_REF_DOCKER_NGINX_MS` | 15000 |
| Redis 启动 | `LZY_SCORE_REF_DOCKER_REDIS_MS` | 10000 |
| MySQL 启动 | `LZY_SCORE_REF_DOCKER_MYSQL_MS` | 45000 |
| WP 部署就绪 | `LZY_SCORE_REF_WP_DEPLOY_MS` | 90000 |
| WP TTFB | `LZY_SCORE_REF_TTFB` | 200 |
| WP 整页 | `LZY_SCORE_REF_WP_TOTAL_MS` | 500 |

可用子项取平均作为 `scores.application`。

## 标准化基准（达到即约 10 分，可在 `config/default.conf` 调整）

| 指标 | 配置项 | 默认 |
|------|--------|------|
| CPU 多核 eps | `LZY_SCORE_REF_CPU_MULTI` | 8000 |
| CPU 单核 eps | `LZY_SCORE_REF_CPU_SINGLE` | 2000 |
| 内存 MiB/s | `LZY_SCORE_REF_MEM_MIB` | 8000 |
| 磁盘顺序 MiB/s | `LZY_SCORE_REF_DISK_SEQ` | 500 |
| 磁盘随机 IOPS | `LZY_SCORE_REF_DISK_IOPS` | 20000 |
| 下行 Mbps | `LZY_SCORE_REF_NET_DL` | 1000 |
| 上行 Mbps | `LZY_SCORE_REF_NET_UL` | 500 |
| Ping ms（越低越好） | `LZY_SCORE_REF_NET_PING` | 20 |
| 月费 USD（越低越好） | `LZY_SCORE_REF_PRICE` | 5 |

公式（越高越好）：`min(10, value / ref * 10)`  
公式（越低越好）：`min(10, ref / value * 10)`

## 线路分（Route）

| 推断 | 分数 |
|------|------|
| CN2 | 9.5 |
| CU 9929 | 9.0 |
| CMI | 8.5 |
| 优质 IP 段提示 | 7.5–8.0 |
| 普通骨干（163/169 等） | 6.0 |
| 未知 | 5.0 |

基于 ASN / traceroute 启发式，**不能**等价于完整 BGP 质量保证。

## 输出

`results/<run_id>/score.json`，示例：

```json
{
  "overall": 9.2,
  "scores": { "cpu": 9.3, "disk": 9.1, "network": 9.5 }
}
```

实现：[`scoring/score.sh`](score.sh)
