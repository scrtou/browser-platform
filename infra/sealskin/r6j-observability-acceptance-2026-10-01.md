# R6J · 只读监控与日志保留阶段验收

日期：2026-10-01 UTC。结论：只读监控器、告警/恢复状态机和私有事件保留已实现并启用；生产 Personal/Work 前后身份与配置保持。应用容器日志限额仍未应用，R6J 整体保持进行中。

## 已验证并生效

- 用户级 `browser-platform-monitor.timer` 已启用，每 60 秒执行；服务状态 success / exit 0，timer active / waiting，实际状态已持久化。
- 仅 GET 本机控制 socket 的缓存健康：Personal、Work 实际读数 healthy。没有强制探测、启动、停止或 Session 变更；用户主动关闭的测试 Profile 不纳入期望运行清单。
- 主机资源阈值：可用内存低于 1,024 MiB、磁盘低于 4,096 MiB。首次只读采样为 2,709 MiB / 9,695 MiB，数值随其他负载变化。
- 连续两次失败触发、两次成功恢复；故障持续不重复写事件。未知资源不解除已有资源告警。状态重读保留计数和活动告警。
- 输出只含 Profile ID、固定状态枚举、数值资源及告警状态；不复制健康消息、URL、Session、Cookie 或凭据。外部邮件/聊天通知未配置。
- 状态目录 0700、文件 0600；全局文件锁拒绝重叠运行。单文件原子提交，最多 2 MiB，历史按最近 14 天及最多 2,000 条裁剪；损坏或过大状态保留并失败退出。

7 项独立回归通过，覆盖真实 Unix HTTP 缓存接口、健康/过期/异常/停止、故障/恢复/重启续接、未知资源、敏感文本隔离、时间/条数保留、损坏状态、锁竞争和符号链接拒绝。真实服务也已通过一次以上定时采样。服务失败仅输出 `MONITOR_FAILED`；本地 systemd 与状态时间用于排查监控器自身失败，不能把旧状态当新鲜健康。

部署文件为 `~/.local/lib/browser-platform/monitor.py`、`~/.config/browser-platform/monitor/config.json` 及同名用户级 service/timer；持久状态为 `~/.local/state/browser-platform-monitor/status.json`。停用 timer 不影响浏览器，具体操作见[监控说明](../monitoring/README.md)。

## 日志候选与未完成范围

独立 QA 容器采用 json-file、16 KiB、最多 2 文件、压缩，写入约 250 KiB 固定无敏感数据后，实际日志文件数不超过 2、总大小小于 40 KiB；核对精确容器标签/ID 后清理。候选 Compose 覆盖提供 10 MiB × 3 文件配置。

生产 SealSkin 当前 json-file Config 为空，本轮没有重建容器或改 daemon 设置；候选覆盖不能证明它已生效。控制器创建的动态 Worker/Relay/Guard 日志默认值还需补齐实现/验证，再准备统一维护与存量迁移方案。主机共享 journald 策略未更改，未删除/vacuum 其他服务日志。本机可见 journal 约 75.6 MiB 的一次读数不等于已验证长期保留上限。

因此“全部生产日志已有限额”“所有运维计划完成”均不成立。下一步仍在 R6J 内完成动态容器日志策略及可审阅维护材料；R7G 供应方缺证、客户端暂缓和 R6I 未部署保持。

私有证据：`runtime/r6j-observability-20261001/` 的首次/定时采样、安装文件摘要、timer/service 状态、QA 日志轮换和 `final-status.json`。生产前后快照一致，唯一日志 QA 容器已删除；监控服务作为本轮交付持续运行。
