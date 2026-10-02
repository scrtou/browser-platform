# R6AQ · 主机 journald 预算验收

2026-10-02 UTC：已部署并通过即时运行验收。root 完整 journal 用量为 194.0 MiB，配置前后相同。原用户级 77.1 MiB 仅代表可见子集。

独立 drop-in `/etc/systemd/journald.conf.d/60-browser-platform-budget.conf`，root:root/0644，SHA256 `a1a90927f035a75fa6d219e6ec2ed1f3b012fa662b2c7970f30316329b18ea0b`。持久 512 MiB / 保留空闲 2 GiB / 单文件 32 MiB；运行 64 MiB / 保留空闲 128 MiB / 单文件 8 MiB；最长 1 天轮换，最多保留 30 天。

有效合并配置逐键匹配；仅重启 systemd-journald，active 且启动记录明确 `max 512.0M`，没有未知配置/解析错误。自有随机标记写入、sync 与 root 读回通过。安装前后生产保护快照一致，浏览器/Session/目录/凭据/控制器/Adapter/runner 均保持。

配置前目标文件不存在，独立目录中完成按摘要删除/恢复检查；真实主机未执行回退。回退只移除本次匹配摘要的 drop-in，再重启 journald 并复核，不恢复旧日志。实际安装使用无网络、只读容器与限定 systemd 目录挂载；连接主机服务管理器仅增加 host PID/SYS_CHROOT，未使用 privileged。首轮只读检查因缺 host PID 未连接成功，未写入配置，失败日志保留。

本次没有 vacuum、手工删除日志、制造海量日志或重启主机/Docker/浏览器。journald 只回收归档文件，因此预算不是文件系统硬配额，也不保证日志必定保留满 30 天；30 天自然到期观察尚未经过，不能写成长期实测通过。Docker json-file、监控事件及业务操作 journal 继续按各自规则管理。

[配置/操作与限制](../monitoring/journald-budget.md) · [工作项](../../docs/work-items/R6AQ-2026-10-02-journald-budget.md)。私有证据：`runtime/r6aq-journald-20261002/`。
