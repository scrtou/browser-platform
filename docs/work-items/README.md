# 工作项记录

[文档导航](../README.md) · [工作流程](../workflow.md) · [开发进度](../progress.md) · [开发计划](../roadmap.md) · [设计偏差](../deviations/README.md)

每个实施工作项在动手前创建记录，使用 [模板](template.md)。本目录记录执行与收尾，当前产品状态仍以 `progress.md` 为准，优先级仍以 `roadmap.md` 为准。

状态使用：**待启动 → 准备中 → 进行中 → 待验证 → 已收尾**。待启动可保存预读草稿，不算正在实施。外部条件不足时使用 **待外部条件** 并写清继续条件。正在实施的工作项收尾前不能开始下一项计划；模板勾选不能代替实际证据。

| 工作项 | 对应计划 | 状态 | 收尾 / 下一步 |
| --- | --- | --- | --- |
| [R2C 生产旧 Home 维护](R2C-2026-09-15-production-home-maintenance.md) | [R2](../roadmap.md#r2) | 已收尾 | Personal/Work 真实旧 Home 加密备份、隔离恢复与 Work 恢复完成；Personal 旧 Home/应用/journal 保留，迁移转入 R4B |
| [R2B 旧 Firefox 加密恢复实测](R2B-2026-09-15-legacy-browser-recovery.md) | [R2](../roadmap.md#r2) | 已收尾 | 真实旧 Firefox/Wayland 三类存储 age 往返、错误路径、源先退出、新根读回和 QA 清理通过；生产维护与目标 Mac 条件保持 |
| [R5E r7 登录、凭据与一致性组合](R5E-2026-09-15-release-combination.md) | [R5](../roadmap.md#r5) | 已收尾 | 23 项实际组合、101 项备份、加密新环境恢复及 DEV-038、版本/清理/文档核对完成；未部署，R2/R4B 条件保留 |
| [工作流程落地](DOCS-2026-09-13-workflow.md) | 本次文档任务 | 已收尾 | 流程、代码地图、偏差目录、模板与状态同步完成，静态核对通过 |
| [R1 运行健康与恢复提示](R1-2026-09-13-runtime-health.md) | [R1](../roadmap.md#r1) | 已收尾 | 2026-09-13 上线 `0.3.2-health-v1`；隔离 QA 14 项与线上回归通过；Mac/Trilium 提示页复测归入 R4。下一项 R2 可开始 |
| [R2 开机持久运行与生产恢复](R2-2026-09-13-boot-recovery.md) | [R2](../roadmap.md#r2) | 待外部条件 | 按序恢复、备份工具、linger、真实旧 Home 恢复及正式生产 Caddy/Docker/VPS 同代次恢复通过；退出全部登录与 Debian 13 待验证 |
| [R2A 旧部署加密备份与维护准备](R2A-2026-09-15-legacy-backup-preparation.md) | [R2](../roadmap.md#r2) | 已收尾 | 独立旧格式、80 项备份/CLI 检查、两个生产只读快照及身份前置检查通过；DEV-037、QA 清理、生产保持与文档静态完成。真实 Home/维护条件仍归 R2 |
| [R3 生命周期与数据保护](R3-2026-09-13-lifecycle-protection.md) | [R3](../roadmap.md#r3) | 已收尾 | 2026-09-13 上线 `0.3.2-lifecycle-v2`；9 项隔离演练与发布回归通过；生产未启用空闲回收/门槛（用户决定）。下一项 R4 可开始 |
| [R4A 客户端边界与 Camoufox 隔离迁移](R4A-2026-09-13-client-migration-qa.md) | [R4](../roadmap.md#r4) | 已收尾 | 2026-09-14 Linux 矩阵、非文本评估、11 项 Camoufox 网络/停止重建与迁移候选完成；QA 清理，生产未切换；R4B 实机与维护条件保留 |
| [R4B 目标客户端与实际迁移](R4B-2026-09-14-target-client-migration.md) | [R4](../roadmap.md#r4) | 已收尾 | 2026-09-17 共享控制器、账号入口、Work 兼容镜像和 r9/fill-r10 Personal 切换生产；服务器端、目标 Mac 生产验收及正式 Caddy/Docker/VPS 重启通过，DEV-040–044 已解决；退出登录/Debian 13 归 R2，下一项按进度/计划重新选取 |
| [R6 远程浏览器管理面（设计与父项）](R6-2026-09-16-environment-management.md) | [R6](../roadmap.md#r6) | 进行中（父项） | R6A–R6E 候选已收尾；R6F 已将列表/账号/修改/停启/关闭安全子集部署生产，新增/删除、代理、指纹关闭；真实客户端安全子集已验证，完整组合仍待验证 |
| [R6B Profile 目录、账号角色、管理员面板与关闭按钮](R6B-2026-09-17-directory-roles-stop.md) | [R6](../roadmap.md#r6) / 管理面第 2 步 | 已收尾 | 2026-09-18：Profile 目录与热更新、账号 v2 角色、面板仅管理员、reauth/改密、按账号撤销、关闭按钮；DEV-045–047 已解决；candidate-2 的 147 项测试、vet、race 通过，未部署。下一子项 R6C 已收尾 |
| [R6E 自定义指纹生成与验收作业](R6E-2026-09-18-custom-fingerprint-jobs.md) | [R6](../roadmap.md#r6) / 管理面第 5 步 | 已收尾 | 2026-09-19：高层字段作业与私有 spool、主机执行器隔离生成/有界重试/完整验收/镜像核对/目录追加、失败保留、内存排队；DEV-051 已解决；249 项 Go 测试、vet、gofmt、race、21 项主机 Python 与一次真实作业通过，未部署。下一项 R6F |
| [R6F 组合 QA、真实客户端、生产候选与回退](R6F-2026-09-19-release-combination.md) | [R6](../roadmap.md#r6) / 管理面第 6 步 | 进行中 | 安全子集与现有环境 overlay 已生产部署；固化/自定义指纹组合、Mac/Trilium 安全子集、账号密码操作及组合控制根加密恢复已通过并清理；真实生产 Home 备份、Mac 自定义 artifact、Profile 生命周期写操作和实际回退仍待完成 |
| [R6D 代理草稿、隔离探针与 proxy_required 修订](R6D-2026-09-18-proxy-drafts.md) | [R6](../roadmap.md#r6) / 管理面第 4 步 | 已收尾 | 2026-09-18：代理草稿、控制器管理员接口的 Secret Store 导入/有界探针/策略追加、版本只增与撤销、下一代次绑定、切回 DIRECT；DEV-049/050 已解决；243 项 Go 测试、vet、gofmt、race 与 545 项控制器 pytest 通过，未部署。下一项 R6E |
| [R6C 新增删除浏览器、Home 归档与 launch plan](R6C-2026-09-18-create-delete-launch.md) | [R6](../roadmap.md#r6) / 管理面第 3 步 | 已收尾 | 候选隔离验证完成：创建/删除目录记录、管理员应用安装/删除、Home 创建/控制器归档、固化环境与 DIRECT/现有策略引用、一次性 launch plan；234 项 Go 测试、race/vet/gofmt 与控制器 pytest 通过，未部署。下一项 R6D |
| [R6A 授权环境列表与只读环境摘要](R6A-2026-09-17-environment-list.md) | [R6](../roadmap.md#r6) / 管理面第 1 步 | 已收尾 | 2026-09-17 网关 `view`/`start` 授权、只读摘要服务、`/manage/` 页面与 JSON；12 项新增测试、138 项全模块、vet、race 通过；候选未部署，账号表格式未变；用户随后要求面板仅管理员，DEV-045 已由 R6B 解决 |
| [R5A 上游代理协议与认证](R5A-2026-09-14-proxy-protocols.md) | [R5](../roadmap.md#r5) | 已收尾 | 六组/70 项网络检查、三种错误密码、181 项 Python 与 r6 正常退出修复通过；QA 清理和生产前后核对完成，未部署；可开始 R5B |
| [R5B Secret Store、撤销与加密恢复](R5B-2026-09-14-secret-store.md) | [R5](../roadmap.md#r5) | 已收尾 | 226 项控制端、39 项备份/挂载测试、18 项运行检查、加密新环境恢复及扫描通过；QA/文档收尾、生产保留核对完成，未部署；可开始 R5C |
| [R5C1 受管理 DIRECT 隔离](R5C1-2026-09-14-direct-isolation.md) | [R5](../roadmap.md#r5) / R5C | 已收尾 | 274 项控制端、25 项挂载/Guard、21 项核心运行检查、QA 清理及文档/构建静态核对通过，生产保持，未部署；下一项 R5C2 DNS/TTL，R5C3 一致性仍待后续 |
| [R5C2 批准解析器、公开 DNS 与真实 TTL](R5C2-2026-09-14-approved-dns-ttl.md) | [R5](../roadmap.md#r5) / R5C | 已收尾 | 固定候选与标准 Unbound 的真实公开三路径/180 秒 TTL、52 项网页协议、冻结/两轮故障恢复/新代次、100 次绕过阻断及日志关联通过；DEV-012–019 已处理，清理/文档完成，生产保持。下一项 R5C3，未部署生产 |
| [R5C3 运行时网络与浏览器环境一致性](R5C3-2026-09-14-runtime-coherence.md) | [R5](../roadmap.md#r5) / R5C | 已收尾 | 候选 6 的 484 项控制、C01–C05/恢复/隔离、版本核对、资源清理及文档检查通过；DEV-020–029 已处理，生产保持，未部署；下一项 R5D |
| [R5D 入口登录、Session 授权与各层脱敏](R5D-2026-09-14-entry-authentication.md) | [R5](../roadmap.md#r5) | 已收尾 | 2026-09-15 C3/r7 的 534 项控制、82+37 项配套、13 项真实客户端、五类材料拒绝与 407 面扫描通过；DEV-030–036、QA 清理、生产保持、候选准备和文档静态核对完成；未部署，R2/R4B 发布条件保留 |

文件命名为 `计划编号-YYYY-MM-DD-主题.md`。子项要链接父计划，保留完整完成条件；遇到偏差立即创建单独记录并双向链接。
