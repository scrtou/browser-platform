# R2C · 生产旧 Home 加密备份与恢复维护

状态：已收尾。开始日期：2026-09-15。结束日期：2026-09-15。

## 目标与范围

承接 [R2](R2-2026-09-13-boot-recovery.md)、[R2A](R2A-2026-09-15-legacy-backup-preparation.md) 和 [R2B](R2B-2026-09-15-legacy-browser-recovery.md)，在已授权的维护窗口对生产 Personal 与 Work 两个旧 Firefox 代次执行真实 Home 的停机一致性加密备份和隔离恢复核对。用户已确认 `Linger=yes`、Adapter `active`，并提供目标客户端 macOS 15.1 (24B83)、Trilium 0.105.0，可执行 Files、断线重连和剪贴板实测。

本项不部署 R5E/r7、不切换入口、不迁移 Personal 到 Camoufox、不删除旧 Home。停机前保存当前 journal、容器、镜像、绑定和配置摘要；每个旧 Worker 的实际 image ID 与当前应用定义分别记录。失败时保留占用和日志，不强杀浏览器。

## 前置与维护范围

- 维护对象：生产 `personal` 与 `work` 两个现有旧 Firefox Profile；SealSkin 控制器、Adapter、静态 Relay 和 Caddy 保持运行，除非恢复演练明确进入主机重启阶段。
- 已满足：`Linger=yes`，用户 Adapter 服务 `active`；R2B 独立 QA 旧 Firefox/Wayland 三类存储恢复通过。
- 本项待确认：真实 Home 停止、age 加密归档、隔离恢复读取、退出登录持续运行验证、Docker/VPS 重启及 Debian 13 是否在同一窗口执行。

## 完成条件

- 两个 Profile 停止前的运行快照、Home/容器/绑定和输入摘要保存到私有运行目录。
- 每个 Profile 经过正常停止并确认 Session、Worker、网络资源为空后，`create-legacy`、`verify`、新私有目录 `restore` 成功；归档不含未授权参数或公开秘密。
- 恢复目录核对服务身份、实际旧镜像、Home 数据和控制状态；不直接激活旧格式，不覆盖生产 Home。
- 退出全部登录会话后 Adapter 保持可用；如执行主机重启，记录完整启动窗口和失败回滚。
- 生产两个 Profile 的容器、Home、配置、journal 和入口绑定前后一致或有明确维护记录；QA/临时资源清理。
- 更新 R2、运维说明、验收索引、进度/计划、本记录；未执行的 Debian 13、R4B Mac 项目和 R5E 发布继续明确标记。

## 收尾结论

已收尾。只读基线、Personal/Work 运行快照、两个旧 Home 的 age 加密归档、verify、离线 restore 均已完成；Work 已按原旧 Firefox 镜像恢复运行并确认资源完整。Personal 在迁移切换前保持停止，旧 `personal` Home、旧 Firefox 应用、最新 journal 和加密归档均保留。用户已选择进入 [R4B](R4B-2026-09-14-target-client-migration.md)，后续由 R4B 创建新的 r7 Home/应用/策略并启动新代次；本项不把迁移结果计入备份维护。R5E 候选未部署。

### 收尾核对

- [x] 两个旧 Home 均完成停机一致性 age 加密归档、verify 与隔离 restore。
- [x] Work 已恢复原旧 Firefox 代次并确认 Adapter 记录、Worker 与资源完整。
- [x] Personal 保持停止，旧 Home、应用、journal 和回退材料未删除或覆盖。
- [x] 详细 inspect、归档和恢复证据保留在被忽略的私有目录；公开记录未写入凭据、私钥或授权 Session URL。
- [x] 未部署 R5E/r7、未修改 Caddy/SealSkin 入口；后续迁移由 R4B 单独登记和验收。
