# R4B · 目标客户端与实际入口迁移

状态：进行中。登记日期：2026-09-14。开始日期：2026-09-15。结束日期：未结束。

## 目标与范围

- 对应 [R4 父计划](../roadmap.md#r4)，承接已收尾的 [R4A](R4A-2026-09-13-client-migration-qa.md)。用户已确认进入 Personal 迁移，2026-09-15 开始生产候选准备；目标 Mac/Trilium 实机验收仍作为切换后的必要条件。
- 在目标 Mac / Trilium 记录版本、显示缩放、输入法、screen/DPR、坐标、导航/标签页、Files 原生选择/拖放、断线恢复及剪贴板边界，逐项填入 [客户端矩阵](../client-matrix.md)。已发送的版本/缩放/输入法询问仍待答复。
- 完成真实 Home 停机备份及独立恢复验证，重新核对原 Worker、镜像、环境、绑定与迁移候选，按明确维护范围执行 Personal 的 stop → 配置切换 → 新 Home 启动 → 实机验收；保留旧 Firefox Home 与最新 journal。
- 核对回退材料并演练：回退会创建新 Firefox generation，不会复活原 Session。不得用旧 journal 覆盖现有操作记录。
- 工作依赖目标客户端访问、用户的维护时机及 [R2](R2-2026-09-13-boot-recovery.md) 的真实备份条件；Linux 隔离证据不能代替这些条件。等待期间允许按已更新父计划推进独立 R5。

## 已有材料与继续条件

| 材料 | 当前事实 / 使用条件 |
| --- | --- |
| [R4A 验收](../../infra/sealskin/client-migration-acceptance-2026-09-14.md) | Linux 客户端、正常 Camoufox Guard、停止重建已通过；QA 资源已清理 |
| 私有 `runtime/r4-client-migration-2026-09-13/migration-preparation-v2/` | 可审阅候选，`readyToSwitch=false`；执行前重新生成并核对漂移 |
| [迁移准备器](../../infra/camoufox/prepare-migration.py) | 只读生产状态，生成正向/回退配置；不执行 stop、不安装、不改 journal |
| 新客户端包 `c79102f832b141bd` | Unicode 修复仅在 QA 验证，生产仍使用旧包 |
| R5D 正常退出/显示认证与 r7 候选 | 切换前以 `env-tw-camoufox-r7` 和匹配成功报告重新生成候选，并核对控制/Relay/Worker 的全部能力及当前策略；原 R4A/r6 材料不能直接当作 r7 入口发布。[R5E](R5E-2026-09-15-release-combination.md) 正在补登录、Store 与 coherence 组合，生产迁移包尚未生成 |
| [R2A 旧部署加密准备](R2A-2026-09-15-legacy-backup-preparation.md) | 工具、只读实际镜像快照及 80 项测试已收尾；真实 Home 加密备份/隔离浏览器恢复仍待维护窗口，不能用运行快照代替备份 |
| 当前生产 | Work 已恢复旧 Firefox；Personal 旧 Home 已由 R2C 加密归档并保持停止；r7 镜像/产物已在主机但尚未绑定到 Personal |

## 完成条件与验证

目标客户端矩阵有实测分项，失败、不支持与未测如实保留；备份可在隔离环境恢复；切换前后可核对 Home、环境产物、策略和绑定；新入口网络/显示/恢复符合规格；回退步骤可重现。未达到这些条件不能标记 R4 或整体发布通过。

## 文档与收尾

执行时更新客户端矩阵、Trilium 指南、迁移验收、组件 README、设计/规格（若契约改变）、验收索引、进度/计划与本记录。当前已完成 R2C 的真实旧 Home 备份/恢复前置；正在生成 r7 正向/回退候选并准备 Personal 的受控切换。实机验收、生产新代次启动和回退演练尚未完成。
