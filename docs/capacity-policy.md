# 浏览器容量策略

[工作项](work-items/R6AI-2026-10-02-capacity-release.md) · [验收](../infra/sealskin/r6ai-capacity-release-acceptance-2026-10-02.md)

`limits.auto=true` 表示门槛由机器资源推导，迁移后无需沿用旧机器数量。Adapter和Docker Workers必须位于同一Linux主机；读取本机CPU、`/proc/meminfo`和`storage_path`所在文件系统。远程Docker或只有Adapter在受限容器内时应按实际Worker主机手动配置，不能把Adapter的容器配额当成整个浏览器平台的额度。

| 项目 | 默认推导 | 正值覆盖字段 |
| --- | --- | --- |
| 每浏览器内存预算 | 1152MiB（1GiB Worker+128MiB配套） | `memory_per_profile_mib` |
| 内存保留 | 总内存20%，至少1024MiB | `memory_reserve_mib` |
| 活动浏览器 | CPU数与⌊(总内存−保留)/每浏览器预算⌋两者较小值，最少0 | `max_active_profiles` |
| 并发启动 | CPU数/4与活动上限/4向下取整的较小值，最少1 | `max_concurrent_launches` |
| 磁盘最低空闲 | 文件系统总量2%，下限4096MiB、上限16384MiB | `min_free_disk_mib` |

自动模式省略或0表示推导；`auto=false`保留旧语义，三项0表示不限，内存预算字段只用于自动模式。示例配置：

```json
{"limits":{"auto":true,"storage_path":"storage"}}
```

4核/5924MiB/99GiB机器计算为4个活动、1个并发、4096MiB磁盘保留；16核/32GiB/1TiB机器为16个活动、4个并发、16384MiB磁盘保留。总预算容不下一个浏览器时计算为0，拒绝新启动，不视为无限制。正值覆盖数量不会关闭自动模式的实时内存保护。

每次新启动在全局短准入锁内重新读取内存和磁盘。`MemAvailable−内存保留`必须足够覆盖所有进行中的启动及本次新启动的预算，防止并发请求重复使用尚未实际分配的内存；测量失败保守返回`CAPACITY_RESOURCES_UNKNOWN`。内存、活动数、并发数、磁盘拒绝分别为`CAPACITY_MEMORY / CAPACITY_ACTIVE_PROFILES / CAPACITY_CONCURRENT_LAUNCHES / CAPACITY_DISK`，入口仍使用现有503提示。测量和拒绝不创建Home、控制器资源或journal占用。停止/失败外的绑定继续计入活动数量。

已有会话先复用/对账，容量下降或测量失败不停止或驱逐浏览器。进行中启动结束后释放临时内存名额；预算可能与已实际分配的部分短时重复计入，取保守值。此处只决定是否接收新启动，不限制已运行页面未来的内存增长，也不替代Worker资源限制。默认预算沿用R6I限定负载经验，需要按重负载网页提高预算或人工下调数量。

只读检查（不连接浏览器、不获取Session URL、不持状态写锁）：

```bash
~/.local/lib/browser-platform/profile-adapter -config infra/sealskin/adapter-config.json -inspect-capacity
```

输出配置在本机此刻的计算结果、内存/磁盘采样值，不包含凭据或会话；不是正在进行的启动计数或“还可开启数量”。配置修改后重启Adapter使服务读取；迁移应同时更新storage路径。监控器现有告警阈值是独立运维配置，不随此项自动修改。

实现入口：config.Load/Validate → `Limits.InspectCapacity` → Ensure已有会话处理 → admitLaunch锁内checkCapacity/prepareLaunch/启动计数 → 锁外LaunchURL → releaseLaunchSlot。恢复与独占规则沿用生命周期契约。

缓存与历史材料的 [保留政策](disk-retention.md) 独立于容量门槛；R6AN 已恢复至少当前最低保留加 1024 MiB 的余量，不下调门槛来掩盖空间不足。
