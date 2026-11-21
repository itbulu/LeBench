# LeBench 模块覆盖表

状态：`implemented` / `tested` / `blocked` / `not_supported`

| 模块 | 阶段 | 状态 | 说明 |
|------|------|------|------|
| system | S0 | implemented / tested | CPU/内存/存储/虚拟化/OS/BBR/IP |
| cpu | S1 | implemented | Sysbench；可选 `--enable-geekbench` |
| memory | S1 | implemented | sysbench memory 读写吞吐 |
| disk_dd | S1 | implemented | 临时文件 DD；禁块设备 |
| disk_fio | S1 | implemented | 4K 随机 + 1M 顺序 |
| network | S2 | implemented | 需配置节点；无节点 `not_run` |
| ping | S2 | implemented | ICMP/TCP 出站；需目标配置 |
| routes | S3 | implemented | 本机回程；去程 `not_run` |
| ip_quality | S3 | implemented | 可选 API；密钥不入库 |
| compatibility | S3 | implemented | 需 `--enable-compatibility` 或 deep |
| stability | S3 | implemented | 有界采样，非 SLA |
| physical | S4 | implemented | 只读；权限不足降级 |
| gpu | S4 | implemented | 探测；无卡 `not_applicable` |
| app_perf | S4 | implemented / tested | 需 `--enable-app-perf` |
| cloud_delivery | S4 | implemented / tested | 功能项记录 `not_run` 原因 |
| site_schema_v1 | S5 | blocked | 待网站 Schema 批准 |

Linux 实机完整数值验证待用户环境验收。
