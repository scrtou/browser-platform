# 主机 journald 预算

此配置用于共享主机 journal：持久日志 512 MiB，尽量保留 2 GiB 磁盘空闲；内存日志 64 MiB，尽量保留 128 MiB；单文件分别 32/8 MiB，最长 1 天轮换，保留最多 30 天。大小/文件轮换与时间条件共同作用，日志可能早于 30 天淘汰，不能保证保存满 30 天。

journald 仅回收归档文件，活动文件和文件系统记账可能使观察值略超预算；这不是文件系统硬配额。KeepFree 不会替其他应用回收空间。此策略覆盖所有写入默认 journal namespace 的主机服务，Docker json-file 和平台业务操作日志分别管理。

以 root 核对完整用量和现行有效配置：

```bash
journalctl --disk-usage
systemd-analyze cat-config systemd/journald.conf
```

保存原配置后，将本目录 `journald-budget.conf` 以 root:root/0644 安装为 `/etc/systemd/journald.conf.d/60-browser-platform-budget.conf`，核对没有后续同名配置键覆盖，再执行：

```bash
systemctl restart systemd-journald.service
systemctl is-active systemd-journald.service
systemd-analyze cat-config systemd/journald.conf
journalctl -u systemd-journald.service --since '5 minutes ago'
journalctl --disk-usage
```

使用自有标记写入/读回确认日志接收；检查启动记录的预算及配置解析错误。无需重启 Adapter、Docker 或浏览器；本次不执行 vacuum，不直接删除日志文件。journald 的正常保留机制会在后续轮换时淘汰符合条件的归档。

回退时先核对该 drop-in 的摘要仍等于安装版本，再移除此文件（若有原文件则只恢复原文件），重启 journald 并核对有效配置/日志接收。保留其他 drop-in、主机日志和所有业务操作 journal；不要用旧 `/var/log/journal` 快照覆盖当前日志。

2026-10-02 实际部署及证据见 [R6AQ 验收](../sealskin/r6aq-journald-acceptance-2026-10-02.md)。长期 30 天淘汰属于持续运行观察，不以短时检查声称已等待验证。
