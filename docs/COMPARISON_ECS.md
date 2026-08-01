# 对照：spiritLHLS/ecs（融合怪）与 LZY Bench 优化路线

参考项目：[spiritLHLS/ecs](https://github.com/spiritLHLS/ecs)  
本仓库：[itbulu/LeBench](https://github.com/itbulu/LeBench)

## 一、融合怪的优点（值得学习）

| 优点 | 说明 | 对用户的价值 |
|------|------|----------------|
| **一键上手** | `curl \| bash` / 短域名即可跑 | 降低评测门槛 |
| **覆盖面广** | 基础信息、CPU/内存/磁盘、测速、回程、流媒体、IP 质量等 | 「一次测全」心智 |
| **三网体验成熟** | 回程路由、三网测速、节点自更新 | 国内选型核心诉求 |
| **解锁检测较可靠** | 专用工具/二进制，误判相对少 | 比纯 curl 更可信 |
| **IP 质量** | 多库查询、黑名单、邮件端口等 | 代理/机房/邮局风险一眼可见 |
| **带宽类型** | 商宽 / 家宽 / 数据中心等推断 | 解释延迟与合规差异 |
| **分享友好** | 文本结果、分享链接、screen/tmux 友好 | 博客/群测传播快 |
| **容错与 CDN** | 国内加速、失败降级、并行优化 | 垃圾机也能跑完 |
| **参数化** | `-m` 菜单/非交互、指定 GB/fio 等 | 适合自动化 |

> 注：融合怪官方更推荐无环境依赖的 Go 版：[oneclickvirt/ecs](https://github.com/oneclickvirt/ecs)。Shell 版以维护为主。

## 二、LZY Bench 已有优势（应保持）

| 优势 | 说明 |
|------|------|
| **标准化 JSON** | 模块结果结构统一，便于 API / 数据库 |
| **自动评分** | 基准标准化 + 权重，禁止纯人工分 |
| **真应用场景** | Docker / WordPress 部署与 TTFB |
| **多种输出** | JSON + Markdown + HTML |
| **Platform** | Dashboard、排行榜、多机对比、upload |
| **模块失败不中断** | 单测失败继续后续项 |
| **可配置** | `config/default.conf` / `local.conf` |

定位差异：

```text
融合怪：覆盖广、上手快、分享方便（测评脚本合集体验）
LZY Bench：可复现、可评分、可上平台 + 真实应用（标准化评测体系）
```

## 三、我们可优化的清单（按优先级）

### P0（已完成）

| 项 | 优化动作 | 状态 |
|----|----------|------|
| 一键运行 | `install-run.sh` | 完成 |
| IP 质量 | 模块 `ipquality` | 完成 |
| 带宽类型 | `route.json` | 完成 |
| 解锁增强 | YouTube / X / ChatGPT-Trace | 完成 |

### P1（已完成）

| 项 | 优化动作 | 状态 |
|----|----------|------|
| 三网测速 | `network.china_download` curl 下载测速（可配 URL） | 完成 |
| 纯文本摘要 | `summary.txt`（results + reports） | 完成 |
| dd 快测 | `disk.dd` 与 fio 并存 | 完成 |

### P2（后续）

| 项 | 说明 |
|----|------|
| Geekbench CLI 参数 | 显式 `-ctype` 类开关文档化 |
| nexttrace 深度解析 | 更完整 ASN 路径 |
| 巨型交互菜单 | 不建议照搬；保持子命令 |
| 嵌入融合怪脚本 | 不建议；保持自研模块 |

## 四、模块映射（ecs → LZY）

| 融合怪能力 | LZY 模块 / 产出 |
|------------|-----------------|
| 系统信息 | `system` → `system.json` |
| CPU / 内存 / 磁盘 | `cpu` / `memory` / `disk` |
| 测速 | `network`（持续增强） |
| 回程 / 线路 | `route`（+ 带宽类型） |
| 流媒体解锁 | `streaming` |
| IP 质量 | `ipquality`（新增） |
| 应用体验 | `docker` / `wordpress`（融合怪无） |
| 评分 / 排行 | `scoring` + `platform`（融合怪无） |

## 五、一键安装（对齐融合怪体验）

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh)
```

或：

```bash
curl -fsSL https://raw.githubusercontent.com/itbulu/LeBench/main/install-run.sh -o install-run.sh
sudo bash install-run.sh
```

## 六、原则

1. **借鉴指标与体验，不整包合并脚本**  
2. **所有新能力必须进 JSON，并可进入评分 / 报告 / Platform**  
3. **保持失败隔离与清理策略**  
4. **差异化打「应用 + 评分 + 看板」**
