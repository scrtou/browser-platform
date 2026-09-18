# DEV-2026-09-18-047 · Profile 目录规格误写为独立 flock

状态：已解决（修订规格，2026-09-18；未部署生产）。发现日期：2026-09-18。关联工作项：[R6B](../work-items/R6B-2026-09-17-directory-roles-stop.md)、[R6](../work-items/R6-2026-09-16-environment-management.md)。

## 设计预期

[管理面规格“现有基础与职责变化”](../specs/proxy-environment/management.md#现有基础与职责变化)要求 Profile 目录只有一个写入所有者，并以私有权限、同步和原子替换保护持久化；原表格把并发保护简写为目录文件自身的 `flock`。

## 实际事实与证据

- `adapter/cmd/profile-adapter/main.go` 在构造 Profile 服务前调用 `state.LockService(cfg.StateFile)`；同一 Adapter journal 只能有一个服务进程，Profile 目录也只由该服务写入。
- `adapter/internal/profile/directory.go` 使用进程内 `RWMutex` 串行读取/更新，再以 0600 临时文件、文件 fsync、rename 和目录 fsync 提交；账号 CLI 对 Profile 目录只有只读访问。
- R6B 工作项在实施前已选择“服务锁保证单写者 + 进程内互斥”，但规格表仍写成目录文件独立 `flock`，形成文档与实现不一致。候选未部署，生产不受影响。

## 影响与处理决定

- 影响：实现仍有明确的单写者和原子提交保证；错误在公开规格会误导后续实现者再增加一套文件锁，或误判当前候选缺少并发保护。
- 处理方式：修订设计。规格明确由 Adapter 全局服务锁排除第二个写进程，目录进程内互斥负责同进程更新；保留 0600、fsync 和原子替换要求。
- 不需要用户额外决定；R6C 若引入 Adapter 之外的目录写入者，必须重新设计跨进程锁和所有权，不能沿用本结论。

## 实施、验证与文档同步

| 材料 | 更新 / 结果 |
| --- | --- |
| 实现 | 无代码变更；沿用 `state.LockService`、目录 `RWMutex` 与原子写入 |
| 验收与证据 | `state/service_lock_test.go` 的第二进程拒绝、`profile/directory_test.go` 的持久化/重载/修订检查及全模块 147 项测试、race 均通过 |
| 设计 / 规格 / 组件说明 | 管理面规格的 Profile 定义职责行改为“Adapter 服务锁 + 进程内互斥 + fsync + 原子替换” |
| 进度 / 计划 / 工作项 | R6B 工作项、验收与偏差索引同步；候选未部署，R6C 未开始 |

## 最终复核

2026-09-18：规格与既有单写者实现一致；当前只有运行中的 Adapter 可写目录，CLI 只读。未来增加第二写入者须新建工作项和跨进程锁设计。生产 candidate-4 没有 Profile 目录；解决日期 2026-09-18。
