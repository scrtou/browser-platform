# R7F 生产续跑：DIRECT 能力、Work 备份与发布前置 — 2026-09-29

## 结论与范围

本轮完成 DIRECT 能力观测修正及限定 Adapter 发布、Work 当前停止时点加密备份/校验/独立恢复，以及 Work 迁移输入准备。R7F 仍未收尾：Work 尚未迁入受管理网络，Personal 当前上游、目标 Mac/Trilium 和相关恢复身份条件仍未全部验证。

生产 Adapter 已更新为 `346d63778e56ffb728a9d16b40a412d12d8a0b32dd287c709492c021b8fb3dcc`。旧 `bbef7657…` 二进制保留用于只回退 Adapter。控制器、配置、账号、Profile/模板/网络目录及应用定义未修改；没有启动或停止 Personal、Work 或“测试”浏览器，没有修改真实 Home 或恢复旧 journal。

## 代码与验证

[DEV-076](../../docs/deviations/DEV-2026-09-29-076-direct-capability-observation.md)：控制器 Home 清单本来返回 `network_direct_version`，但 Adapter 的解码结构与 `Capabilities()` 漏掉该字段。新增只读字段映射；缺字段保持 0，未来版本按原值传递，不猜测为已支持版本。现有 `required_runtime_capabilities` 可配置集合不变。

| 检查 | 结果 |
| --- | --- |
| 加密清单协议：缺字段、version 1、未来 version 2 | 通过；原值保留，旧控制器兼容 |
| Adapter 全量 `go test -count=1 ./...`、`go vet ./...`、gofmt | 通过 |
| sealskin/profile/httpapi/access/control 五包 race | 通过 |
| 固定 Go 镜像离线构建 | `sha256:3680233e…`，只读源码、无网络、1.5 CPU/1536 MiB；候选摘要如上 |
| r10 环境登记器、受管桌面单测 | 9 + 2 项通过 |
| 生产 `inspect-profile work` | `network_direct_version=1`，Work 仍 stopped/0 resources |
| 运行二进制与候选、生产配置与运行身份 | 通过；运行进程摘要一致，原 Session/Worker ID、镜像、启动时间和网络模式保持 |

首轮新增协议测试误用了既有夹具未提供的 `/work` 路由而得到 404；改为夹具已有 `/personal`，仍验证相同 DIRECT 字段及三种版本场景。首轮部署检查遗漏入口 Host，得到 421 并恢复旧二进制；按实际配置补齐 Host 后，原 HTTP 200 就绪门槛和身份检查全部通过。失败日志与回退记录保留，没有修改服务来放宽 Host 校验。

## 当前运行状态

| Profile | 状态与绑定 |
| --- | --- |
| “测试” | r10，Profile revision 7；1 record/1 Worker/5 resources/1 Relay/1 Guard/2 networks。15:24 UTC 更新后及 15:25 UTC 最终新鲜探测均为 healthy，浏览器、显示、代理、Session 与新鲜度全部通过 |
| Personal | revision 9，已绑定 `personal-tw-socks` revision 1；stopped，全部运行资源为 0；Home 保留。绑定存在不代表当前代理可达 |
| Work | revision 4，disabled/stopped，全部运行资源为 0；原 Firefox/Wayland 镜像和 Home `work` 保留，尚无 network policy |

## 备份与迁移输入

- Work 当前停止时点：`BACKUP_CREATED`、`BACKUP_VERIFIED`、`BACKUP_RESTORED` 全部成功，**5,195 条目**。使用既有固定运行证据模式，原 Work 精确镜像、构建摘要与历史真实 PASS 匹配；age 固定 `v1.2.1`，解密校验在独立 tmpfs 完成。恢复副本 `ready_to_activate=false`、`access_review_required=true`，未启动或绑定。
- Personal 历史材料复核：2026-09-27 的加密 verify 为 **1,193 条目**，restore 回执存在，密文摘要与恢复回执一致；这不是本轮新建的 Personal 备份，也不证明后续上游可用。
- Work 原镜像 `ec848635…`、受管理候选 `895907b7…` 的完整父层前缀、正常退出/显示认证/Firefox 网络锁定标签、三份源文件摘要和构建输入标签匹配。生产控制器只读宿主机地址证据挂载、DIRECT 能力、网关镜像及本轮备份等 15 项前置检查通过。
- 私有材料固定原 Work 应用、仅替换镜像的审阅草稿、独立 DIRECT 策略输入及原 revision，标为 **DRAFT_NOT_DEPLOYABLE**。原 Work 无网络模式，普通 `SetBrowserManagedDirect` 与统一代理绑定仍会按设计拒绝。仍需受控的 legacy→managed 目录迁移路径、控制器规范化的不可变 policy ID/SHA 和后续认证绑定；不能直接安装仅换镜像的草稿，不能把 Work 猜测成 Camoufox 指纹模板。

## 保留与剩余条件

私有材料位于忽略目录 `infra/sealskin/runtime/r7f-review-20260929-rd3d8P/`：固定工具链日志、两轮检查/发布记录、旧/新 Adapter、Work 密文/恢复副本和 `final-review/` 的脱敏基线与迁移草稿。原有所有 Home、备份、故障记录和 journal 保留。测试容器及解密 tmpfs 已退出清理；备份、恢复副本与回退材料继续保留。

文档收尾：19 份本轮涉及文档的 747 个相对链接/锚点通过，`git diff --check` 通过；修复验收索引中脱离表格的 R7G 条目及 DEV-072 路径。Work 密文和含恢复身份的副本均确认被 Git 忽略。生产服务最终为 active/running，磁盘二进制摘要仍与已部署候选一致。

剩余工作归 R7F：Work 迁移路径、生产 DNS/HTTPS/无直连及数据恢复验收；Personal 当前有效上游与健康重建；旧管理员恢复身份拒绝证据；Mac/Trilium 首页、代理 Tab、模板选择及 r10 桌面右键直接用户确认。R7G 的真实动态 SOCKS5/客户端验收及部署仍不属于本轮。
