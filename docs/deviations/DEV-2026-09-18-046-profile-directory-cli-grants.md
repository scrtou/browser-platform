# DEV-2026-09-18-046 · 账号 CLI 在持久化 Profile 目录启用时仍接受静态种子授权

状态：已解决（R6B 候选，2026-09-18；未部署生产）。发现日期：2026-09-18。关联工作项：[R6B](../work-items/R6B-2026-09-17-directory-roles-stop.md)、[R6](../work-items/R6-2026-09-16-environment-management.md)。

## 设计预期

[管理面规格](../specs/proxy-environment/management.md#核心对象)与 R6B 工作项规定：`profile_directory` 存在后，持久化目录是运行中 Profile 集合的事实来源，配置中的 `profiles` 只用于首次导入；账号 CLI 必须按该目录校验授权。目录不可读或无效时应拒绝账号变更，不能退回静态种子继续写入。

## 实际事实与证据

- R6B 收尾复核发现 `adapter/cmd/profile-accounts/main.go` 的 `known` 回调读取目录后，仍把目录 ID 与配置种子 ID 合并；目录读取失败时还会静默返回配置种子。
- 当配置种子仍包含已从权威目录移除的 Profile 时，CLI 可写入该授权；运行中 Adapter 随后按目录校验账号表，会拒绝整张表并撤销登录。
- R6C 尚未实现正常删除路径，但现有“目录是事实来源”契约已经要求此边界；候选未部署，生产 candidate-4 没有 `profile_directory`，生产不受影响。

## 影响与处理决定

- 影响：未部署的 R6B CLI 候选可能写入与运行中 Profile 集合不一致的账号表，造成候选 Adapter 拒绝账号表并撤销登录。
- 处理方式：在 R6B 收尾内修复实现。CLI 启动时若配置了 `profile_directory`，先成功读取目录并以其 ID 完全替换静态种子集合；读取失败立即拒绝，不写账号表。
- 不需要用户额外决定；新增回归测试覆盖静态种子多于权威目录和目录不可读两条失败边界，验证完成前 R6B 保持待复核。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | `profile-accounts` 在建立 `AccountStore` 前读取持久化目录；成功后用目录 ID 替换配置种子，失败直接返回，不再静默回退或取并集 |
| 验收与证据 | 新增 `TestPersistedDirectoryIsAuthoritativeForCLIGrants`：拒绝只存在于静态种子的授权、目录损坏时拒绝且账号表字节不变；全模块 147 项测试、vet、gofmt 及 checks 镜像 race 通过，见 [R6B 验收](../../infra/sealskin/environment-directory-acceptance-2026-09-17.md) |
| 设计 / 规格 / 组件说明 | 既有“目录为事实来源、静态配置仅首次导入”契约不变 |
| 进度 / 计划 / 工作项 | R6B 验收、工作项、进度、计划和偏差索引已同步；候选未部署，下一子项仍为 R6C |

## 最终复核

2026-09-18：CLI 只接受权威目录中的 Profile，目录缺失、损坏或不安全时在账号锁和写入前失败；最终 candidate-2 二进制、147 项测试及全模块 race 通过。candidate-1 与环境性 race 重试保留在私有证据目录。生产未部署 R6B，candidate-4、version 1 账号表和现有登录不受影响；解决日期 2026-09-18。
