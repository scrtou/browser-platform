# DEV-2026-09-20-057 · 当前 Work 固定镜像缺少环境产物字段

状态：已解决（工具与生产 Work 备份阶段）。关联工作项：[R6F](../work-items/R6F-2026-09-19-release-combination.md)。

## 预期

当前启用 Secret Store、入口账号和密封 Session 的生产 Profile 应使用 `secure-backup.py create` 完成停机一致性加密备份，并把 Home、控制状态、必要密钥和该应用实际采用的固定运行材料一起纳入归档。工具不得静默降级到旧格式，也不得补造环境验收报告。

## 实际事实

- Personal 的 Camoufox 应用包含环境 artifact、完整 acceptance 及其摘要，现有 `create` 路径可直接核对并归档。
- Work 的 `firefox-work` 是 R4B 部署的兼容应用，应用定义固定精确镜像 `sha256:ec848635…`，但没有 Camoufox 环境 artifact/acceptance 字段；这是该 Firefox 兼容发布的原有数据模型，不表示镜像未验收。
- R4B 私有证据已有固定镜像构建记录、部署后实际运行检查和重启恢复检查；公开验收也记录了镜像、正常退出、显示认证、客户端和生产结果。
- 现有 `secure-backup.py create` 无条件要求应用中的环境摘要与传入文件匹配，因此会在读取 Home 前安全拒绝 Work。`create-legacy` 只适用于没有 Store、入口账号和密封 Session 的旧部署，不能用于当前 Work。

## 处理

保留现有冻结环境路径和旧格式边界，新增显式的固定运行证据模式：只允许应用没有环境摘要且镜像引用已经固定为完整 `sha256:` ID 时使用；构建记录必须把 `imageId` 绑定到同一镜像，实际运行验收必须为 `PASS`，并把同一 Profile 的 Worker 镜像和运行状态绑定到该镜像。归档继续使用当前加密格式并包含两份证据、Store、账号、Session、身份和控制状态；不自动从普通失败降级，也不修改生产应用定义。

实现后固定 checks 镜像中的新格式、固定运行证据、coherence、旧格式和运行时节点四组回归共 118 项通过。随后以 R4B 原始构建记录与生产 `PASS` 运行检查对 Work 执行正常停止和当前格式备份：5,174 个条目创建、verify 和全新隔离 restore 通过，只排除已识别的 Wayland 运行时 socket。源 Home 保留，恢复 Store 保持锁定，未 activate。

## 影响与范围

Work 随后已由已认证固定入口使用原 Home 创建新 generation，固定镜像、原 Home 挂载和强制新鲜健康报告通过；浏览器内数据仍待用户目视确认。Personal 健康新代次不受影响。该兼容路径只解决当前已有固定 Firefox 运行证据的归档输入，不把 Firefox 兼容镜像改写成 Camoufox 环境 artifact，也不扩大 R4B 的历史验收范围。
