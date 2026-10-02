# 本机监控与日志边界

`monitor.py` 只通过 Adapter 私有 Unix socket 的 GET 缓存健康接口读取指定 Profile，不发送 POST、不强制探测、不启动/停止/重建浏览器。每分钟由用户级 timer 执行，内存限额 64 MiB / CPU 10% / 16 tasks，单次 30 秒超时。普通服务输出只有成功/失败代码和活动告警数量。

已部署范围（2026-10-01）：Personal、Work 的只读健康与主机可用内存/磁盘。用户主动关闭的测试 Profile 不在期望运行清单里。外部邮件/聊天通知未配置，也不自动发送。

配置私有文件 `~/.config/browser-platform/monitor/config.json`，0600：

```json
{
  "socket": "/absolute/path/to/adapter.sock",
  "profiles": ["personal", "work"],
  "storage_path": "/absolute/path/to/storage",
  "state_directory": "/absolute/path/to/private-monitor-state",
  "memory_min_mib": 1024,
  "disk_min_mib": 4096,
  "failure_samples": 2,
  "recovery_samples": 2,
  "retention_days": 14,
  "max_events": 2000
}
```

状态目录必须由当前用户持有、0700，路径不得经过符号链接。程序、配置和事件都属于本机用户；不开放网络监听。部署程序至 `~/.local/lib/browser-platform/monitor.py`，两份 systemd 单元至 `~/.config/systemd/user/`，确认配置后执行：

```bash
systemctl --user daemon-reload
systemctl --user start browser-platform-monitor.service
systemctl --user enable --now browser-platform-monitor.timer
systemctl --user status browser-platform-monitor.timer
```

`~/.local/state/browser-platform-monitor/status.json` 原子保存最近采样、各告警计数/活动状态及事件历史。连续两次失败才写 `firing`，连续两次正常才写 `resolved`；持续故障不重复写事件。资源读数未知不解除已有低资源告警。停止且资源清零的 Profile 不告警；过期、不可达、未知或不健康的报告进入故障计数。只保存固定状态枚举，不复制报告消息、检查文本、Session/operation 标识、URL、Cookie 或凭据。

每次成功采样把事件截到最近 14 天及最多 2,000 条，整个原子状态文件上限 2 MiB。没有新增采样就不会后台删除旧事件；timer 的调度和状态文件时间应一起检查。损坏/过大状态拒绝覆盖，服务返回通用错误；保留原文件供排查，不自动重置告警。`monitor.lock` 防止重叠写入。连续服务失败或状态时间超过两个周期应检查本机 `systemctl --user status browser-platform-monitor.service`。监控器本身失败不伪造一份健康状态。

停用只需 `systemctl --user disable --now browser-platform-monitor.timer`；保留状态和业务数据。该操作不停止任何浏览器。

## 现有日志的保留策略

监控历史采用上述时间/条数/文件大小限制。Adapter 服务使用 journald；R6AQ 已部署[共享预算](journald-budget.md)：持久/运行 512/64 MiB，最多 30 天，未 vacuum 其他应用日志。

`compose.logging.yml` 是 SealSkin 与旧静态 Relay 的显式候选覆盖文件：json-file，每文件 10 MiB、最多 3 文件、压缩旧日志。独立 QA 用 16 KiB / 2 文件实际触发轮换并核对文件数和大小。应用日志策略需要重建相应容器；R6J1 已按用户授权完成生产维护，当前 11 容器实际生效，见[生产验收](../sealskin/r6j1-log-deployment-acceptance-2026-10-01.md)。不要直接删除 Docker 管理的活动日志。

动态 Worker/Guard/Relay 由控制器创建，不能从 Compose 覆盖推断它们已有限额。其新建默认限制现已由 bounded-logs.patch 实现并通过真实四类容器验证，三个现有 Home 已由 R6J1 正常停止、备份并重建；共享 journald 独立预算现由 R6AQ 完成。不要把监控事件保留当作所有应用日志都已配置。

验证：`python3 -m unittest discover -s infra/monitoring -v`；独立 Unix HTTP、故障/恢复、重启读回、保留、损坏状态、锁和符号链接拒绝均有覆盖。详见[验收](../sealskin/r6j-observability-acceptance-2026-10-01.md)。

2026-10-01 后续：日志专用候选已部署，[生产维护材料](production-log-maintenance.md)已更新。先前[组合候选](../sealskin/r6j-log-policy-acceptance-2026-10-01.md)包含未批准的 R7G，未用于本次生产。
