# 旧部署加密备份与维护准备验收 — 2026-09-15

[工作项 R2A](../../docs/work-items/R2A-2026-09-15-legacy-backup-preparation.md) · [操作契约](lifecycle/secret-store.md#旧部署的加密备份) · [管理员准备](ADMIN-linger-and-boot.md) · [DEV-037](../../docs/deviations/DEV-2026-09-15-037-legacy-encrypted-backup.md)

结论：旧部署加密工具、80 项备份检查、生产只读快照、QA 清理与文档静态核对通过，R2A 已收尾。**没有停止生产、读取或复制真实 Home 内容，也没有执行真实浏览器恢复或主机重启。** R2 的维护验收条件保持。

## 版本与方法

- Debian 12、Python 3.11、age v1.2.1；原生产生命周期版本保持。
- `secure-backup.py` SHA-256：`cbbbea52fc6b76f4f9bffa5c3bea58b84d8e01d917963748a9f0f3cfdb7de38c`。
- 新测试 `test_secure_backup_legacy.py` SHA-256：`ee0599ff3ca46cb74f8a2c04af195880a9269e0ade1a346ba67da3f2370fc504`。
- 私有证据根：`infra/sealskin/runtime/r2a-legacy-backup-2026-09-15/`。未改变 C3 控制 payload、Adapter/Relay/Worker 代码或生产配置。

测试使用独立临时文件、真实 age 加密/认证及 tmpfs；Docker/API 清单使用夹具。CLI 场景经过真实 Python 子进程与 Unix socket，只有清单内容由测试服务提供。数据及身份材料的比较证明归档字节保持，不代表真实服务认证或浏览器已读取恢复数据。

## 完成条件核对

| 要求 | 结果与边界 |
| --- | --- |
| 旧部署可加密往返 | 显式 `snapshot-legacy` / `create-legacy` 采用独立格式，恢复样本 Home、旧凭据、Adapter/服务身份字节及实际镜像引用；链接/硬链接规则保持。原 Store `create` 不自动降级 |
| 实际旧镜像与配置区别 | 快照分别记录实际 Worker/控制器身份和应用中的下次镜像。真实 Personal 不同、Work 相同；没有把当前定义当作旧环境验收 |
| 旧 journal 兼容 | 缺失 Home/App 可选字段时由 Adapter 的 Session/归属检查及精确 Home 挂载确认；快照和停止后保留字段形态。非空冲突、代次变化、配置/应用/策略漂移拒绝 |
| 运行中与竞态 | 运行中归档拒绝；重复 Worker、容器启动时间变化、清单不一致、加密期间出现 Store 均拒绝。失败不发布密文目标 |
| 格式不能降级 | Store 目录/配置、Session 密钥/密封库、显示材料版本、入口账号和 `secret://` 引用不能走旧格式；原格式的撤销/账号恢复测试保持通过 |
| 不安全恢复拒绝 | 错误 identity、损坏/截断密文、路径/链接/摘要/成员/格式/journal 异常均在创建恢复目录前拒绝；现有归档和恢复目录保留 |
| 公钥与私钥 | 私钥继续要求私有权限；服务公钥允许受信任 `0644` 文件，但可被其他用户写入则拒绝。生产文件权限未修改 |
| 恢复边界 | 旧格式返回 `offline_only=true`、`ready_to_activate=false`，写离线提示并拒绝 `activate`。提示不是旧控制器的启动锁，不可直接挂载恢复包启动服务 |
| 回归与 CLI | `backup-tests-4/`：原 37 项 + 新 43 项 = **80 passed，0 skipped**。包含真实 CLI 的快照、运行中拒绝、加密、验证和离线恢复；stdout/stderr 无样本秘密 |
| 生产只读 | `production-snapshots-3/` 两个快照通过，未读 Home 内容。四个生产容器的 ID/image/StartedAt/PID、五份配置/绑定摘要前后相同，并与 R5D 收尾基线一致 |
| 维护材料 | `material-preflight-1/` 确认 13 组身份/控制来源可收集，没有收集 Home 或复制密钥。`host-preflight-1.json`：Adapter active/enabled，Caddy active，Linger=no，sudo 仍需密码；可用磁盘 60.85 GiB、tmpfs 2.89 GiB，仅为当次采样 |

快照不包含秘密值，仅保存允许的运行引用与摘要；不是 Home 备份。归档不包含镜像层、热安装 payload 或客户端文件，维护前必须保留匹配发布材料。一个包只包含指定 Home，控制 metadata 可能引用其他 Profile，恢复不得自动启动这些绑定。旧环境缺少冻结产物时只记 `observed-legacy-runtime`，没有降低 E/S05 的正式验收条件。

## 失败历史与修复

- `backup-tests-1/`：37 passed、31 个准备错误；新夹具遗漏 Adapter 锁文件，未运行到旧格式场景。补齐夹具后 `backup-tests-2/` 为 68 passed。
- `production-snapshots-1/`：两个快照被拒绝；真实旧 journal 没有新加的可选 Home/App 字段。未改生产状态，按 Adapter 既有归属规则修复工具并增加冲突/形态检查，`backup-tests-3/` 为 76 passed，`production-snapshots-2/` 通过。
- 只读文件检查发现生产服务公钥为 0644，共享收集器曾将其误作私钥权限。分开完整性与保密检查，保留可写公钥/可读私钥拒绝；补 CLI 后最终 80 项通过。最终代码的生产快照记录在 `production-snapshots-3/`，原失败证据保留。

## 收尾与未完成范围

`cleanup-1/` 确认早两轮共 136 个 pytest 夹具目录已删除，后两轮私有夹具和所有本项 tmpfs 暂存已清理；没有创建测试容器。失败日志、脱敏结果和只读快照保留在私有证据目录。生产四容器与五份配置/绑定再次保持。

`final-static-1/` 已通过公开文件/文档链接与锚点、21 个 JSON、4 个相关 Python 语法和 47 个已知秘密变体检查；两个生产快照也参与扫描，无秘密命中。普通与 staged diff、展开源码的 whitespace 检查通过，Git index 未变。完整 `git diff --check` 的 exit 2 仍仅来自旧 patch 的 65 个必要空白上下文行，逐行确认；patch 摘要与 R5D 相同，没有删除上下文空格。收尾文字同步后的复核记录在 `final-static-2/`。

生产维护未开始；本报告不替代真实 Home 的停机一致性、浏览器数据/站点登录恢复、退出全部 SSH 后持续可用、正式 Docker/VPS 重启、Debian 13 或目标 Mac/Trilium 验收。r7 发布组合与实际迁移仍按 R5/R4B 计划推进。
