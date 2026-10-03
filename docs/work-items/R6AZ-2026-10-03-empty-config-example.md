# R6AZ · 清理默认配置中的旧浏览器示例

状态：已收尾（主分支示例/文档）。开始日期：2026-10-03。结束日期：2026-10-03。

## 目标与范围

用户指出 `adapter/config.example.json` 仍有 personal/work；本项补齐 [1.0整理](../v1.0-delivery-plan.md)漏项。将默认示例改为空浏览器，修正直接复制示例的操作说明，解释历史种子与现行安装路径的区别。基线为 `db8f355`，工作区干净；前项 [R6AY](R6AY-2026-10-03-fingerprint-capability-plan.md)已收尾。

完成条件：示例无旧浏览器种子；明确空目录/账号初始化要求；配置加载和既有目录回归通过；相关文档、偏差、验收及 Git 提交完成。只变更示例与文档，不改业务代码、生产配置/数据、已固定的 v1.0 标签或归档，不开始指纹增强。

## 阅读与代码核对

| 入口/材料 | 事实与实际副作用 |
| --- | --- |
| [配置](../../adapter/internal/config/config.go) → [main](../../adapter/cmd/profile-adapter/main.go) | Load 解析 profiles 和 profile_directory；启动传入 NewService，示例并非仅展示文字 |
| [Service](../../adapter/internal/profile/service.go) → [directory.open](../../adapter/internal/profile/directory.go) | 已有目录覆盖种子；目录缺失且种子非空时持久化导入，种子为空则拒绝缺失目录 |
| [安装器](../../infra/deployment/install.py) | 自行生成 profiles=[]，显式创建空 browsers 数组和待初始化账号表，不读取旧示例 |
| [Adapter说明](../../adapter/README.md)、[组件部署说明](../../infra/sealskin/README.md) | 复制示例的旧指引仍关联 PoC 名称，需要明确现行全新部署入口 |
| [R6AX验收](../../infra/sealskin/r6ax-v1-install-acceptance-2026-10-03.md) | 已覆盖正式安装器空初始化；不证明另一份手动示例已经清理 |

## 实施与偏差

[DEV-168](../deviations/DEV-2026-10-03-168-legacy-default-profile-seeds.md)已解决：修正默认示例与说明；保留兼容导入机制和历史验收记录。同步明确示例中的access/profile_directory依赖lifecycle，不能仅关闭开关连接原版上游。

## 验证方法

静态核对两份公开 Adapter 示例、安装器与默认浏览器列表；通过现有配置加载入口检查示例；运行配置、显式空目录/导入与账号初始化相关已有测试。检查变更文档相对链接及 `git diff --check`。测试仅使用临时资源，不启动生产浏览器或服务。

## 文档与收尾

已更新：Adapter README、SealSkin README、运维安装导航、1.0部署说明与发行补记/交付计划、工作项/偏差/验收索引、docs/README、progress、roadmap。设计/协议不变，示例遵循既有空初始化契约；不改变原验收证据。

验收复核：两份示例实际加载、12项配置及6项目录/账号既有回归通过，详见[报告](../acceptance/r6az-empty-config-example-2026-10-03.md)。私有证据在被忽略的runtime目录，任务构建缓存已回收，生产资源无变更。相对链接及diff检查通过后随本项提交归档。

收尾结论：约定的示例/说明修复已完成；Git提交交付主分支。固定v1.0标签/归档不覆盖，原包按正式安装器使用；本项无需程序部署，未开始其他计划工作。
