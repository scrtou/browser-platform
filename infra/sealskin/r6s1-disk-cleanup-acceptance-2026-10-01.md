# R6S1 磁盘缓存清理验收 · 2026-10-01

结果：用户授权的磁盘维护完成。[工作项](../../docs/work-items/R6S1-2026-10-01-disk-cleanup.md)关联 R6S 前置资源维护，不代表 R6S 功能验收或发布完成。

## 清理范围与空间

仅使用 Docker BuildKit 的构建缓存清理接口。先按超过 24 小时、超过 1 小时筛选，再包含闲置内部缓存；仍未达到余量目标时取消时间筛选，以 `--all --force --reserved-space 1GB` 回收其余闲置缓存。这里的 `--all` 作用于 **buildx prune 构建缓存**，没有执行 image/system/volume prune。BuildKit 管理占用保护，没有停止正在运行的构建或浏览器。

| 操作 | 工具报告回收量 |
| --- | ---: |
| `docker buildx prune --builder default --filter until=24h --force` | 1.236 GB |
| `docker buildx prune --builder default --filter until=1h --force` | 104.5 MB |
| `docker buildx prune --builder default --all --filter until=1h --force` | 1.043 GB |
| `docker buildx prune --builder default --all --force --reserved-space 1GB` | 6.444 GB |
| 合计（Docker 十进制口径，近似值） | 8.83 GB |

首次检查可用 547 MiB；执行前快照为 312 MiB，执行后核对快照为 6,862 MiB（约 6.70 GiB），使用率由 100% 降为 94%。实际净增加约 6.40 GiB。期间其他测试仍在写入主机，不能把工具回收量等同于 `df` 净增加，也不承诺后续可用量不变。

最终 `docker system df` 的 Build Cache 为 5.289 GB，其中可回收 726.2 MB；剩余含镜像共享内容，不能把全部显示大小当作可释放空间。已达到可用至少 5 GiB 的维护目标，未进一步清理 Go 编译缓存、数据卷或日志。

## 保护范围复核

- 前后 15 个既有容器的 ID、镜像、状态、启动时间、重启次数、挂载和网络连接精确一致，包含生产浏览器、R6S QA 和其他构建容器。没有服务重启或浏览器退出。
- 36 个 Docker 镜像 ID 及标签、14 个网络 ID 前后一致。原有 975 个数据卷均保留；期间另一个项目的 PostgreSQL 临时测试新增 1 个匿名卷，已由 Docker 事件核对来源，未清理该卷。
- 20 份受保护文件（生产配置、账号/密钥文件、Profile/Session 状态、模板/网络目录及生产作业文件）的内容 SHA-256 与权限一致。公开记录不披露敏感内容或摘要。
- R6S 证据根的 6,496 个路径前后相同；未清理 Home、产物、来源缓存、失败日志、发布或备份材料。此处核对路径保持，不宣称逐字节冻结运行中的浏览器 Home。
- Adapter 和只读监控 timer 均为 active。后续自动采样可用 6,797 MiB，`disk_low` 已恢复为 failed=false / active=false。未重新运行完整网络/客户端验收，也未将既有 Personal 上游 unknown 改为 healthy。

私有证据：`infra/sealskin/runtime/r6s1-disk-cleanup-20261001/`，包含前后快照、四次 prune 日志、缓存清单、保护范围比较及同期 Docker 事件。该目录被 Git 忽略，权限 0700。

经核对未发现本次维护引入的设计偏差。R6S 剩余组合验收与发布、R7G、异机灾备及全计划审计保持原状态，本次不自动继续功能实施。
