# DEV-2026-10-01-088 · 新版 Adapter 恢复依赖缺口

状态：已解决（已配置管理 JSON 与独立管理员私钥的归档/重绑缺口）。关联 [R6K](../work-items/R6K-2026-10-01-disaster-recovery.md)，选择补齐备份实现和恢复依赖检查。

独立恢复要求从备份和显式依赖重建服务。secure-backup.collect_control_sources 当前收集普通 Adapter 身份、状态、访问账号和控制根，但不收集配置引用的 profile_directory、environment/template/network catalog、legacy migration 文件及独立 sealskin_admin 私钥；原配置保留绝对路径。直接使用归档会读不到新版管理状态，或者错误依赖仍在的源目录。

原报告只声明单 Home/同主机材料，不改写为过去已通过整机恢复。新增备份成员保存已配置的管理依赖，恢复时显式重绑；缺失依赖或不安全类型拒绝。环境产物/客户端挂载、镜像层、系统工具和作业目录仍需完整依赖清单核对，不能把补齐几个配置文件等同于整机闭包。旧归档保持可读，但缺少新增成员时必须提供显式受信任依赖，不自动回退到源路径。

验证：新增依赖收集/缺失拒绝测试，实际隔离源退役后迁移到新根目录启动并验证管理/身份/数据，124 项备份回归与 8 项布局检查通过，实际新目录恢复和回退通过，见 [R6K 验收](../../infra/sealskin/r6k-disaster-recovery-acceptance-2026-10-01.md)。
