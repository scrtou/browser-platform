# DEV-2026-09-19-055 · 加密备份校验器拒绝 R6F version 2 账号表

状态：已解决（工具代码与组合 QA）。关联工作项：[R6F](../work-items/R6F-2026-09-19-release-combination.md)。

## 预期

R6F 组合根的 `secure-backup.py` 应能收集当前 Adapter 账号表，并保留现行账号角色、Profile 授权和禁用状态；归档前必须拒绝无效或不完整的账号材料。

## 实际事实

- 2026-09-19 首次使用当前 SealSkin 控制根和已停止的 QA Home 执行加密归档时，`secure-backup.py` 返回 `BACKUP_ACCESS_REGISTRY_INVALID`。
- 当前生产 `entry-users.json` 已按 R6B/R6F 升级为 `version: 2`，包含 `role: admin|user`；旧校验器只接受 `version: 1`，并把 `role` 视为未知字段。
- 失败发生在归档创建前，没有生成归档、没有修改生产服务、Home、账号表或 Secret Store。

## 处理

将校验器与 Adapter 账号契约对齐：接受 version 1/2；version 1 禁止角色字段；version 2 只接受 `admin`/`user`；管理员可没有 Profile 授权，普通入口账号仍至少需要一个授权。新增 version 2 管理员/入口账号回归，固定 checks 镜像中的 116 项备份测试通过。

修复后使用同一当前控制根、当前 version 2 账号表、当前 Session/Secret Store 和 r9 环境资产，在停止且不再绑定生产的旧 QA Home 上完成真实 age v1.2.1 加密归档、verify 和离线 restore（4543 个成员；排除一个已识别的 Wayland 运行时 socket）。证据保存在被忽略的 `infra/sealskin/runtime/r6f-release-combination-2026-09-19/combination-backup-1/`。

## 影响与范围

该修复使 R6F 组合控制根能够被当前账号表格式保护；它不等同于真实 Personal/Work Home 的停机备份。生产 Profile 仍在运行，本轮没有停止或写入其 Home；真实生产 Home 备份需用户明确选择 Profile 和维护窗口后另行执行。
