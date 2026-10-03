# DEV-2026-09-29-074 · 环境登记器缺少模板一致性元数据

状态：已解决（登记器元数据契约）。发现日期：2026-09-29。关联工作项：[R7F R7 组合候选、生产发布与目标客户端验收](../work-items/R7F-2026-09-23-production-release.md)。

## 设计预期与实际差异

R7D 要求环境目录中的 accepted artifact 保存 `template_revision`、浏览器模板 ID、engine/version、OS/platform 和完整 User-Agent，模板目录再据此验证浏览器、指纹产物和显示模板三元组。生产 r9 与已有自定义 artifact 已具备这些字段。

R7F 登记 r10 的发布前演练发现，`environment-job.py register` 与自定义作业共用的 `catalog_entry` 仍只写 R6E 字段；生成条目缺少全部 R7D 元数据。若把该条目加入兼容目录，Adapter 会按设计以 `ErrTemplateCatalogUnavailable` 拒绝，不能通过手工修改生产 JSON 绕过。

## 处理决定

- 修复共享登记器：调用者必须显式提供 accepted 浏览器模板 ID；其他一致性字段从已验收 artifact 的规格和 resolved config 派生。
- Firefox User-Agent 产品版本与 `rv` 必须同时存在且一致；OS 必须为当前支持的 Linux，revision/platform/UA 缺失均以 `CATALOG_METADATA_INVALID` 拒绝发布。
- 固化登记和自定义作业使用同一路径与回归，r10 重新从原 artifact/acceptance 生成目录条目，不修改产物字节。

## 验证与收尾

登记器 9 项单测、r10 候选目录和生产环境目录登记已通过；Adapter r10 已部署并正常监听。管理页已将“测试”绑定到 r10（Profile revision 7，精确 artifact SHA `f785549f…`）。用户从固定入口重新打开后，14:04 UTC 强制探测为 `healthy`，r10 环境元数据和 artifact 绑定与登记值一致。偏差仍保持处理中，待 R7F 整体收尾时统一核对目标客户端与其余发布条件。

## 2026-09-30 独立收尾

本轮从实际 `template_metadata` 实现重新派生三个 accepted 原 artifact 的七个字段，与当前目录逐项相同，前后生产快照保持。结合已有九项回归、固定/自定义登记共用代码、r10 实际登记/绑定/健康启动及 352 文件包的完整依赖核对，本偏差自身条件已满足，状态改为已解决。上段“等 R7F 整体收尾”保留为此前跟踪方式；Trilium 桌面菜单与客户端尺寸继续由 DEV-073/R7F 独立追踪，不因本偏差关闭而算通过。见 [父项完成条件复核](../../infra/sealskin/r7f-completion-review-2026-09-30.md)。
