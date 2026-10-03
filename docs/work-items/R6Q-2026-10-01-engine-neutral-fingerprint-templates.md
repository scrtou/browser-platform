# R6Q · 通用指纹模板与生成引擎分离

状态：已收尾（服务器实现、完整 QA 与限定部署）。用户确认将通用指纹配置独立于引擎保存，生成组合时再选择引擎；运行产物仍绑定引擎、版本和验收。

## 范围与实际调用链

`httpapi/manage.go` 指纹表单 → `template_sources.go` 保存源记录 → `profile/template_sources.go CreateTemplateCombination` → v2 queue → `infra/camoufox/environment-job.py`/`template_sources.py` → 固定镜像完整验收 → environment/template 双目录发布。目前来源要求 engine/browser_version，缓存仅按来源 ID；这两个位置需调整，不能只删除页面下拉。

新增通用来源 version 2，仅存名称、locale/languages/timezone；revision 仍是不可变记录修订。生成表单显式选择 browser_template_id，服务端根据 accepted 目录和当前生成器能力生成目标快照（ID/revision/engine/version），写入 v3 作业。执行器在生成及发布前核对目标，产物仍固定完整引擎/镜像/版本。通用来源缓存按目标快照隔离，同一目标改显示复用设备；同一目标的镜像变化拒绝静默重生成。

旧无 version 的来源和 v1/v2 队列继续读取。旧来源保留原引擎限制和缓存，不覆写或猜测迁移；新保存请求拒绝 engine/browser_version。当前生产只有一个 accepted v1 作业，尚无独立来源/显示记录。当前可生成目标仍为 Camoufox 152/Linux、固定 DPR1；Chromix 自定义生成不属于本项，已有组合保持。

## 完成条件与验证

1. 新指纹记录/表单没有引擎和版本；生成组合有明确目标选择，缺失/伪造/不支持的目标拒绝。
2. v3 队列精确绑定来源/显示摘要及 accepted 目标修订；执行器拒绝目标漂移/版本错配，通用来源按目标缓存，显示变化不改变无关参数。
3. 旧来源、v1/v2 作业、缓存和 accepted 产物继续读取；独立 QA 检查旧缓存复用、失败保留、发布恢复和新组合完整生成验收。用户真实 Home/绑定/未完成日志保持。
4. 最小 Adapter 从已部署 R6P 源码构建，完整 test/vet；主机执行器回归、实际 accepted 目录、两种显示组合/真实桌面和页面检查通过后，仅更新 Adapter/空闲作业服务。前后核对生产容器、目录/账号和旧 spool；无浏览器重建。

## 文档与收尾清单

设计、管理规格/规格入口、Adapter/Camoufox/Chromix README、UI/客户端说明、运维、验收/索引、工作项/索引、progress/roadmap。原 R6P 验收保留历史并加后续链接；R6O 用户缩放反馈与百分比保存边界保持。公开记录脱敏，详细资料保存在 ignored `infra/sealskin/runtime/r6q-engine-neutral-20261001/`。

基线：R6P Adapter `031513760425f73be5d70742f7d9892bd8033c494f94ed84f2920489871d31bf`，`runtime/r6p-templates-20261001/final-adapter-source` 与固定 runner；保留所有既有脏改动，不发布 R6I/R7G，不启动其他计划。

实施偏差：[DEV-100](../deviations/DEV-2026-10-01-100-template-combination-responsive.md) 记录有数据的组合表格窄窗口控件溢出，修复布局后按原条件验收。

## 收尾复核

- [x] 原需求：通用指纹源无引擎字段，生成时必选受支持的 accepted 目标，产物继续绑定版本/镜像/报告。
- [x] 实际行为：v3 精确来源/显示摘要与目标修订；按目标缓存、镜像漂移拒绝；旧源字节、v1/v2、原缓存和 accepted 产物兼容。
- [x] 验收：最小 Adapter 完整 test/vet，36 项主机测试及冻结执行器26项；双组合完整验收/真实目录绑定、非显示指纹一致、桌面 A→B→A、两类发布恢复、六组有数据页面通过。
- [x] 偏差：DEV-100 窄屏组合行已修复并部署，修复前失败材料保留。1280 初次生成约束失败保留，经固定来源复用后完整通过。
- [x] 部署：只替换 Adapter 和空闲 runner，精确源码/二进制/清单核对通过，生产容器、目录/账号和旧 spool 保持；QA 运行资源清理，离线证据保留。
- [x] 文档：设计/规格、组件 README、UI/客户端/运维、验收索引、进度/计划与工作项更新；R6P 保留历史并链接后续。

证据见 [R6Q 验收](../../infra/sealskin/r6q-engine-neutral-acceptance-2026-10-01.md)。目标 Mac/Trilium 新表单尚未专门反馈；Chromix 自定义生成、Camoufox 自动模式、R6O 百分比跨客户端保存、异机冷恢复与全计划审计保持各自后续范围。未启动下一计划。
