# DEV-031 · Session 状态持久化包含明文访问材料

状态：已解决（代码与隔离 QA，未部署生产）。工作项：[R5D](../work-items/R5D-2026-09-14-entry-authentication.md)。

预期：Session 能力与显示凭据不得进入普通状态/日志；必要解密材料必须在专用私有路径并纳入加密备份，丢失或损坏时拒绝恢复且保留 Home/占用。

源码事实：SealSkin launch 将 `access_token`、显示 `password/custom_user` 等加入 `state.sessions`；`config_store.save_sessions()` 深复制后直接写 YAML。加载失败又捕获异常而继续空状态。R5B 只证明其上游 Secret Store 范围，未解决这条 Session 持久化路径。

处理选择：修复实现。以独立 0600 密钥、私有目录和 AES-256-GCM 密封持久化 Session 快照，读取完整认证成功后才更新内存；旧明文状态按明确兼容迁移路径原子密封，不能丢失现存 Session。缺失/错误密钥、损坏密文或写入失败必须显式失败，不能回退到空记录。密钥随已加密备份恢复，不宣称删除明文临时文件等于物理擦除。

须验证：正常/旧格式迁移/新环境恢复、逐点写入失败、错误密钥与损坏文件、普通状态扫描，以及已有生命周期和网络控制测试。证据留在本项私有目录，生产未部署。

实施进展：Session 状态和原停止/网络控制的 124 项测试通过（`session-state-after-1/`），覆盖迁移写入前后中断重试、迁移后拒绝明文降级、缺库/错误或缺失密钥、路径/权限异常、原子写故障和新目录恢复。迁移使用专用目录内的临时摘要记录；认证密封完成后删除，保留既有停止意图。AES-GCM 不提供针对同时替换整个密钥/状态目录的外部回滚计数保证。

已补加密备份的 Session 密钥配对校验和入口账号/CA 收集；旧明文 control-state 工具遇到 Session 库或入口账号配置时拒绝创建归档。含入口账号的恢复需使用当前受信任账号表完成离线启用，避免从旧备份重新启用已禁用账号。

2026-09-15 最终验证：C3 镜像 534 项控制检查通过；`wrapper-tests-final-2/` 使用固定 age v1.2.1 的 37 项备份检查通过，首轮缺工具路径的 skip 保留。`client-qa-13/` 的真实控制器 restart 与 Worker 原代次 resume 均保持 Session、Home 和 Cookie/localStorage/IndexedDB；`runtime-security-3/` 核对密文、专属密钥/显示材料和普通状态扫描通过。回退安装器拒绝直接移除仍需解密的模块，维护/恢复说明已更新。真实生产 Home 和整目录回滚检测不在本次通过范围，见 [最终验收](../../infra/sealskin/entry-authentication-acceptance-2026-09-15.md)。
