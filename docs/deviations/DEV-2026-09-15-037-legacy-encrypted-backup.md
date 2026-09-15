# DEV-037 · 旧生产部署缺少可用的加密备份入口

状态：已解决（工具与只读准备；真实维护仍归 R2）。工作项：[R2A](../work-items/R2A-2026-09-15-legacy-backup-preparation.md)，父项 [R2](../work-items/R2-2026-09-13-boot-recovery.md)。

预期：R2 的真实 Home 维护必须先具备可恢复的加密备份，包含实际运行镜像、身份、状态和凭据；没有冻结环境验收的旧 Worker 必须记录真实范围。

2026-09-15 代码与部署事实：`secure-backup.py collect_sources()` 无条件要求 FileSecretStore、32 字节主密钥和完整成功产物，归档验证/恢复也强制 Store 布局。生产没有 `profile-secret-store.json` / `proxy-secret-store/`，仍是旧凭据文件；当前应用定义又不代表仍运行的旧 Worker。管理员说明末尾仍推荐明文 `backup-home.py` 或仅 `control-state`，与现行 S05 加密/完整恢复要求冲突。此前 R5B/R5D 的加密备份 PASS 只对其 Store/QA 格式成立，不能扩展到旧生产部署。

处理选择：修复工具并更新说明。增加明确的旧部署快照/加密归档契约，保留实际运行身份，复用受验证的流式 age 和 tmpfs 认证/安全恢复路径。旧模式拒绝 Store、密封状态或入口账号，不能降低现有新格式的恢复/撤销门槛；不制造虚假的 Store、产物或成功报告。恢复到新私有目录后保持离线，原 journal 和生产 Home 不覆盖。

验证计划：真实 age 的无 Store 往返、当前/下次镜像区别、运行中和输入漂移拒绝、错误密文/identity/成员与已有目标拒绝、模式降级拒绝以及原 37 项回归。维护输入仅只读生成；真实 Home 停机恢复、退出登录、主机重启与目标客户端仍待其原计划条件。

2026-09-15 首轮生产只读快照被 `BACKUP_LEGACY_RUNNING_BINDING_REQUIRED` 拒绝；四容器和五份配置/绑定未变。实际旧 journal 尚无后来新增的 `home_name` / `application_id`，而新测试夹具包含这两项。Adapter 的既有 `checkDefinition` 对缺失旧字段继续通过 Session、bootstrap 和实际 Home 清单校验归属。修复快照时沿用此真实契约：必须由运行中 Adapter 确认唯一 running Session/Worker、与 journal 同 Session，再核对精确 Home 挂载；非空身份字段仍须匹配。快照保留字段是否存在，停止后要求同一 operation 及相同字段形态，不能为通过检查修改生产 journal。补充真实旧字段缺失和身份冲突测试，保留 `production-snapshots-1` 失败证据。

第二轮快照成功，Personal 实际镜像与当前定义不同，Work 相同；新增与原有共 76 项测试通过。后续仅读取文件属性发现，生产 Adapter 的服务公钥为 `0644`（私钥 `0600`、父目录 `0700`），而共享收集器误把公钥也按私钥权限拒绝。公钥没有保密要求；修复为要求受信任 UID、普通单链接文件及无组/其他写权限，私钥继续要求 `0600`，不修改生产文件权限。补充此真实布局及可写公钥拒绝检查。

最终结果：80 项真实 age 检查全部通过（含 CLI/Unix socket），最终代码的两个生产快照与 13 组身份/控制来源前置检查通过；四容器及五份配置/绑定保持。QA 暂存已清理，管理员说明移除明文正式备份建议，组件、设计/规格、运维及计划已同步并通过静态检查，见 [R2A 验收](../../infra/sealskin/legacy-backup-acceptance-2026-09-15.md)。旧恢复提示不是旧控制器执行的启动锁，真实 Home/浏览器恢复和维护条件没有改写为完成。
