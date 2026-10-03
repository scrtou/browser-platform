# DEV-153 · 全新系统用户的控制器 UID 绑定

状态：已解决（R6AX范围）。关联 [R6AX](../work-items/R6AX-2026-10-03-v1-release.md)。

首次独立安装使用新系统 UID 993，Docker LinuxServer 初始化正确应用 `PUID`/`PGID`，tmpfs 目录权限、挂载和主机路径映射正确，但 API 在 `session_runtime.runtime_root()` 拒绝 `SESSION_AUTH_TMPFS_BIND_REQUIRED`，管理员引导未生成，安装于 180 秒超时。原失败根 `/srv/bp-r6ax-fresh`、私有日志与诊断保留。

源码表明 Python 控制设置只读取 `SEALSKIN_PUID`/`SEALSKIN_PGID`，未配置时固定默认 1000；进程实际 UID 993 与 `settings.puid=1000` 不一致。旧生产恰好为 UID 1000，没有覆盖全新系统用户情况。安装器必须同时设置容器初始化和控制器配置的两组 UID/GID，而不能依赖默认数值或弱化凭据所属检查。

选择修复安装配置，保持控制器镜像及权限校验不变。补充生成配置关联检查，用新空目录、新用户再次完整安装；首次失败实例先保存证据并停止，仅释放该实例端口。新安装、实际显示及机器重启验证通过后再关闭偏差。该问题不影响已验收的 R6AW 内置包内容。

最终核对：R6AX最终包新安装、相同最终程序三引擎输入/关闭、服务与主机重启及保护生产部署已通过；本记录原失败与处理过程保留。具体适用证据见[R6AX最终验收](../../infra/sealskin/r6ax-v1-install-acceptance-2026-10-03.md)。
