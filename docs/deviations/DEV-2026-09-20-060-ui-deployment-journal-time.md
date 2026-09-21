# DEV-060 · UI 发布日志时间格式

状态：已解决。日期：2026-09-20。关联：[R6H](../work-items/R6H-2026-09-20-management-ui-deployment.md)。

预期：第二版 Tab UI 原子替换后，健康、权限门槛、运行绑定和日志证据检查完成，再记录发布成功；失败恢复旧二进制，不恢复配置或持久状态。

事实：候选 `fe4e13c4…` 首轮 health/ready、登录门槛、进程摘要、文件与完整 Session/容器/网络绑定检查均已通过，但发布脚本给 `journalctl --since` 传入带小数秒和时区偏移的 ISO 时间，本机拒绝解析。脚本因此按失败策略恢复 `c4f62410…` 并重启 Adapter；旧版本恢复 active/ready。没有浏览器生命周期操作，也未修改配置、账号、Profile 或 Home。

处理：修复发布器日志查询时间为 systemd 接受的 UTC 格式，保留首次失败及回退记录，在独立 attempt-2 中重新执行全部部署检查。UI 与功能验收条件不变，不能把首轮写成已发布。

私有证据：`infra/sealskin/runtime/r6h-management-tabs-2026-09-20/deployment-failure.json`、pre/post 快照及精确二进制备份；重试材料独立保存在 `attempt-2/`。

复验：17:26 UTC attempt-2 已安装 `fe4e13c4…`，日志采集成功且无 warn/error，health/ready、登录门槛、实际进程摘要、配置/账号/Profile/unit 摘要、完整 inspect（含 Session）、Home/应用/策略绑定、容器 ID/启动时间及网络 ID 全部通过；旧 `c4f62410…` 精确回退材料保留。该结论不替代目标 Mac 视觉验收。
