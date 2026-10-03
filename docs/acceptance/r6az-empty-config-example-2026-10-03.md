# R6AZ · 默认空浏览器示例验收

结果：PASS（2026-10-03）。关联[工作项](../work-items/R6AZ-2026-10-03-empty-config-example.md)与[DEV-168](../deviations/DEV-2026-10-03-168-legacy-default-profile-seeds.md)。基线 `db8f355`；变更只含示例和文档。

| 核对项 | 结果及范围 |
| --- | --- |
| 两份Adapter示例 | JSON解析通过，profiles均为空，profile_directory及lifecycle启用；组件示例旧personal/work种子已移除 |
| 实际配置加载 | Go 1.27.1执行现有 profile-adapter 的 `-inspect-capacity`，两份示例均通过严格Load/Validate及本机只读容量检查；该路径不读控制密钥、不连接控制器、不写业务状态 |
| 配置回归 | `go test -count=1 -v ./internal/config`，12项通过，含空种子/目录依赖与访问控制条件 |
| 目录与账号回归 | 6项已有测试通过：显式空目录忽略旧种子/首条持久化与重开、缺失损坏拒绝、兼容种子导入、显式初始化账号表、并发仅首个管理员建立且不覆盖、CLI授权以持久目录为准 |
| 正式安装器 | 源码核对独立生成空profiles、空browsers和待初始化账号表；本项未重新安装，原真实安装证据仍归R6AX |
| 文档 | 两处组件指引、空目录/账号表格式及权限、安装器关系和发行补记同步；检查变更文档相对链接及diff空白 |
| 隔离与清理 | 仅既有测试临时资源及只读配置命令，任务独立Go构建缓存已删除；无生产服务、浏览器、账号或Home修改 |

私有执行记录：`infra/sealskin/runtime/r6az-config-example-20261003/validation.json`、四份加载/测试日志及`document-checks.json`。未新增业务代码或重复实现型测试。

目录/账号回归选择：`TestExplicitEmptyDirectoryCanCreateFirstBrowserAndReopen`、`TestEmptyDirectoryStillRejectsMissingAndMalformedState`、`TestDirectoryImportsPersistsAndHotUpdates`、`TestExplicitBootstrapStateRejectsAmbiguousOrCorruptRegistry`、`TestInitCreatesOnlyFirstAdminAndNeverReplaces`、`TestPersistedDirectoryIsAuthoritativeForCLIGrants`。

交付范围：主分支示例修正；固定v1.0标签/归档不重写，旧归档使用者应按正式安装说明生成配置。无需部署程序；回滚限本项示例/文档，不恢复任何历史业务数据。本项不宣称新一轮真实安装、三引擎或供应方验证。
